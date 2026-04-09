#!/usr/bin/env python3
"""Ensure provider TLS configuration exists in an OpAMP config JSON file."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

DEFAULT_TRUST_ANCHOR_MODE = "none"
UTF8_ENCODING = "utf-8"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Ensure provider.tls config exists with cert/key/trust settings."
    )
    parser.add_argument("--config-file", required=True, help="Path to opamp config JSON file.")
    parser.add_argument("--cert-file", required=True, help="TLS certificate path.")
    parser.add_argument("--key-file", required=True, help="TLS private key path.")
    parser.add_argument(
        "--trust-anchor-mode",
        default=DEFAULT_TRUST_ANCHOR_MODE,
        choices=["none", "partial_chain", "full_chain_to_root"],
        help=f"Provider TLS trust mode (default: {DEFAULT_TRUST_ANCHOR_MODE}).",
    )
    return parser.parse_args()


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    """Load config JSON from disk, returning an empty object when missing."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding=UTF8_ENCODING).strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a JSON object: {path}")
    return data


def ensure_provider_tls_config(
    *,
    config_file: pathlib.Path,
    cert_file: pathlib.Path,
    key_file: pathlib.Path,
    trust_anchor_mode: str,
) -> None:
    """Write provider.tls settings into the target config file."""
    data = _load_json(config_file)
    provider = data.get("provider")
    if not isinstance(provider, dict):
        provider = {}
    tls = provider.get("tls")
    if not isinstance(tls, dict):
        tls = {}

    tls["cert_file"] = str(cert_file)
    tls["key_file"] = str(key_file)
    tls["trust_anchor_mode"] = trust_anchor_mode
    provider["tls"] = tls
    data["provider"] = provider

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        f"{json.dumps(data, indent=2)}\n",
        encoding=UTF8_ENCODING,
    )


def main() -> int:
    """Program entrypoint."""
    args = parse_args()
    config_file = pathlib.Path(args.config_file)
    cert_file = pathlib.Path(args.cert_file)
    key_file = pathlib.Path(args.key_file)

    ensure_provider_tls_config(
        config_file=config_file,
        cert_file=cert_file,
        key_file=key_file,
        trust_anchor_mode=args.trust_anchor_mode,
    )

    print(f"[OK] Updated provider TLS config in {config_file}")
    print(f"      cert_file: {cert_file}")
    print(f"      key_file : {key_file}")
    print(f"      trust    : {args.trust_anchor_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
