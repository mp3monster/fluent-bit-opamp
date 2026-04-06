# TOFU Design for `/v1/opamp` Endpoint

This document describes how to add Trust On First Use (TOFU) support to the OpAMP transport endpoint without changing current runtime behavior yet.

Current status:

- No code changes are proposed here.
- `/v1/opamp` behavior remains unchanged.
- This is a design and implementation plan only.

## Goal

Allow a client to bootstrap trust on first contact, then require a bearer token for subsequent `/v1/opamp` requests.

This is intended for environments where:

- full PKI enrollment is not available at first startup, and
- stronger controls than "open endpoint" are needed after bootstrap.

## Non-goals

- TOFU is not equivalent to mutual TLS or pre-provisioned identity.
- TOFU does not protect against an active attacker during first contact.
- This design does not replace existing `/tool`, `/mcp`, `/sse`, `/messages` bearer controls.

## Proposed TOFU Model

1. First contact:
- Unknown client (by `instance_uid`) sends `AgentToServer` to `/v1/opamp` with no bearer token.
- Server accepts once and mints a per-client bearer token.
- Server returns the token via `ServerToAgent.connection_settings.opamp.headers` as `Authorization: Bearer <token>`.

2. Steady state:
- Client stores token and includes it on all future `/v1/opamp` HTTP and WebSocket requests.
- Server validates token against the stored hash for that `instance_uid`.

3. Recovery/rotation:
- Server supports token reset per client (or global), forcing re-bootstrap.
- Server can queue `ReportFullState` when trust is reset or sequence checks fail.

## Why this fits current codebase

- Provider already builds `connection_settings.opamp` payloads in `_build_change_connections` and can include headers there.
- Consumer already receives `connection_settings` but currently only logs it; this is the main gap to close.
- Existing bearer-auth patterns and rejection logging can be reused for consistency.

## Required Provider Changes (planned)

## 1. Add TOFU state model

Add trust fields to client state (for example `ClientRecord`):

- `tofu_enabled: bool`
- `tofu_token_hash: str | None`
- `tofu_token_issued_at: datetime | None`
- `tofu_last_validated_at: datetime | None`
- `tofu_bootstrap_remote_addr: str | None`
- `tofu_failed_auth_count: int`

Notes:

- Store token hash only (never token plaintext).
- Use a strong random token (`secrets.token_urlsafe(48)` or equivalent).
- Hash with keyed HMAC (server-side secret/pepper) to avoid plain hash replay risks.

## 2. Implement TOFU verifier for `/v1/opamp`

Implement endpoint-specific checks (not global `before_request`) because TOFU needs `instance_uid` from protobuf payload:

- HTTP path: in `opamp_http`, parse protobuf, evaluate TOFU before `STORE.upsert_from_agent_msg`.
- WebSocket path: in `opamp_websocket`, evaluate on first decoded message before client update.

Decision outcomes:

- Unknown client + no token: allow bootstrap, mint token.
- Known client + valid token: allow.
- Known client + missing/invalid token: reject and log.

## 3. Return bootstrap token through OpAMP connection settings

When token is minted or rotated, include:

- `response.connection_settings.opamp.headers["Authorization"] = "Bearer <token>"`

Also include heartbeat settings already being set in `_build_change_connections`.

## 4. Add config flags

Recommended provider config/env:

- `opamp_tofu_enabled` (default `false`)
- `opamp_tofu_require_after_bootstrap` (default `true`)
- `opamp_tofu_persist_state` (default `false` for dev, `true` for prod)
- `opamp_tofu_rotation_on_uid_change` (default `true`)

If persistence is enabled, store trust metadata in provider config/state storage so restarts do not invalidate trust unexpectedly.

## 5. Logging and audit

Log at warning/info with consistent fields:

- `client_id`
- `remote_addr`
- `outcome` (`bootstrap`, `validated`, `rejected_missing_token`, `rejected_mismatch`, `rotated`)
- `channel` (`HTTP`/`websocket`)

Any rejection should remain easy to detect operationally.

## Required Consumer Changes (planned)

## 1. Persist OpAMP auth headers from connection settings

In `handle_connection_settings`:

- Parse `connection_settings.opamp.headers`.
- Extract `Authorization` when present.
- Persist in runtime state (and optionally on disk, encrypted/OS keyring where available).

## 2. Send token on HTTP and WebSocket

- `send_http`: include `Authorization` header in `httpx` request.
- `send_websocket`: include auth header in WebSocket handshake (`additional_headers`/equivalent for `websockets.connect`).

## 3. Token lifecycle behavior

- On receiving a new token, replace old token.
- On auth failure, log clearly and optionally trigger re-bootstrap policy (configurable).

## Security Considerations

- TOFU first contact is vulnerable to MITM spoofing if transport is not protected.
- Prefer TLS even with TOFU.
- For production, combine TOFU with:
  - network ACLs,
  - TLS termination,
  - short token rotation windows,
  - alerting on trust resets.

## Interaction with existing provider logic

- `check_sequence_num` force-resync behavior remains valid and should be retained.
- Instance UID replacement (`issue unique id`) should trigger token rotation to avoid trust confusion.
- Rejected auth should not mutate client state.

## Test Plan

Provider tests:

- Unknown client first HTTP message bootstraps and returns token in `connection_settings.opamp.headers`.
- Second HTTP message with token succeeds.
- Missing/invalid token after bootstrap fails and logs rejection.
- Same sequence for WebSocket transport.
- UID rotation invalidates old token and issues new token.

Consumer tests:

- Client stores token received in connection settings.
- HTTP send includes bearer token after bootstrap.
- WebSocket send includes bearer token after bootstrap.
- Token replacement updates outbound auth behavior.

Integration tests:

- End-to-end bootstrap over HTTP.
- End-to-end bootstrap over WebSocket.
- Restart behavior with and without persisted TOFU state.

## Rollout Plan

1. Add TOFU code paths behind config flag, default off.
2. Add tests and docs.
3. Enable in dev only.
4. Enable in controlled staging.
5. Enable in production only with TLS and monitoring in place.

## Example Configuration (target)

```json
{
  "provider": {
    "opamp_tofu_enabled": true,
    "opamp_tofu_require_after_bootstrap": true,
    "opamp_tofu_persist_state": false,
    "opamp_tofu_rotation_on_uid_change": true
  }
}
```

## Summary

TOFU for `/v1/opamp` can be added with minimal protocol disruption by issuing per-client bearer tokens through OpAMP connection settings on first contact, then enforcing them on subsequent HTTP/WebSocket traffic. This keeps development flexibility while significantly improving post-bootstrap endpoint protection.
