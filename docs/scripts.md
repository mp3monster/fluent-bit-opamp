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
| Render Mermaid `.mmd` to PNG (local wrapper) | `scripts/render_mermaid_png.sh` | n/a |
| Request server shutdown via API | `scripts/shutdown_opamp_server.sh` | `scripts/shutdown_opamp_server.cmd` |
| Build deployable Python artifacts (provider + consumer) | `scripts/build_artifacts.sh` | `scripts/build_artifacts.cmd` |

`configure_keycloak` supports a container readiness-only mode:

- Linux / macOS: `./scripts/configure_keycloak.sh --ready-only`
- Windows cmd: `scripts\configure_keycloak.cmd --ready-only`
- Windows PowerShell: `.\scripts\configure_keycloak.ps1 -ReadyOnly`
- Optional runtime override: `CONTAINER_RUNTIME=docker|podman`

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

## Mermaid PNG rendering

Use the wrapper script after installing the Mermaid toolchain:

```bash
./scripts/render_mermaid_png.sh -i input.mmd -o output.png
```
