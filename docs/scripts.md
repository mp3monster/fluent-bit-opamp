# Scripts Reference

This table lists the helper scripts and their platform-specific names.

| Purpose | Linux / macOS | Windows |
| --- | --- | --- |
| Run the OpAMP server (provider) | `scripts/run_opamp_server.sh` | `scripts/run_opamp_server.cmd` |
| Run the OpAMP supervisor (consumer) | `scripts/run_fluentbit_supervisor.sh` | `scripts/run_fluentbit_supervisor.cmd` |
| Run the OpAMP supervisor (Fluentd consumer) | `scripts/run_fluentd_supervisor.sh` | `scripts/run_fluentd_supervisor.cmd` |
| Run all supervisor launch scripts (each in a new window) | `scripts/run_all_supervisors.sh` | `scripts/run_all_supervisors.cmd` |
| Start Fluentd directly | `scripts/start_fluentd.sh` | `scripts/start_fluentd.cmd` |
| Configure local Keycloak for JWT auth testing | `scripts/configure_keycloak.sh` | `scripts/configure_keycloak.cmd` / `scripts/configure_keycloak.ps1` |
| Generate self-signed TLS cert/key for local HTTPS testing | `scripts/generate_self_signed_tls_cert.py` | `scripts\generate_self_signed_tls_cert.py` |
| Ensure `provider.tls` settings exist in config JSON | `scripts/ensure_provider_tls_config.py` | `scripts\ensure_provider_tls_config.py` |
| Render Mermaid `.mmd` to PNG (local wrapper) | `scripts/render_mermaid_png.sh` | n/a |
| Request server shutdown via API | `scripts/shutdown_opamp_server.sh` | `scripts/shutdown_opamp_server.cmd` |
| Build deployable Python artifacts (provider + consumer) | `scripts/build_artifacts.sh` | `scripts/build_artifacts.cmd` |
| Build wheel artifacts and optionally publish to GitHub release assets | `scripts/build_and_publish_wheels.py` | `scripts\build_and_publish_wheels.py` |

`configure_keycloak` supports a container readiness-only mode:

- Linux / macOS: `./scripts/configure_keycloak.sh --ready-only`
- Windows cmd: `scripts\configure_keycloak.cmd --ready-only`
- Windows PowerShell: `.\scripts\configure_keycloak.ps1 -ReadyOnly`
- Optional runtime override: `CONTAINER_RUNTIME=docker|podman`

## Provider HTTPS bootstrap

- `run_opamp_server` accepts `--https` on Linux and Windows launchers.
- When `--https` is supplied, the launcher:
  1. Generates a self-signed cert/key in `certs/provider-server.pem` and `certs/provider-server-key.pem`.
  2. Updates the active OpAMP config file (`OPAMP_CONFIG_PATH` or `config/opamp.json`) to include:
     - `provider.tls.cert_file`
     - `provider.tls.key_file`
     - `provider.tls.trust_anchor_mode` (`none`)
     - `provider.tls.enabled` defaults to `true` when omitted.
- The wrapper consumes `--https` itself and does not pass it through to `opamp_provider.server`.

## Supervisor config defaults

- `run_fluentbit_supervisor` resolves config in this order:
  `tests/opamp.json` -> `config/opamp.json`.
- `run_fluentd_supervisor` resolves config in this order:
  `consumer/opamp-fluentd.json` -> `tests/opamp.json` -> `config/opamp.json`.
- `run_fluentd_supervisor` and `start_fluentd` use `consumer/fluentd.conf`
  as the canonical Fluentd config path.

## Artifact build scripts

`build_artifacts` scripts generate both `sdist` and `wheel` packages for:

- `provider` -> `dist/provider/`
- `consumer` -> `dist/consumer/`

The scripts:

- activate `.venv` when present
- ensure the `build` package is installed
- clear old files in target artifact folders before building

Example:

```bash
./scripts/build_artifacts.sh
```

```cmd
scripts\build_artifacts.cmd
```

## Wheel Build + GitHub Publish

Use `build_and_publish_wheels.py` to generate wheels for both components:

- provider (server) wheel -> `dist/provider/*.whl`
- consumer (agent) wheel -> `dist/consumer/*.whl`
- provider deployable artifact SBOM (CycloneDX JSON) -> `dist/sbom/opamp_provider_deployable_artifacts.cyclonedx.json`
- consumer deployable artifact SBOM (CycloneDX JSON) -> `dist/sbom/opamp_consumer_deployable_artifacts.cyclonedx.json`

Build only:

```bash
python3 scripts/build_and_publish_wheels.py
```

Build and publish to GitHub release assets in `mp3monster/fluent-opamp`:

```bash
GITHUB_TOKEN=<token> python3 scripts/build_and_publish_wheels.py --publish --tag v0.1.0
```

Optional publish flags:

- `--repo owner/name` to override repository target
- `--release-name "..."` to set release title (defaults to tag)
- `--release-notes "..."` or `--release-notes-file <path>`
- `--draft`
- `--prerelease`
- `--provider-sbom-path <path>` to override provider SBOM output path
- `--consumer-sbom-path <path>` to override consumer SBOM output path

When `--publish` is used, both wheel files and both generated SBOM files are uploaded as release assets.

## Mermaid PNG rendering

Use the wrapper script after installing the Mermaid toolchain:

```bash
./scripts/render_mermaid_png.sh -i input.mmd -o output.png
```
