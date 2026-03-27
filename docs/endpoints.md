# OpAMP Provider Endpoints

This document lists the HTTP and WebSocket endpoints exposed by the provider.

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

## MCP Transport Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/sse` | FastMCP SSE stream endpoint exposed through Quart (when `mcptool` + FastMCP are available). |
| POST | `/messages` | FastMCP SSE message endpoint paired with `/sse`. |
