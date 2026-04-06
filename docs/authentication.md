# Provider Authentication

This project supports optional bearer-token authentication for provider endpoints that are typically used by MCP clients:

- `/tool`
- `/tool/*`
- `/sse`
- `/messages`
- `/mcp`
- `/mcp/*`
- `/api`
- `/api/*`

Authentication is controlled by environment variables so it can be switched off quickly for development and unit testing.

For production-facing deployments fronted by an API gateway, including internal-vs-external client profiles and route policy guidance, see:

- [docs/api_gateway_requirements.md](api_gateway_requirements.md)
- [TOFU Design for `/v1/opamp`](opamp_tofu_design.md)

## Modes

Set `OPAMP_AUTH_MODE` to one of:

- `disabled` (default): no auth checks are applied.
- `static`: compare bearer token against a configured static secret.
- `jwt`: validate JWT bearer tokens using JWKS (for example Keycloak).

## Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPAMP_AUTH_MODE` | Auth mode (`disabled`, `static`, `jwt`) | `disabled` |
| `OPAMP_AUTH_PROTECTED_PATH_PREFIXES` | Comma-separated protected path prefixes | `/tool,/sse,/messages,/mcp,/api` |
| `OPAMP_AUTH_STATIC_TOKEN` | Shared secret token used in `static` mode | unset |
| `OPAMP_AUTH_JWT_ISSUER` | JWT issuer URL (for claim validation; also used to derive JWKS URL) | unset |
| `OPAMP_AUTH_JWT_AUDIENCE` | Required `aud` claim in JWT mode | unset |
| `OPAMP_AUTH_JWT_JWKS_URL` | Explicit JWKS URL (overrides issuer-derived JWKS endpoint) | derived from issuer |
| `OPAMP_AUTH_JWT_LEEWAY_SECONDS` | JWT time-claim leeway | `30` |
| `OPAMP_AUTH_IDP_LOGIN_URL` | Optional explicit IdP login URL for browser redirects (`/`, `/ui`, `/help`) in JWT mode | derived from issuer |
| `OPAMP_AUTH_IDP_CLIENT_ID` | Optional client id used for derived IdP login URL (fallback: `OPAMP_AUTH_JWT_AUDIENCE`) | unset |

## Recommended Protected Prefixes (Gateway-Aligned)

When running behind an API gateway, align provider-side checks to protect all sensitive routes by default:

```bash
export OPAMP_AUTH_PROTECTED_PATH_PREFIXES='/tool,/sse,/messages,/mcp,/api,/v1/opamp'
```

This keeps provider checks consistent with gateway route protection for both operator and agent traffic.

## OpAMP Endpoint Authorization Mode

Provider config key `provider.opamp-use-authorization` controls `/v1/opamp` authorization independently of path-prefix protection:

- `none` (default): no bearer validation on OpAMP transport.
- `config-token`: require `Authorization: Bearer <token>` and compare with `OPAMP_AUTH_STATIC_TOKEN`.
- `idp`: require bearer token and validate JWT using `OPAMP_AUTH_JWT_*`.

This intentionally reuses the same static token / IdP JWT settings as UI/API authentication.

## Development: Disable Auth

For local endpoint development and unit tests:

```bash
export OPAMP_AUTH_MODE=disabled
```

## Static Token Scenario

Use static mode for lightweight dev/staging auth without an IdP.

```bash
export OPAMP_AUTH_MODE=static
export OPAMP_AUTH_STATIC_TOKEN='replace-with-long-random-token'
```

Example request:

```bash
curl -H "Authorization: Bearer ${OPAMP_AUTH_STATIC_TOKEN}" http://127.0.0.1:8080/tool
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
export OPAMP_AUTH_MODE=jwt
export OPAMP_AUTH_JWT_ISSUER='http://127.0.0.1:8081/realms/opamp'
export OPAMP_AUTH_JWT_AUDIENCE='opamp-mcp'
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

If auth is enabled and no valid bearer token is provided, provider returns `401`.

## Browser App URL Redirects (JWT/IdP Mode)

When `OPAMP_AUTH_MODE=jwt`, requests to `/`, `/ui`, and `/help` without a bearer token are redirected to the IdP login URL.

- If `OPAMP_AUTH_IDP_LOGIN_URL` is set, that URL is used directly.
- Otherwise, provider derives Keycloak-compatible login URL from `OPAMP_AUTH_JWT_ISSUER` and client id settings.

## Authorization Rejection Logging

Any rejected authorization attempt is logged at warning level with:

- auth mode
- request method
- request path
- source address
- rejection reason

This is intended for operational visibility and troubleshooting.
