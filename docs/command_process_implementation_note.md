# Command Process Implementation Note

This note describes how command intents are accepted by the Provider API, queued in memory, transformed into OpAMP payloads, and marked as sent.

## Scope

- Provider API endpoint: `POST /api/clients/<client_id>/commands`
- In-memory queue model: `provider/src/opamp_provider/state.py`
- Payload construction and dispatch: `provider/src/opamp_provider/app.py`
- Command discovery/registry: `provider/src/opamp_provider/commands.py`
- Command object contract: `provider/src/opamp_provider/command_interface.py`
- Built-in command objects:
  - `provider/src/opamp_provider/command_restart_agent.py`
  - `provider/src/opamp_provider/chatop_command.py`
- UI trigger (restart button): `provider/src/opamp_provider/html/web_ui.html`

## API Contract

The commands endpoint accepts an array of key/value pairs:

```json
[
  { "key": "classifier", "value": "command" },
  { "key": "action", "value": "restart" }
]
```

Supported classifiers:

- `command`
- `custom`
- `custom_command`

Required keys:

- `classifier`
- `action`

Compatibility behavior:

- The endpoint still accepts legacy payloads such as `{ "command": "restart" }`.
- Legacy payloads are normalized to:
  - `classifier=command`
  - `action=<command value>`

## Queue And State Model

`CommandRecord` stores normalized intent data:

- `command` (currently mirrors `action` for compatibility/readability)
- `classifier`
- `action`
- `key_value_pairs`
- `received_at`
- `sent_at`

Queue behavior:

1. API validates classifier/action and shape.
2. Valid command intent is appended to `ClientRecord.commands`.
3. Next poll from the client reads the first unsent command via `next_pending_command(...)`.
4. After a command/custom payload is emitted, the record is marked sent with `mark_command_sent(...)`.

## Startup Discovery And Registry

At provider startup (module import time), `opamp_provider.commands` scans command modules and discovers all concrete `CommandObjectInterface` implementations.

Discovery outputs:

- Command registry keyed by `(classifier, operation)` for factory creation.
- Capability map keyed by `(classifier, operation)` for reverse-FQDN lookup.
- Custom capability list derived from discovered command objects.

Helper APIs:

- `get_registered_command_keys()`
- `get_registered_command_fqdns()`
- `get_custom_capabilities_list()`
- `get_command_fqdn(classifier=..., operation=...)`
- `command_object_factory(classifier=..., operation=..., key_values=...)`

Capability filtering behavior:

- If a command object returns `None` for `get_capability_fqdn()`, it is excluded from the custom capabilities list.
- `RestartAgent` intentionally returns `None` because restart is a default OpAMP command feature, not a custom capability.

Any duplicate `(classifier, operation)` registration raises an error at startup.

## Classifier/Action Dispatch

Dispatch happens in `app.py` via a mapping from `(classifier, action)` to builder methods.

Current mapping:

- `("command", "restart")` -> `_build_restart_command(...)`
- `("custom", "chatopcommand")` -> `_build_custom_command_payload(...)`
- `("custom_command", "*")` -> `_build_custom_command_payload(...)`

If no mapping exists for the submitted classifier/action, the API rejects it with `400`.

## Payload Construction

### Restart Command

`_build_restart_command(...)` constructs `ServerToAgent.command` and sets:

- `command.type = CommandType_Restart`

This creates a `ServerToAgentCommand` payload for restart.

### Custom Command

`_build_custom_command_payload(...)` constructs `ServerToAgent.custom_message`.

For `classifier=custom` and `action=chatopcommand`, the server builds a `ChatOpCommand` object via the command factory and uses `to_custom_message()`.

`ChatOpCommand` payload behavior:

- `capability` is fixed to reverse-FQDN:
  - `org.mp3monster.opamp_provider.chatopcommand`
- `type` is fixed to:
  - `by REST Call`
- `data` is set to UTF-8 bytes of the full key/value dictionary JSON.

For generic `custom_command` payloads, additional optional key/value pairs can be supplied:

- `capability`
- `type`
- `data`

Defaults:

- `capability` defaults to `custom_command`
- `type` defaults to the submitted `action`
- `data` defaults to empty bytes when omitted

## Send Flow

For both HTTP and WebSocket OpAMP paths:

1. Server resolves pending command intent.
2. `_apply_command_intent(...)` runs classifier/action dispatch.
3. Response is returned to the client.
4. If response has `command` or `custom_message`, the queued record is marked sent.

## Debug Logging

Debug logging exists at payload build points:

- Created `ServerToAgent.command` payload
- Created `ServerToAgent.custom_message` payload
- Dispatch summary (`classifier`, `action`, `has_command`, `has_custom_message`)

Enable DEBUG logging in the provider runtime to see these entries.
