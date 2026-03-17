# OpAMP Provider

Quart-based OpAMP server skeleton and web UI.

## Configuration

The provider reads `opamp.json` from the repo `config/` folder by default. You can override the
config file location with the `OPAMP_CONFIG_PATH` environment variable.

Example `opamp.json`:

```json
{
  "provider": {
    "server_capabilities": ["AcceptsStatus"],
    "delayed_comms_seconds": 60,
    "significant_comms_seconds": 300,
    "webui_port": 8080
  }
}
```

### Fields

- `provider.server_capabilities` (array of strings, required)
  Capabilities list. Names must match `ServerCapabilities` enum values in `shared/opamp_config.py`.
- `provider.delayed_comms_seconds` (integer, optional, default `60`)
  Time in seconds before a client is marked delayed (amber).
- `provider.significant_comms_seconds` (integer, optional, default `300`)
  Time in seconds before a client is marked significantly delayed (red).
- `provider.webui_port` (integer, optional, default `8080`)
  Port for the provider UI and HTTP server.

## Run scripts

Helper scripts live in `scripts/` at the repo root:

- Windows CMD: `scripts/run_opamp_server.cmd`
- Bash: `scripts/run_opamp_server.sh`

Both scripts write logs to `logs/opamp_server.log` and rotate it on startup.

## Quickstart (manual)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Generate protobufs (optional; auto-generated on first import):

```bash
python -m opamp_provider.proto.ensure
```

Run the server:

```bash
quart --app opamp_provider.app:app run --port 4320
```

## Web UI

- Console: `http://localhost:8080/ui`
- Help: `http://localhost:8080/help`

The UI includes a shutdown button that prompts for confirmation and calls the shutdown API.

## Shutdown API

```
POST /api/shutdown
{"confirm": true}
```
