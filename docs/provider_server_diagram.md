# Provider Server Architecture Diagram

This document contains Mermaid source diagrams for the provider/server side.  
Rendered PNG versions are embedded in [docs/provider_server_diagrams.md](provider_server_diagrams.md).

## Class and Module Relationships

```mermaid
classDiagram
    direction LR

    class ProviderServerEntrypoint {
      <<module>>
      +main()
    }

    class ProviderApp {
      <<module>>
      +opamp_http()
      +opamp_websocket()
      +queue_command()
      +list_clients()
      +set_client_actions()
      +set_requested_config()
      +_build_response()
      +_apply_command_intent()
      +enforce_bearer_auth()
    }

    class ProviderConfig {
      <<module>>
      +load_config_with_overrides()
      +set_config()
      +persist_provider_config()
      +_load_provider_tls_config()
    }

    class ProviderAuth {
      <<module>>
      +evaluate_bearer_auth()
      +evaluate_asgi_scope_auth()
      +reload_auth_settings()
    }

    class ClientStore {
      +upsert_from_agent_msg()
      +queue_command()
      +next_pending_command()
      +mark_command_sent()
      +set_next_actions()
      +pop_next_action()
      +set_agent_identification()
      +pop_agent_identification()
    }

    class ClientRecord
    class EventHistory
    class CommandRecord

    class CommandRegistry {
      <<module>>
      +command_object_factory()
      +get_command_metadata()
      +get_custom_capabilities_list()
    }

    class CommandObjectInterface {
      <<interface>>
      +get_command_classifier()
      +get_key_value_dictionary()
      +get_capability_fqdn()
      +isOpAMPStandard()
    }

    class RestartAgent
    class ChatOpCommand
    class CommandShutdownAgent
    class CommandNullCommand

    class ProviderTransport {
      <<module>>
      +encode_message()
      +decode_message()
    }

    class MCPRoutes {
      <<module>>
      +tool_openapi_spec()
      +list_connected_otel_agents()
      +list_all_commands()
    }

    class MCPBridge {
      <<module>>
      +register_tool_routes()
      +register_mcp_transport()
    }

    ProviderServerEntrypoint --> ProviderConfig
    ProviderServerEntrypoint --> ProviderApp
    ProviderServerEntrypoint --> ClientStore

    ProviderApp --> ProviderAuth
    ProviderApp --> ProviderConfig
    ProviderApp --> ClientStore
    ProviderApp --> CommandRegistry
    ProviderApp --> ProviderTransport
    ProviderApp --> MCPBridge

    ClientStore o-- ClientRecord
    ClientRecord o-- CommandRecord
    CommandRecord --|> EventHistory

    CommandRegistry ..> CommandObjectInterface
    RestartAgent ..|> CommandObjectInterface
    ChatOpCommand ..|> CommandObjectInterface
    CommandShutdownAgent ..|> CommandObjectInterface
    CommandNullCommand ..|> CommandObjectInterface

    MCPBridge --> ProviderAuth
    MCPBridge --> MCPRoutes
    MCPRoutes --> ClientStore
    MCPRoutes --> CommandRegistry
```

## Runtime Entrypoints and Transport

```mermaid
flowchart TD
    A["scripts/run_opamp_server.sh or .cmd"] --> B["python -m opamp_provider.server"]
    C["installed CLI: opamp-provider"] --> B

    B --> D["server.main()"]
    D --> E["provider_config.load_config_with_overrides(...)"]
    E --> F["provider_config.set_config(...)"]
    F --> G["STORE.set_default_heartbeat_frequency(...)"]
    G --> H{"provider.tls present?"}
    H -->|No| I["Quart app.run(host, port)"]
    H -->|Yes| J["Quart app.run(host, port, certfile, keyfile)"]

    I --> K["POST /v1/opamp"]
    I --> L["WEBSOCKET /v1/opamp"]
    I --> M["/api/* + /tool/* + /ui"]

    J --> K
    J --> L
    J --> M

    K --> N["opamp_http()"]
    N --> O["STORE.upsert_from_agent_msg(..., channel=HTTP)"]
    O --> P["_build_response(...)"]
    P --> Q["ServerToAgent protobuf response"]

    L --> R["opamp_websocket()"]
    R --> S["decode_message() + AgentToServer parse"]
    S --> T["STORE.upsert_from_agent_msg(..., channel=websocket)"]
    T --> U["_build_response(...)"]
    U --> V["encode_message() + websocket.send(...)"]
```

## Command Queue and Dispatch Pipeline

```mermaid
flowchart TD
    A["Web UI or API caller"] --> B["POST /api/clients/:client_id/commands"]
    B --> C["queue_command() validates and normalizes key/value pairs"]

    C --> D{"Concrete command object available?"}
    D -->|Yes| E["command_object_factory(...)"]
    D -->|No| F["Use normalized pairs directly"]
    E --> G["STORE.queue_command(...)"]
    F --> G

    G --> H["CommandRecord stored on ClientRecord.commands"]

    I["Client check-in via HTTP or websocket"] --> J["STORE.next_pending_command(client_id)"]
    J --> K["_build_response(..., pending_command)"]
    K --> L["_apply_command_intent(...)"]
    L --> M{"Builder selected"}
    M -->|command/restart| N["ServerToAgent.command"]
    M -->|command/forceresync| O["ServerToAgent.flags ReportFullState"]
    M -->|custom/custom_command| P["ServerToAgent.custom_message"]

    N --> Q["Transmit response to client"]
    O --> Q
    P --> Q

    Q --> R["STORE.mark_command_sent(...)"]
```

## Auth and MCP Transport Routing

```mermaid
flowchart TD
    A["Incoming request"] --> B{"Transport type"}

    B -->|HTTP to Quart route| C["@app.before_request enforce_bearer_auth()"]
    C --> D["provider_auth.evaluate_bearer_auth(...)"]
    D --> E{"Allowed?"}
    E -->|No| F["Return JSON 401/503 (+ WWW-Authenticate for 401)"]
    E -->|Yes| G["Continue to route handler"]

    B -->|ASGI scope for /sse, /messages, /mcp| H["register_mcp_transport() dispatch wrapper"]
    H --> I["provider_auth.evaluate_asgi_scope_auth(scope)"]
    I --> J{"Allowed?"}
    J -->|No| K["ASGI auth rejection payload"]
    J -->|Yes| L["Forward to FastMCP ASGI app"]

    B -->|WebSocket /v1/opamp| M["opamp_websocket()"]
    M --> N["decode_message() + provider protocol handling"]

    O["Protected prefixes default: /tool, /sse, /messages, /mcp"] --> C
    O --> I
```
