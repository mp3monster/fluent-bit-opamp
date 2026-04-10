# Adding Your Own Custom Action

This guide explains how to add and deploy a new custom action end-to-end across:

- provider command creation and queueing
- provider custom-message dispatch
- consumer custom-message handling

It uses `nullcommand` as the baseline pattern.

## Baseline: How `nullcommand` Works Today

Provider baseline class:

- `provider/src/opamp_provider/command_implementations/command_nullcommand.py`

Key parts in that class:

- classifier: `custom`
- action/operation: `nullcommand`
- capability FQDN: `org.mp3monster.opamp_provider.nullcommand`
- payload builder: `to_custom_message()` returning `CustomMessage`

The provider exposes this command in the UI metadata endpoint (`/api/commands/custom`) and can queue it.

Current behavior: the consumer includes a built-in handler for `org.mp3monster.opamp_provider.nullcommand` that logs the `dummyValue` payload field when this command is executed.

## Provider: Add a New Custom Action

## 1) Create a command implementation

Add a new file in:

- `provider/src/opamp_provider/command_implementations/command_<your_action>.py`

Implement:

- `CommandObjectInterface`
- `CommandParameterSchemaInterface` (if your action has user parameters)

Model it after `CommandNullCommand`:

- set classifier (`custom`)
- set action/operation
- return your capability FQDN from `get_capability_fqdn()`
- implement `to_custom_message()` to encode payload data
- optionally implement `get_user_parameter_schema()` for UI fields

Use this naming/location/interface pattern because provider discovery scans `opamp_provider.command_implementations`, imports modules that match the `command*` convention, and registers classes that satisfy the command interfaces. The custom command factory then resolves discovered classes dynamically by capability/operation/action, so matching these conventions is what makes your command discoverable and queueable without per-command factory edits.

## 2) Provider command routing (custom commands: no per-command edit required)

Provider custom command routing uses wildcard handling for classifier `custom`, which means you do not add per-command entries in `COMMAND_BUILDERS`. This matters because queueing still validates `(classifier, action)` and uses `_build_custom_command_payload(...)` to emit `ServerToAgent.custom_message`, so custom commands can flow through one routing path while still being validated.

## 3) Restart provider

Restart the provider after code changes because command discovery/registration is built at startup and new modules are not re-discovered live.

If you want state continuity across restart (clients, pending approvals, queued command state), use state persistence:

1. In the provider UI (`Global Settings` -> `Server Settings` -> `State Persistence`), set `state_save_folder`, `retention_count`, and `autosave_interval_seconds_since_change`, then click `OK + Save`.
2. If persistence is currently disabled, enable it in `config/opamp.json` by setting `provider.state_persistence.enabled` to `true` (the UI currently manages persistence settings but does not toggle this enable flag), then restart the provider once.
3. Check runtime status with `GET /api/settings/diagnostic` and confirm `state_persistence_enabled` is `true`.
4. Optionally force a snapshot before restart using `POST /api/settings/state/save`.
5. Restart provider with restore enabled so persisted state is loaded:
   `opamp-provider --config-path ./config/opamp.json --restore`

After restart, verify `GET /api/settings/diagnostic` again and check `state_persistence.restore_status` for the restore result.

## Consumer: Add a Handler for Your Capability

## 1) Create handler class

Add a handler file in:

- `consumer/src/opamp_consumer/custom_handlers/<your_handler>.py`

Subclass:

- `CustomMessageHandlerInterface`

Implement:

- `get_fqdn()` (must exactly match provider capability FQDN)
- `handle_message(...)`
- `execute_action(...)`

Reference implementations:

- `consumer/src/opamp_consumer/custom_handlers/chatops_command.py`
- `consumer/src/opamp_consumer/custom_handlers/shutdowncommand.py`
- `consumer/src/opamp_consumer/custom_handlers/nullcommand.py`

Do this because consumer dispatch is capability-driven: `handle_custom_message(...)` resolves by `CustomMessage.capability` and executes the matching handler. If your handler FQDN does not exactly match what the provider sends, the message is rejected.

## 2) Ensure handler discovery is enabled

Set in consumer config:

- `consumer.allow_custom_capabilities: true`

The default client dynamically discovers handlers from:

- `consumer/src/opamp_consumer/custom_handlers`

via `build_factory_lookup(...)`.

Set this because the handler registry stays empty when `allow_custom_capabilities` is false. Discovery is dynamic, but only from this folder and only for classes implementing `CustomMessageHandlerInterface`.

## 3) Restart consumer

Restart the consumer so the new handler module is discovered and loaded into the in-memory lookup created when client instances initialize.

## Deploy and Verify

## 1) Verify provider metadata

Call:

- `GET /api/commands/custom`

Confirm your command appears with:

- `fqdn`
- `operation`
- `displayname`
- `schema` (if defined)

This confirms provider discovery worked and that the command is visible to UI/API clients before runtime dispatch testing.

## 2) Queue command

From UI:

- open a client
- Commands tab
- choose your custom command
- fill required parameters
- queue

Or via API with key/value pairs (include at minimum `classifier`, `operation`, `capability`).

Queueing verifies provider route validation and command normalization in `/api/clients/<client_id>/commands`.

## 3) Verify consumer execution

Check consumer logs for:

- custom message received for your capability
- handler resolved
- `execute_action(...)` called

This confirms the end-to-end contract: provider emitted the expected capability/type/data and consumer mapped that capability to the intended handler.

## Existing Code Changes Needed Today

For a new UI-visible custom action that behaves like `nullcommand`, the current codebase requires these edits:

1. Add a new command implementation file under `provider/src/opamp_provider/command_implementations/`, because provider module/class discovery is startup-based and convention-driven.
2. Add a consumer handler class under `consumer/src/opamp_consumer/custom_handlers/` with matching capability FQDN, because custom messages are dispatched by capability and unmatched capabilities are rejected.
3. Set `consumer.allow_custom_capabilities=true` in config, because handler discovery/lookup is disabled otherwise.

You do not need per-command edits in:

1. `provider/src/opamp_provider/commands.py` for custom capability/operation mapping.
2. `provider/src/opamp_provider/app.py` to register custom actions in `COMMAND_BUILDERS`.

Optional but recommended:

1. Add tests in `provider/tests` for queueing and payload shape.
2. Add tests in `consumer/tests` for handler discovery and `execute_action(...)`.
