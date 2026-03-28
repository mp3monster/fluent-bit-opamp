# Consumer Client Architecture Diagram

This diagram shows how the consumer-side classes and modules relate after introducing the Fluentd concrete implementation.

```mermaid
classDiagram
    direction LR

    class OpAMPClientInterface {
      <<interface>>
      +send()
      +send_disconnect()
      +launch_agent_process()
      +terminate_agent_process()
      +restart_agent_process()
      +handle_custom_message()
      +handle_custom_capabilities()
      +handle_connection_settings()
      +handle_packages_available()
      +handle_remote_config()
      +poll_local_status_with_codes()
      +add_agent_version()
      +get_agent_description()
      +get_agent_capabilities()
      +finalize()
    }

    class AbstractOpAMPClient {
      <<abstract>>
      +data: OpAMPClientData
      +config: ConsumerConfig
      +send()
      +send_http()
      +send_websocket()
      +_handle_server_to_agent()
      +_heartbeat_loop()
      +handle_custom_message()
      +get_custom_handler_folder()*
    }

    class OpAMPClient {
      +get_custom_handler_folder()
    }

    class FluentdOpAMPClient {
      +get_custom_handler_folder()
      +launch_agent_process()
      +add_agent_version()
      +get_agent_description()
      +_health_from_metrics()
    }

    class OpAMPClientData
    class ConsumerConfig
    class FullUpdateControllerInterface {
      <<interface>>
      +configure(full_update_controller)
      +update_sent(ms_from_epoch)
    }
    class AlwaysSend
    class SentCount {
      +full_resend_after: int
      +sent_count: int
    }
    class TimeSend {
      +full_update_after_seconds: int
      +last_full_update_ms: int
    }
    class CommandHandlerInterface {
      <<interface>>
    }
    class CustomMessageHandlerInterface {
      <<interface>>
    }
    class Registry {
      +build_factory_lookup()
      +create_handler()
    }
    class ProtoMessages {
      AgentToServer
      ServerToAgent
      CustomMessage
    }

    OpAMPClientInterface <|.. AbstractOpAMPClient
    AbstractOpAMPClient <|-- OpAMPClient
    AbstractOpAMPClient <|-- FluentdOpAMPClient

    AbstractOpAMPClient *-- OpAMPClientData
    AbstractOpAMPClient --> ConsumerConfig
    OpAMPClientData --> FullUpdateControllerInterface
    FullUpdateControllerInterface <|.. AlwaysSend
    FullUpdateControllerInterface <|.. SentCount
    FullUpdateControllerInterface <|.. TimeSend

    AbstractOpAMPClient --> Registry
    Registry --> CustomMessageHandlerInterface
    CustomMessageHandlerInterface --|> CommandHandlerInterface

    AbstractOpAMPClient --> ProtoMessages
```

## Runtime Entrypoints

```mermaid
flowchart TD
    A["scripts/run_supervisor.sh or .cmd"] --> B["python -m opamp_consumer.client"]
    C["scripts/run_supervisor_fluentd.sh or .cmd"] --> D["python -m opamp_consumer.fluentd_client"]
    E["installed CLI: opamp-consumer"] --> B
    F["installed CLI: opamp-consumer-fluentd"] --> D

    B --> G["OpAMPClient (Fluent Bit)"]
    D --> H["FluentdOpAMPClient (Fluentd)"]

    G --> I["AbstractOpAMPClient shared send/heartbeat/handler flow"]
    H --> I
```

## Reporting Flags and Update Controllers

```mermaid
flowchart TD
    A["Client startup"] --> B["Create controller from full_update_controller_type"]
    B --> C["Initialize reporting_flags (all true by default)"]
    C --> D["_populate_agent_to_server()"]

    D --> E{"Flag true?"}
    E -->|REPORT_DESCRIPTION| F["Include agent_description, set flag false"]
    E -->|REPORT_CAPABILITIES| G["Include capabilities, set flag false"]
    E -->|REPORT_CUSTOM_CAPABILITIES| H["Include custom_capabilities, set flag false"]
    E -->|REPORT_HEALTH| I["Include health, set flag false"]

    F --> J["Send over websocket/http"]
    G --> J
    H --> J
    I --> J

    J --> K{"Send succeeded?"}
    K -->|Yes| L["controller.update_sent()"]
    K -->|No| M["No controller update for this attempt"]

    L --> N{"Controller strategy"}
    N -->|AlwaysSend| O["set_all_reporting_flags(true)"]
    N -->|SentCount threshold met| O
    N -->|TimeSend interval elapsed| O
    N -->|Threshold not met| P["Keep current flags"]

    Q["ServerToAgent.flags includes ReportFullState"] --> O
```
