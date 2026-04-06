# OpAMP Provider

Quart-based OpAMP server skeleton and web UI.

## Configuration

The provider reads `opamp.json` from the repo `config/` folder by default. You can override the
config file location with the `OPAMP_CONFIG_PATH` environment variable.

Example `opamp.json`:

```json
{
  "provider": {
    "delayed_comms_seconds": 60,
    "significant_comms_seconds": 300,
    "webui_port": 8080,
    "minutes_keep_disconnected": 5,
    "retryAfterSeconds": 30,
    "client_event_history_size": 50,
    "log_level": "INFO",
    "default_heartbeat_frequency": 30,
    "human_in_loop_approval": false,
    "opamp-use-authorization": "none"
  }
}
```

### Fields

- `provider.delayed_comms_seconds` (integer, optional, default `60`)
  Time in seconds before a client is marked delayed (amber).
- `provider.significant_comms_seconds` (integer, optional, default `300`)
  Time in seconds before a client is marked significantly delayed (red).
- `provider.webui_port` (integer, optional, default `8080`)
  Port for the provider UI and HTTP server.
- `provider.minutes_keep_disconnected` (integer, optional, default `30`)
  Minutes to retain disconnected clients before purging. Disconnections are
  purged during UI refresh at half this interval.
- `provider.retryAfterSeconds` (integer, optional, default `30`)
  Retry delay (in seconds) used when the server responds with an unavailable error.
- `provider.client_event_history_size` (integer, optional, default `50`)
  Maximum number of retained client history events.
- `provider.log_level` (string, optional, default `INFO`)
  Provider log level name (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
  Level names are resolved via Python `logging`.
- `provider.default_heartbeat_frequency` (integer, optional, default `30`)
  Default heartbeat interval assigned to clients.
- `provider.human_in_loop_approval` (boolean, optional, default `false`)
  Requires unknown agents to be reviewed in the Pending Approval workflow before they are accepted.
  This setting can be updated in the UI via Global Settings -> ServerSettings.
- `provider.opamp-use-authorization` (string, optional, default `"none"`)
  OpAMP transport authorization mode for `/v1/opamp` HTTP and WebSocket:
  - `none`: no OpAMP bearer-token enforcement.
  - `config-token`: require `Authorization: Bearer <token>` and compare against `OPAMP_AUTH_STATIC_TOKEN`.
  - `idp`: require bearer token and validate as JWT using IdP settings (`OPAMP_AUTH_JWT_*`).
  This uses the same token/JWT settings as UI/API auth.

## Human-In-Loop Approval Workflow

When `provider.human_in_loop_approval` is enabled:

- Unknown agents are not added directly to the active client list.
- Their first payload is translated into a pending client record and stored in a pending-approval list.
- If payload-to-client transformation fails, the agent UID is added to a blocked list.
- Blocked agents are rejected on both HTTP and WebSocket transports.

The web UI displays a `Pending Approval` count in the top metadata bar.
Selecting it opens an approval dialog with:

- UID
- instance ID
- IP
- agent type/version
- host type
- accept/block decision per row (default `block`) and set-all controls

Submitting `OK` moves accepted agents into the active client list and adds blocked entries to the blocked list.

Related API endpoints:

- `GET /api/approvals/pending`
- `POST /api/approvals/pending`

## CLI Overrides

You can override selected config values at runtime:

- `--config-path` overrides the config file location.
- `--port` overrides `provider.webui_port`.
- `--log-level` overrides `provider.log_level`.

## Run scripts

Helper scripts live in `scripts/` at the repo root:

- Windows CMD: `scripts/run_opamp_server.cmd`
- Bash: `scripts/run_opamp_server.sh`

Both scripts write logs to `logs/opamp_server.log` and rotate it on startup.

## Running As A Service/Daemon

For Linux `systemd` and Windows service examples for provider and consumer deployments (and consumer launch permissions for Fluent Bit/Fluentd), see:

- `../docs/service_daemon_setup.md`

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

Installed CLI command:

```bash
opamp-provider --config-path ./config/opamp.json --port 4320
```

## Web UI

- Console: `http://localhost:8080/ui`
- Help: `http://localhost:8080/help`

The UI includes a shutdown button that prompts for confirmation and calls the shutdown API.

## Optional Bearer Authentication

Provider bearer auth is environment-controlled and defaults to disabled.

- `OPAMP_AUTH_MODE=disabled` (default) for local development/tests.
- `OPAMP_AUTH_MODE=static` with `OPAMP_AUTH_STATIC_TOKEN=<secret>`.
- `OPAMP_AUTH_MODE=jwt` with JWT settings (for example Keycloak issuer/audience).
- In `jwt` mode, browser app URLs (`/`, `/ui`, `/help`) redirect to IdP login when no bearer token is provided.

Protected path prefixes default to:

- `/tool`
- `/sse`
- `/messages`
- `/mcp`
- `/api`

See [docs/authentication.md](../docs/authentication.md) for full setup, Keycloak Docker script usage, and MCP token examples.

## Shutdown API

```
POST /api/shutdown
{"confirm": true}
```
