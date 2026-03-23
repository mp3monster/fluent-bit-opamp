# Command Process Implementation Note

This note describes how command intents are accepted by the Provider API, queued in memory, transformed into OpAMP payloads, and marked as sent.

## Scope

- Provider API endpoint: `POST /api/clients/<client_id>/commands`
- Provider custom command metadata endpoint: `GET /api/commands/custom`
- In-memory queue model: `provider/src/opamp_provider/state.py`
- Payload construction and dispatch: `provider/src/opamp_provider/app.py`
- Command discovery/registry: `provider/src/opamp_provider/commands.py`
- Command object contract: `provider/src/opamp_provider/command_interface.py`
- Built-in command objects:
  - `provider/src/opamp_provider/command_restart_agent.py`
  - `provider/src/opamp_provider/chatop_command.py`
  - `provider/src/opamp_provider/command_shutdown_agent.py`
  - `provider/src/opamp_provider/command_nullcommand.py`
- UI trigger/selection (restart + custom command panel): `provider/src/opamp_provider/html/web_ui.html`

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
- Filtered command lists based on OpAMP-standard status (`isOpAMPStandard()`).
- Capability map keyed by `(classifier, operation)` for reverse-FQDN lookup (custom commands).
- Custom capability list derived from discovered custom command objects.

Helper APIs:

- `get_registered_command_keys(parameter_exclude_opamp_standard=True, includedisplayname=True)`
- `get_registered_command_fqdns()`
- `get_custom_capabilities_list()`
- `get_command_fqdn(classifier=..., operation=...)`
- `get_command_metadata(parameter_exclude_opamp_standard=True, custom_only=False)`
- `command_object_factory(classifier=..., operation=..., key_values=...)`

Filtering and display behavior:

- `parameter_exclude_opamp_standard=True` returns only non-OpAMP-standard commands.
- `parameter_exclude_opamp_standard=False` returns only OpAMP-standard commands.
- `includedisplayname=True` returns a dictionary of `fqdn -> displayname`.
- `includedisplayname=False` returns a tuple list of `(classifier, operation)` keys.
- Commands with empty/None `get_capability_fqdn()` are excluded from custom capability/FQDN-oriented outputs.

Any duplicate `(classifier, operation)` registration raises an error at startup.

## Command Interface Contract

Command objects implement `CommandObjectInterface` and now expose:

- `isOpAMPStandard() -> bool`
- `getdisplayname() -> str`

Command objects that provide configuration metadata also implement:

- `CommandParameterSchemaInterface.get_user_parameter_schema()`

Schema rows are JSON objects with:

- `parametername` (string)
- `isrequired` (boolean)

## Classifier/Action Dispatch

Dispatch happens in `app.py` via a mapping from `(classifier, action)` to builder methods.

Current mapping:

- `("command", "restart")` -> `_build_restart_command(...)`
- `("custom", "chatopcommand")` -> `_build_custom_command_payload(...)`
- `("custom", "shutdownagent")` -> `_build_custom_command_payload(...)`
- `("custom", "nullcommand")` -> `_build_custom_command_payload(...)`
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
  - `request`
- `data` is set to UTF-8 bytes of the full key/value dictionary JSON.

For `classifier=custom` and `action=shutdownagent`, the server builds a `CommandShutdownAgent` object via the command factory and uses `to_custom_message()`.

`CommandShutdownAgent` payload behavior:

- `capability` is fixed to reverse-FQDN:
  - `org.mp3monster.opamp_provider.command_shutdown_agent`
- `type` is fixed to:
  - `Shutdown Agent`
- `data` is set to UTF-8 bytes of the full key/value dictionary JSON.

For `classifier=custom` and `action=nullcommand`, the server builds a `CommandNullCommand`
object via the command factory and uses `to_custom_message()`.

`CommandNullCommand` payload behavior:

- `capability` is fixed to reverse-FQDN:
  - `org.mp3monster.opamp_provider.nullcommand`
- `type` is fixed to:
  - `Null Command`
- `data` is set to UTF-8 bytes of the full key/value dictionary JSON.

Purpose note:

- `nullcommand` exists primarily to test custom command handling end-to-end
  (discovery, metadata, UI selection/configuration, queueing, and payload emission).

For generic `custom_command` payloads, additional optional key/value pairs can be supplied:

- `capability`
- `type`
- `data`

Defaults:

- `capability` defaults to `custom_command`
- `type` defaults to the submitted `action`
- `data` defaults to empty bytes when omitted

## UI Custom Command Flow

The client dialogue UI uses the metadata endpoint to build the custom command experience:

1. UI calls `GET /api/commands/custom`.
2. Response returns only custom commands with `fqdn`, `displayname`, and `schema`.
3. UI populates a custom command dropdown using `displayname`.
4. On selection, UI renders a configuration table:
   - column 1: parameter label (`parametername`)
   - column 2: editable value field
   - column 3: info icon
5. Hovering the info icon shows only the parameter `description` text (or a default fallback when missing).
6. The UI validates all rows where `isrequired`/`isRequired` is true before enabling send.
7. User submits via the `Send Command` button.
8. Submitting queues the command through `POST /api/clients/<client_id>/commands`.

Notes:

- User-editable fields are sent as key/value pairs from the current custom command table values.
- Internal OpAMP transport fields (for example `classifier`, `type`, `data`) are excluded from user schema metadata and guarded by registry sanitization.

## Consumer ChatOps Command Execution

On the consumer side, `ChatOpsCommand.execute_action(...)` dispatches local HTTP requests based on
the custom message payload:

- URL is built from `chat_ops_port` plus optional `tag` path.
- `attributes` are parsed into a JSON object; invalid/missing attributes resolve to `{}`.
- Request body is serialized as UTF-8 JSON bytes.
- The request explicitly sets:
  - `Content-Type: application/json`
  - `Content-Length: <serialized byte length>`
- Non-2xx responses are converted into an outbound `CustomMessage` with:
  - `type = "failure"`
  - `data = {"http_code":"...","err_msg":"..."}`

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
