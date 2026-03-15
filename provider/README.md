# OpAMP Provider

Quart-based OpAMP server skeleton.

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

## Quickstart

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
