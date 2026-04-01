# OpAMP Provider + Consumer

This repo contains a small OpAMP provider (server) and consumer (client) setup. You can run them independently or together.

## Prerequisites

- Python 3.10+ installed
- `pip` available

## Quick start (provider only)

### PowerShell (Windows)

```powershell
cd D:\dev\opamp
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r provider\requirements.txt
scripts\run_opamp_server.cmd
```

### Bash (Linux/macOS)

```bash
cd /path/to/opamp
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r provider/requirements.txt
./scripts/run_opamp_server.sh
```

The provider will start on the configured `webui_port` (default `8080`) unless you pass `--port`.

## Quick start (consumer only)

### PowerShell (Windows)

```powershell
cd D:\dev\opamp
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r consumer\requirements.txt
python -m opamp_consumer.fluentbit_client --config-path config\opamp.json
```

### Bash (Linux/macOS)

```bash
cd /path/to/opamp
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r consumer/requirements.txt
python3 -m opamp_consumer.fluentbit_client --config-path config/opamp.json
```

## Run provider + consumer together

### PowerShell (Windows)

```powershell
cd D:\dev\opamp
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r provider\requirements.txt
python -m pip install -r consumer\requirements.txt
scripts\run_opamp_server.cmd
```

In a new PowerShell window:

```powershell
cd D:\dev\opamp
.venv\Scripts\Activate.ps1
python -m opamp_consumer.fluentbit_client --config-path config\opamp.json
```

### Bash (Linux/macOS)

```bash
cd /path/to/opamp
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r provider/requirements.txt
python3 -m pip install -r consumer/requirements.txt
./scripts/run_opamp_server.sh
```

In a new shell:

```bash
cd /path/to/opamp
source .venv/bin/activate
python3 -m opamp_consumer.fluentbit_client --config-path config/opamp.json
```

## Notes

- Provider Web UI: http://localhost:8080/ui
- Help page: http://localhost:8080/help
- Optional bearer auth setup (disabled/static/jwt): see `docs/authentication.md`
- Running as a Linux daemon or Windows service (including consumer permissions to launch Fluent Bit/Fluentd): see `docs/service_daemon_setup.md`
- If you change `provider.webui_port` in `config/opamp.json`, the UI/HTTP port will follow it.
- For Windows CMD usage, the commands are similar but use `\.venv\Scripts\activate.bat` to activate the venv.
