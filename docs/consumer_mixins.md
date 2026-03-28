# Consumer Mixins Explained

This document explains how mixins are used in the consumer and how method dispatch works in practice.

## What a mixin is

A mixin is a class that contributes behavior to another class through inheritance, without being a full standalone domain model.

In this project, mixins are used to keep `client.py` smaller by separating large behavior groups into focused files.

## Where mixins are used

`AbstractOpAMPClient` is defined as:

```python
class AbstractOpAMPClient(
    ClientRuntimeMixin, ServerMessageHandlingMixin, OpAMPClientInterface, ABC
):
    ...
```

The two mixins are:

- `ClientRuntimeMixin` in `consumer/src/opamp_consumer/client_mixins.py`
- `ServerMessageHandlingMixin` in `consumer/src/opamp_consumer/client_mixins.py`

## What each mixin owns

`ClientRuntimeMixin` owns runtime/process and polling behavior:

- process lifecycle (`launch_agent_process`, `terminate_agent_process`, `restart_agent_process`)
- local status polling (`poll_local_status_with_codes`)
- version discovery (`add_agent_version`)
- heartbeat loop (`_heartbeat_loop`)

`ServerMessageHandlingMixin` owns provider message handling:

- top-level dispatch (`_handle_server_to_agent`)
- reply validation (`_validate_reply_instance_uid`)
- handlers for server payload sections (`handle_*`)
- custom message dispatch to registered handlers (`handle_custom_message`)

`AbstractOpAMPClient` keeps cross-cutting client responsibilities:

- send orchestration (`send`, `send_http`, `send_websocket`)
- message population (`_populate_agent_to_server`, description/capability helpers)
- full update controller setup and state wiring

## How method resolution works

Python looks for methods in MRO order (Method Resolution Order). For `OpAMPClient`, that order starts:

1. `OpAMPClient`
2. `AbstractOpAMPClient`
3. `ClientRuntimeMixin`
4. `ServerMessageHandlingMixin`
5. `OpAMPClientInterface`
6. `ABC`
7. `object`

Practical impact:

- `send()` resolves in `AbstractOpAMPClient`.
- `_heartbeat_loop()` resolves in `ClientRuntimeMixin`.
- `_handle_server_to_agent()` resolves in `ServerMessageHandlingMixin`.

## How overrides interact with mixins

A concrete subclass can override mixin-provided behavior.

Example: `FluentdOpAMPClient` overrides runtime methods such as `launch_agent_process()` and `add_agent_version()`. Those overrides are used first, before mixin methods, because subclass methods win in MRO lookup.

## Why this refactor helps

- keeps each file focused and easier to review
- allows runtime behavior and server-dispatch behavior to evolve independently
- reduces merge conflict pressure in one large `client.py`
- provides clearer extension points for alternate client types

## Related files

- `consumer/src/opamp_consumer/client.py`
- `consumer/src/opamp_consumer/client_mixins.py`
- `consumer/src/opamp_consumer/client_bootstrap.py`
- `consumer/src/opamp_consumer/fluentd_client.py`
