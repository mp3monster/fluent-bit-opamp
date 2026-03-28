# OpAMP Provider Endpoints

This document lists the HTTP and WebSocket endpoints exposed by the provider.

## Bearer-Token Protection Scope

Bearer protection is prefix-based and controlled by:

- `OPAMP_AUTH_MODE` (`disabled`, `static`, `jwt`)
- `OPAMP_AUTH_PROTECTED_PATH_PREFIXES` (comma-separated path prefixes)

Default protected prefixes are:

- `/tool`
- `/sse`
- `/messages`
- `/mcp`

Important behavior details:

- Any HTTP endpoint can be protected by adding its prefix to
  `OPAMP_AUTH_PROTECTED_PATH_PREFIXES` (for example `/api` or `/v1/opamp`).
- Prefix matching applies to the exact path and descendants.
  Example: protecting `/tool` also protects `/tool/commands`.
- OpAMP HTTP transport (`POST /v1/opamp`) can be protected with a prefix entry.
- OpAMP WebSocket transport (`WEBSOCKET /v1/opamp`) is not currently covered by the
  HTTP bearer-check hook.

## UI Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Redirect to the web UI (`/ui`). |
| GET | `/ui` | Main web UI page. |
| GET | `/help` | Help page. |
| GET | `/create.ico` | UI favicon. |

## Tool Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/tool` | OpenAPI specification for `/tool` endpoints. |
| GET | `/tool/otelAgents` | List agents that are not disconnected. |
| GET | `/tool/commands` | List all commands (OpAMP-standard and custom). |

When bearer auth is enabled (`OPAMP_AUTH_MODE=static` or `jwt`) and `/tool` is in
`OPAMP_AUTH_PROTECTED_PATH_PREFIXES` (default), `/tool` endpoints require an
`Authorization: Bearer <token>` header.

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/clients` | List tracked clients. |
| GET | `/api/clients/<client_id>` | Get one client record. |
| DELETE | `/api/clients/<client_id>` | Remove a client record. |
| POST | `/api/clients/<client_id>/commands` | Queue command/custom command. |
| POST | `/api/clients/<client_id>/actions` | Set next actions for a client. |
| PUT | `/api/clients/<client_id>/heartbeat-frequency` | Set heartbeat frequency for one client. |
| POST | `/api/clients/<client_id>/identify` | Queue new instance UID for client. |
| POST | `/api/clients/<client_id>/config` | Set requested config for a client. |
| GET | `/api/commands/custom` | List custom command metadata for the UI. |
| GET | `/api/settings/comms` | Get communication threshold settings. |
| PUT | `/api/settings/comms` | Update communication threshold settings. |
| GET | `/api/settings/client` | Get global client settings. |
| PUT | `/api/settings/client` | Update global client settings. |
| GET | `/api/help/global-settings` | Get shared help text for Global Settings labels/tooltips. |
| POST | `/api/shutdown` | Shutdown server (requires `{"confirm": true}`). |

## OpAMP Transport Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/v1/opamp` | OpAMP HTTP transport endpoint (AgentToServer/ServerToAgent). |
| WEBSOCKET | `/v1/opamp` | OpAMP WebSocket transport endpoint. |

Bearer protection notes:

- `POST /v1/opamp` is protectable by adding `/v1/opamp` to
  `OPAMP_AUTH_PROTECTED_PATH_PREFIXES`.
- `WEBSOCKET /v1/opamp` is not currently bearer-protected by that setting.

## MCP Transport Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/sse` | FastMCP SSE stream endpoint exposed through Quart (when `mcptool` + FastMCP are available). |
| POST | `/messages` | FastMCP SSE message endpoint paired with `/sse`. |
| POST/GET | `/mcp` | FastMCP Streamable HTTP endpoint (when enabled in transport configuration). |

When bearer auth is enabled and default MCP prefixes are protected, MCP transport
endpoints (`/sse`, `/messages`, `/mcp`) require `Authorization: Bearer <token>`.
