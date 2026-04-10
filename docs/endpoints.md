# OpAMP Provider Endpoints

This document lists the HTTP and WebSocket endpoints exposed by the provider.

## Bearer-Token Protection Scope

Bearer protection is controlled by provider config plus environment-backed secrets/JWT settings:

- `provider.ui-use-authorization` controls non-OpAMP routes (for example `/api`, `/tool`, `/ui`, `/help`, `/doc-set`, `/sse`, `/messages`, `/mcp`).
- `provider.opamp-use-authorization` controls OpAMP transport (`/v1/opamp` HTTP and WebSocket).
- Environment variables provide token/JWT validation settings:
  - OpAMP transport: `OPAMP_AUTH_*`
  - Non-OpAMP routes: `UI_AUTH_*`

## UI Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Redirect to the web UI (`/ui`). |
| GET | `/ui` | Main web UI page. |
| GET | `/help` | Help page. |
| GET | `/doc-set` | Redirect to latest docs URL configured in `provider.latest_docs_url`. |
| GET | `/create.ico` | UI favicon. |

## Tool Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/tool` | OpenAPI specification for `/tool` endpoints. |
| GET | `/tool/otelAgents` | List agents that are not disconnected. |
| GET | `/tool/commands` | List all commands (OpAMP-standard and custom). |

When `provider.ui-use-authorization` is set to `config-token` or `idp`, `/tool`
endpoints require an `Authorization: Bearer <token>` header.

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/clients` | List tracked clients (`pending_approval_total` included). |
| GET | `/api/clients/<client_id>` | Get one client record. |
| DELETE | `/api/clients/<client_id>` | Remove a client record. |
| GET | `/api/approvals/pending` | List pending-approval agents. |
| POST | `/api/approvals/pending` | Apply approve/block decisions for pending agents. |
| POST | `/api/clients/<client_id>/commands` | Queue command/custom command. |
| POST | `/api/clients/<client_id>/actions` | Set next actions for a client. |
| PUT | `/api/clients/<client_id>/heartbeat-frequency` | Set heartbeat frequency for one client. |
| POST | `/api/clients/<client_id>/identify` | Queue new instance UID for client. |
| POST | `/api/clients/<client_id>/config` | Set requested config for a client. |
| GET | `/api/commands/custom` | List custom command metadata for the UI. |
| GET | `/api/settings/comms` | Get communication threshold settings. |
| PUT | `/api/settings/comms` | Update communication threshold settings. |
| GET | `/api/settings/diagnostic` | Get diagnostic and state-persistence status metadata for UI feature-gating/health display. |
| POST | `/api/settings/state/save` | Force an immediate provider state snapshot save (when persistence is enabled). |
| GET | `/api/settings/client` | Get global client settings. |
| PUT | `/api/settings/client` | Update global client settings. |
| GET | `/api/help/global-settings` | Get shared help text for Global Settings labels/tooltips. |
| POST | `/api/shutdown` | Shutdown server (requires `{"confirm": true}`). |

## OpAMP Transport Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/v1/opamp` | OpAMP HTTP transport endpoint (AgentToServer/ServerToAgent). |
| WEBSOCKET | `/v1/opamp` | OpAMP WebSocket transport endpoint. |

Human-in-loop behavior notes:

- When `provider.human_in_loop_approval=true`, unknown agent UIDs are staged into pending approval and rejected until explicitly approved.
- Blocked agent UIDs are rejected for both HTTP and WebSocket traffic.
- `provider.opamp-use-authorization` controls `/v1/opamp` auth mode:
  - `none` (default): no OpAMP bearer-token enforcement.
  - `config-token`: compare bearer token to `OPAMP_AUTH_STATIC_TOKEN`.
  - `idp`: validate bearer JWT using `OPAMP_AUTH_JWT_*` settings.

Bearer protection notes:

- Both `POST /v1/opamp` and `WEBSOCKET /v1/opamp` are protected through `provider.opamp-use-authorization`.
- `config-token` mode validates against `OPAMP_AUTH_STATIC_TOKEN`.
- `idp` mode validates JWT using `OPAMP_AUTH_JWT_*`.

## MCP Transport Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/sse` | FastMCP SSE stream endpoint exposed through Quart (when `mcptool` + FastMCP are available). |
| POST | `/messages` | FastMCP SSE message endpoint paired with `/sse`. |
| POST/GET | `/mcp` | FastMCP Streamable HTTP endpoint (when enabled in transport configuration). |

When `provider.ui-use-authorization` is set to `config-token` or `idp`, MCP
transport endpoints (`/sse`, `/messages`, `/mcp`) require
`Authorization: Bearer <token>`.
