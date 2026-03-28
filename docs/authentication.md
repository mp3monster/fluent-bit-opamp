# Provider Authentication

This project supports optional bearer-token authentication for provider endpoints that are typically used by MCP clients:

- `/tool`
- `/tool/*`
- `/sse`
- `/messages`
- `/mcp`
- `/mcp/*`

Authentication is controlled by environment variables so it can be switched off quickly for development and unit testing.

## Modes

Set `OPAMP_AUTH_MODE` to one of:

- `disabled` (default): no auth checks are applied.
- `static`: compare bearer token against a configured static secret.
- `jwt`: validate JWT bearer tokens using JWKS (for example Keycloak).

## Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPAMP_AUTH_MODE` | Auth mode (`disabled`, `static`, `jwt`) | `disabled` |
| `OPAMP_AUTH_PROTECTED_PATH_PREFIXES` | Comma-separated protected path prefixes | `/tool,/sse,/messages,/mcp` |
| `OPAMP_AUTH_STATIC_TOKEN` | Shared secret token used in `static` mode | unset |
| `OPAMP_AUTH_JWT_ISSUER` | JWT issuer URL (for claim validation; also used to derive JWKS URL) | unset |
| `OPAMP_AUTH_JWT_AUDIENCE` | Required `aud` claim in JWT mode | unset |
| `OPAMP_AUTH_JWT_JWKS_URL` | Explicit JWKS URL (overrides issuer-derived JWKS endpoint) | derived from issuer |
| `OPAMP_AUTH_JWT_LEEWAY_SECONDS` | JWT time-claim leeway | `30` |

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
.\scripts\configure_keycloak.cmd
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

## Authorization Rejection Logging

Any rejected authorization attempt is logged at warning level with:

- auth mode
- request method
- request path
- source address
- rejection reason

This is intended for operational visibility and troubleshooting.
