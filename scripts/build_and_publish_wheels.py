#!/usr/bin/env python3
"""Build provider/consumer wheels and optionally publish to a GitHub release."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from email import message_from_bytes
from pathlib import Path
from typing import Any

DEFAULT_REPO = "mp3monster/fluent-opamp"
DEFAULT_PROVIDER_SBOM_PATH = (
    "dist/sbom/opamp_provider_deployable_artifacts.cyclonedx.json"
)
DEFAULT_CONSUMER_SBOM_PATH = (
    "dist/sbom/opamp_consumer_deployable_artifacts.cyclonedx.json"
)


def _run(cmd: list[str], *, cwd: Path) -> None:
    """Run one subprocess command and stream output to the console."""
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _ensure_python_build(repo_root: Path, python_exe: str) -> None:
    """Ensure the `build` package is available for wheel generation."""
    probe = subprocess.run(
        [python_exe, "-m", "pip", "show", "build"],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode == 0:
        return
    print("Python package `build` not found; installing it now...")
    _run([python_exe, "-m", "pip", "install", "build"], cwd=repo_root)


def _clean_dir(path: Path) -> None:
    """Remove files from one directory, creating it when absent."""
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file():
            child.unlink()


def _build_component_wheel(
    *,
    repo_root: Path,
    python_exe: str,
    component_dir: str,
    out_dir: Path,
) -> Path:
    """Build one wheel and return its path."""
    _clean_dir(out_dir)
    _run(
        [
            python_exe,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(out_dir),
            str(repo_root / component_dir),
        ],
        cwd=repo_root,
    )
    wheels = sorted(out_dir.glob("*.whl"))
    if not wheels:
        raise RuntimeError(f"wheel build for {component_dir} produced no .whl files")
    if len(wheels) > 1:
        print(
            f"warning: multiple wheels found for {component_dir}; using latest: "
            f"{wheels[-1].name}"
        )
    return wheels[-1]


def _normalize_dist_name(value: str) -> str:
    """Normalize distribution name to a stable lowercase key."""
    return str(value or "").strip().lower().replace("_", "-")


def _sha256(path: Path) -> str:
    """Return SHA-256 digest for one file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _read_wheel_metadata(wheel_path: Path) -> dict[str, Any]:
    """Read Name/Version/Requires-Dist from a wheel METADATA payload."""
    metadata_bytes: bytes | None = None
    with zipfile.ZipFile(wheel_path, "r") as archive:
        for member in archive.namelist():
            if member.endswith(".dist-info/METADATA"):
                metadata_bytes = archive.read(member)
                break
    if metadata_bytes is None:
        raise RuntimeError(f"wheel missing dist-info/METADATA: {wheel_path}")

    metadata = message_from_bytes(metadata_bytes)
    name = str(metadata.get("Name") or wheel_path.stem).strip()
    version = str(metadata.get("Version") or "0").strip()
    requires_dist = [str(item).strip() for item in metadata.get_all("Requires-Dist") or []]
    return {"name": name, "version": version, "requires_dist": requires_dist}


def _requirement_name(requirement: str) -> str:
    """Extract dependency package name from Requires-Dist entry."""
    cleaned = requirement.split(";", 1)[0].strip()
    stop_chars = [" ", "(", "[", "!", "<", ">", "=", "~", ";"]
    end = len(cleaned)
    for char in stop_chars:
        pos = cleaned.find(char)
        if pos != -1:
            end = min(end, pos)
    return cleaned[:end].strip()


def _build_cyclonedx_sbom(
    *,
    repo: str,
    artifact: Path,
    sbom_path: Path,
    root_component_name: str,
) -> Path:
    """Generate CycloneDX JSON SBOM for one deployable wheel artifact."""
    components: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    dependency_components: dict[str, dict[str, Any]] = {}

    wheel_meta = _read_wheel_metadata(artifact)
    name = str(wheel_meta["name"])
    version = str(wheel_meta["version"])
    bom_ref = f"pkg:pypi/{_normalize_dist_name(name)}@{version}"
    wheel_component = {
        "type": "library",
        "name": name,
        "version": version,
        "bom-ref": bom_ref,
        "purl": bom_ref,
        "hashes": [
            {
                "alg": "SHA-256",
                "content": _sha256(artifact),
            }
        ],
        "properties": [
            {"name": "opamp.artifact.path", "value": str(artifact)},
        ],
    }
    components.append(wheel_component)

    depends_on: list[str] = []
    for requirement in wheel_meta["requires_dist"]:
        # SBOM targets deployable artifacts; omit optional extras such as dev deps.
        if "extra ==" in requirement.lower():
            continue
        dep_name = _requirement_name(requirement)
        if not dep_name:
            continue
        dep_ref = f"pkg:pypi/{_normalize_dist_name(dep_name)}"
        depends_on.append(dep_ref)
        if dep_ref not in dependency_components:
            dependency_components[dep_ref] = {
                "type": "library",
                "name": dep_name,
                "bom-ref": dep_ref,
                "purl": dep_ref,
                "properties": [
                    {"name": "opamp.requirement.raw", "value": requirement},
                ],
            }
    dependencies.append(
        {
            "ref": bom_ref,
            "dependsOn": sorted(set(depends_on)),
        }
    )

    if dependency_components:
        components.extend(
            dependency_components[key] for key in sorted(dependency_components.keys())
        )

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "tools": [{"vendor": "mp3monster", "name": "build_and_publish_wheels.py"}],
            "component": {
                "type": "application",
                "name": root_component_name,
                "version": version,
                "properties": [
                    {"name": "github.repository", "value": repo},
                    {"name": "wheel.name", "value": name},
                ],
            },
        },
        "components": components,
        "dependencies": dependencies,
    }
    sbom_path.parent.mkdir(parents=True, exist_ok=True)
    sbom_path.write_text(f"{json.dumps(sbom, indent=2)}\n", encoding="utf-8")
    return sbom_path


def _github_request(
    *,
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    content_type: str = "application/json",
) -> Any:
    """Issue an authenticated GitHub API request and return parsed JSON (if any)."""
    data: bytes | None = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "opamp-wheel-publisher",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req) as resp:  # nosec B310 - controlled GitHub API URL.
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {body}") from exc


def _github_upload_asset(
    *,
    upload_url_template: str,
    asset_path: Path,
    token: str,
) -> Any:
    """Upload one release asset to GitHub uploads API."""
    base_upload_url = upload_url_template.split("{", 1)[0]
    query = urllib.parse.urlencode({"name": asset_path.name})
    url = f"{base_upload_url}?{query}"
    data = asset_path.read_bytes()
    content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "opamp-wheel-publisher",
        "Content-Type": content_type,
        "Content-Length": str(len(data)),
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:  # nosec B310 - controlled GitHub uploads URL.
            raw = resp.read()
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub asset upload failed for {asset_path.name}: {exc.code} {body}"
        ) from exc


def _release_by_tag(*, repo: str, tag: str, token: str) -> dict[str, Any] | None:
    """Return release JSON for one tag when it exists; otherwise None."""
    url = f"https://api.github.com/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "opamp-wheel-publisher",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:  # nosec B310 - controlled GitHub API URL.
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub release lookup failed: {exc.code} {body}") from exc


def _create_release(
    *,
    repo: str,
    tag: str,
    token: str,
    name: str | None,
    body: str,
    draft: bool,
    prerelease: bool,
) -> dict[str, Any]:
    """Create a GitHub release and return its JSON payload."""
    payload = {
        "tag_name": tag,
        "name": name or tag,
        "body": body,
        "draft": bool(draft),
        "prerelease": bool(prerelease),
    }
    return _github_request(
        method="POST",
        url=f"https://api.github.com/repos/{repo}/releases",
        token=token,
        payload=payload,
    )


def _delete_existing_assets(
    *,
    repo: str,
    release: dict[str, Any],
    token: str,
    asset_names: set[str],
) -> None:
    """Delete same-name assets from a release so re-uploads succeed."""
    for asset in release.get("assets", []):
        name = str(asset.get("name") or "")
        if name not in asset_names:
            continue
        asset_id = asset.get("id")
        if not isinstance(asset_id, int):
            continue
        print(f"Removing existing release asset: {name}")
        _github_request(
            method="DELETE",
            url=f"https://api.github.com/repos/{repo}/releases/assets/{asset_id}",
            token=token,
        )


def _publish_wheels(
    *,
    repo: str,
    tag: str,
    release_name: str | None,
    release_notes: str,
    draft: bool,
    prerelease: bool,
    token: str,
    artifact_paths: list[Path],
) -> None:
    """Create or update one release and upload build artifacts as assets."""
    release = _release_by_tag(repo=repo, tag=tag, token=token)
    if release is None:
        print(f"Creating GitHub release {tag} in {repo}...")
        release = _create_release(
            repo=repo,
            tag=tag,
            token=token,
            name=release_name,
            body=release_notes,
            draft=draft,
            prerelease=prerelease,
        )
    else:
        print(f"Using existing GitHub release for tag {tag}.")

    _delete_existing_assets(
        repo=repo,
        release=release,
        token=token,
        asset_names={path.name for path in artifact_paths},
    )

    upload_url = str(release.get("upload_url") or "")
    if not upload_url:
        raise RuntimeError("GitHub release payload missing upload_url")

    for artifact_path in artifact_paths:
        print(f"Uploading {artifact_path.name}...")
        asset = _github_upload_asset(
            upload_url_template=upload_url,
            asset_path=artifact_path,
            token=token,
        )
        print(f"Uploaded: {asset.get('browser_download_url', '<no download URL>')}")


def _load_release_notes(args: argparse.Namespace) -> str:
    """Resolve release notes from CLI options."""
    if args.release_notes_file:
        return Path(args.release_notes_file).read_text(encoding="utf-8")
    if args.release_notes:
        return args.release_notes
    return "Automated wheel upload from build_and_publish_wheels.py"


def _parse_args() -> argparse.Namespace:
    """Parse command line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Build wheel artifacts for provider (server) and consumer (agent), "
            "and optionally publish them to a GitHub release."
        )
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository in owner/name form (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--dist-root",
        default="dist",
        help="Artifact root directory (default: dist)",
    )
    parser.add_argument(
        "--provider-sbom-path",
        default=DEFAULT_PROVIDER_SBOM_PATH,
        help=(
            "Provider SBOM output path "
            f"(default: {DEFAULT_PROVIDER_SBOM_PATH})"
        ),
    )
    parser.add_argument(
        "--consumer-sbom-path",
        default=DEFAULT_CONSUMER_SBOM_PATH,
        help=(
            "Consumer SBOM output path "
            f"(default: {DEFAULT_CONSUMER_SBOM_PATH})"
        ),
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for builds (default: current interpreter)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish built wheels to a GitHub release",
    )
    parser.add_argument(
        "--tag",
        help="Release tag used when publishing (required with --publish)",
    )
    parser.add_argument(
        "--release-name",
        help="Release name/title (defaults to tag)",
    )
    parser.add_argument(
        "--release-notes",
        default="",
        help="Release notes text for new release creation",
    )
    parser.add_argument(
        "--release-notes-file",
        help="Path to markdown/text file used as release notes body",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Create the release as draft when publishing",
    )
    parser.add_argument(
        "--prerelease",
        action="store_true",
        help="Mark the release as prerelease when publishing",
    )
    parser.add_argument(
        "--github-token",
        default="",
        help="GitHub token (default: env GITHUB_TOKEN or GH_TOKEN)",
    )
    args = parser.parse_args()

    if args.publish and not args.tag:
        parser.error("--tag is required when --publish is provided")
    if args.release_notes and args.release_notes_file:
        parser.error("use either --release-notes or --release-notes-file, not both")
    return args


def main() -> int:
    """Entrypoint."""
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dist_root = (repo_root / args.dist_root).resolve()
    provider_dist = dist_root / "provider"
    consumer_dist = dist_root / "consumer"

    _ensure_python_build(repo_root, args.python)
    provider_wheel = _build_component_wheel(
        repo_root=repo_root,
        python_exe=args.python,
        component_dir="provider",
        out_dir=provider_dist,
    )
    consumer_wheel = _build_component_wheel(
        repo_root=repo_root,
        python_exe=args.python,
        component_dir="consumer",
        out_dir=consumer_dist,
    )
    provider_sbom_path = _build_cyclonedx_sbom(
        repo=args.repo,
        artifact=provider_wheel,
        sbom_path=(repo_root / args.provider_sbom_path).resolve(),
        root_component_name="fluent-opamp-provider-deployable-artifact",
    )
    consumer_sbom_path = _build_cyclonedx_sbom(
        repo=args.repo,
        artifact=consumer_wheel,
        sbom_path=(repo_root / args.consumer_sbom_path).resolve(),
        root_component_name="fluent-opamp-consumer-deployable-artifact",
    )

    print("Build complete.")
    print(f"Provider wheel: {provider_wheel}")
    print(f"Consumer wheel: {consumer_wheel}")
    print(f"Provider SBOM: {provider_sbom_path}")
    print(f"Consumer SBOM: {consumer_sbom_path}")

    if not args.publish:
        print("Publish skipped (use --publish to upload to GitHub release assets).")
        return 0

    token = (
        args.github_token.strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
        or os.environ.get("GH_TOKEN", "").strip()
    )
    if not token:
        raise RuntimeError(
            "GitHub token is required for publish; use --github-token or set GITHUB_TOKEN/GH_TOKEN"
        )

    notes = _load_release_notes(args)
    _publish_wheels(
        repo=args.repo,
        tag=args.tag,
        release_name=args.release_name,
        release_notes=notes,
        draft=args.draft,
        prerelease=args.prerelease,
        token=token,
        artifact_paths=[
            provider_wheel,
            consumer_wheel,
            provider_sbom_path,
            consumer_sbom_path,
        ],
    )
    print("Publish complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
