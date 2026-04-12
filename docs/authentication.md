# Provider Authentication

This project supports optional bearer-token authentication for provider endpoints:

- `/tool`
- `/tool/*`
- `/sse`
- `/messages`
- `/mcp`
- `/mcp/*`
- `/api`
- `/api/*`
- `/ui`
- `/help`
- `/doc-set`
- `/v1/opamp`

Authentication mode is controlled by provider config keys in `opamp.json`. Static token and JWT
validation settings are provided by environment variables.

For production-facing deployments fronted by an API gateway, including internal-vs-external client profiles and route policy guidance, see:

- [docs/api_gateway_requirements.md](api_gateway_requirements.md)

## Modes

Both provider auth config keys use the same values:

- `none` (default): no bearer checks.
- `config-token`: compare bearer token against a configured static secret.
- `idp`: validate JWT bearer tokens using JWKS (for example Keycloak).

## OpAMP Endpoint Authorization Mode

Provider config key `provider.opamp-use-authorization` controls `/v1/opamp` HTTP and WebSocket:

- `none` (default): no bearer validation on OpAMP transport.
- `config-token`: require `Authorization: Bearer <token>` and compare with `OPAMP_AUTH_STATIC_TOKEN`.
- `idp`: require bearer token and validate JWT using `OPAMP_AUTH_JWT_*`.

## UI / API / MCP Authorization Mode

Provider config key `provider.ui-use-authorization` controls non-OpAMP HTTP and MCP transport
routes (including websocket scopes), for example `/tool`, `/sse`, `/messages`, `/mcp`, `/api`,
`/ui`, `/help`, `/doc-set`:

- `none` (default): no bearer validation.
- `config-token`: require `Authorization: Bearer <token>` and compare with `UI_AUTH_STATIC_TOKEN`.
- `idp`: require bearer token and validate JWT using `UI_AUTH_JWT_*`.

## Environment Variables

OpAMP transport env vars:

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPAMP_AUTH_STATIC_TOKEN` | Shared secret token used when `provider.opamp-use-authorization=config-token` | unset |
| `OPAMP_AUTH_JWT_ISSUER` | JWT issuer URL (claim validation; also used to derive JWKS URL) | unset |
| `OPAMP_AUTH_JWT_AUDIENCE` | Required `aud` claim in OpAMP `idp` mode | unset |
| `OPAMP_AUTH_JWT_JWKS_URL` | Explicit JWKS URL (overrides issuer-derived JWKS endpoint) | derived from issuer |
| `OPAMP_AUTH_JWT_LEEWAY_SECONDS` | JWT time-claim leeway | `30` |
| `OPAMP_AUTH_IDP_LOGIN_URL` | Optional explicit IdP login URL | derived from issuer |
| `OPAMP_AUTH_IDP_CLIENT_ID` | Optional client id for derived IdP login URL | unset |

UI/API/MCP env vars:

| Variable | Purpose | Default |
| --- | --- | --- |
| `UI_AUTH_STATIC_TOKEN` | Shared secret token used when `provider.ui-use-authorization=config-token` | unset |
| `UI_AUTH_JWT_ISSUER` | JWT issuer URL (claim validation; also used to derive JWKS URL) | unset |
| `UI_AUTH_JWT_AUDIENCE` | Required `aud` claim in non-OpAMP `idp` mode | unset |
| `UI_AUTH_JWT_JWKS_URL` | Explicit JWKS URL (overrides issuer-derived JWKS endpoint) | derived from issuer |
| `UI_AUTH_JWT_LEEWAY_SECONDS` | JWT time-claim leeway | `30` |
| `UI_AUTH_IDP_LOGIN_URL` | Optional explicit IdP login URL | derived from issuer |
| `UI_AUTH_IDP_CLIENT_ID` | Optional client id for derived IdP login URL | unset |

## Development: Disable Auth

For local endpoint development and unit tests:

```json
{
  "provider": {
    "opamp-use-authorization": "none",
    "ui-use-authorization": "none"
  }
}
```

## Static Token Scenario

Use static mode for lightweight dev/staging auth without an IdP.

```bash
# /v1/opamp endpoints
export OPAMP_AUTH_STATIC_TOKEN='replace-with-long-random-token'
# non-OpAMP HTTP + MCP endpoints
export UI_AUTH_STATIC_TOKEN='replace-with-long-random-token'
```

Example request:

```bash
curl -H "Authorization: Bearer ${UI_AUTH_STATIC_TOKEN}" http://127.0.0.1:8080/tool
```

## Keycloak JWT Scenario (Docker)

Use the helper script to create/configure a local Keycloak container, realm, client, and test user:

```bash
./scripts/configure_keycloak.sh
```

Windows (cmd):

```cmd
scripts\configure_keycloak.cmd
```

Windows (PowerShell):

```powershell
.\scripts\configure_keycloak.ps1
```

Prepare container only (no realm/client/user changes):

```bash
./scripts/configure_keycloak.sh --ready-only
```

```cmd
scripts\configure_keycloak.cmd --ready-only
```

```powershell
.\scripts\configure_keycloak.ps1 -ReadyOnly
```

Force Podman runtime:

```bash
CONTAINER_RUNTIME=podman ./scripts/configure_keycloak.sh --ready-only
```

```cmd
set CONTAINER_RUNTIME=podman && scripts\configure_keycloak.cmd --ready-only
```

```powershell
$env:CONTAINER_RUNTIME='podman'; .\scripts\configure_keycloak.ps1 -ReadyOnly
```

The script prints:

- issuer URL
- JWKS URL
- client ID/secret
- user credentials
- sample token request

Configure provider JWT auth:

```bash
# /v1/opamp endpoints
export OPAMP_AUTH_JWT_ISSUER='http://127.0.0.1:8081/realms/opamp'
export OPAMP_AUTH_JWT_AUDIENCE='opamp-mcp'
# non-OpAMP HTTP + MCP endpoints
export UI_AUTH_JWT_ISSUER='http://127.0.0.1:8081/realms/opamp'
export UI_AUTH_JWT_AUDIENCE='opamp-ui'
```

Request a bearer token from Keycloak:

```bash
TOKEN="$(
  curl -s -X POST \
    http://127.0.0.1:8081/realms/opamp/protocol/openid-connect/token \
    -d grant_type=password \
    -d client_id=opamp-mcp \
    -d client_secret=opamp-mcp-secret \
    -d username=opamp-user \
    -d password=opamp-password \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)"
```

Use the token:

```bash
curl -H "Authorization: Bearer ${TOKEN}" http://127.0.0.1:8080/tool/commands
```

## MCP Setup with Bearer Token

When your MCP client supports custom headers, pass:

`Authorization: Bearer <token>`

at connection/request time for `/sse`, `/messages`, or `/mcp` transports.

For MCP client setup script usage and command-line parameters (Claude/Codex/canonical),
see `../mcp/README.md`.

If auth is enabled and no valid bearer token is provided, provider returns `401`.

## Authorization Rejection Logging

Any rejected authorization attempt is logged at warning level with:

- auth mode
- request method
- request path
- source address
- rejection reason

This is intended for operational visibility and troubleshooting.
