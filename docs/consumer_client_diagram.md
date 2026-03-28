# Consumer Client Architecture Diagram

This diagram shows the current consumer structure after splitting large `client.py` responsibilities into mixins and bootstrap helpers.

## Class and Module Relationships

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

    class ClientRuntimeMixin {
      +launch_agent_process()
      +terminate_agent_process()
      +restart_agent_process()
      +poll_local_status_with_codes()
      +add_agent_version()
      +_heartbeat_loop()
    }

    class ServerMessageHandlingMixin {
      +_handle_server_to_agent()
      +_validate_reply_instance_uid()
      +handle_error_response()
      +handle_remote_config()
      +handle_connection_settings()
      +handle_packages_available()
      +handle_flags()
      +handle_capabilities()
      +handle_command()
      +handle_agent_identification()
      +handle_custom_capabilities()
      +handle_custom_message()
    }

    class AbstractOpAMPClient {
      <<abstract>>
      +data: OpAMPClientData
      +config: ConsumerConfig
      +send()
      +send_http()
      +send_websocket()
      +_populate_agent_to_server()
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
    class SentCount
    class TimeSend

    class client_message_builder {
      <<module>>
      +populate_agent_to_server()
      +populate_agent_to_server_health()
    }
    class client_transport {
      <<module>>
      +send_http_message()
      +send_websocket_message()
    }
    class client_bootstrap {
      <<module>>
      +load_agent_config()
      +build_minimal_agent()
      +run_client()
      +run_default_client_main()
    }

    OpAMPClientInterface <|.. AbstractOpAMPClient
    ClientRuntimeMixin <|-- AbstractOpAMPClient
    ServerMessageHandlingMixin <|-- AbstractOpAMPClient
    AbstractOpAMPClient <|-- OpAMPClient
    AbstractOpAMPClient <|-- FluentdOpAMPClient

    AbstractOpAMPClient *-- OpAMPClientData
    AbstractOpAMPClient --> ConsumerConfig
    OpAMPClientData --> FullUpdateControllerInterface
    FullUpdateControllerInterface <|.. AlwaysSend
    FullUpdateControllerInterface <|.. SentCount
    FullUpdateControllerInterface <|.. TimeSend

    AbstractOpAMPClient --> client_message_builder
    AbstractOpAMPClient --> client_transport
    OpAMPClient --> client_bootstrap
```

## Runtime Entrypoints

```mermaid
flowchart TD
    A["scripts/run_supervisor.sh or .cmd"] --> B["python -m opamp_consumer.client"]
    C["scripts/run_supervisor_fluentd.sh or .cmd"] --> D["python -m opamp_consumer.fluentd_client"]
    E["installed CLI: opamp-consumer"] --> B
    F["installed CLI: opamp-consumer-fluentd"] --> D

    B --> G["client.main()"]
    G --> H["client_bootstrap.run_default_client_main(...)"]
    H --> I["OpAMPClient (Fluent Bit)"]

    D --> J["fluentd_client.main()"]
    J --> K["FluentdOpAMPClient (Fluentd)"]

    I --> L["AbstractOpAMPClient + mixins"]
    K --> L
```

## Mixin Dispatch Model

```mermaid
flowchart TD
    A["OpAMPClient instance"] --> B{"Which method is called?"}

    B -->|launch_agent_process| C["ClientRuntimeMixin.launch_agent_process()"]
    B -->|_heartbeat_loop| D["ClientRuntimeMixin._heartbeat_loop()"]
    B -->|_handle_server_to_agent| E["ServerMessageHandlingMixin._handle_server_to_agent()"]
    B -->|handle_custom_message| F["ServerMessageHandlingMixin.handle_custom_message()"]
    B -->|send| G["AbstractOpAMPClient.send()"]

    H["FluentdOpAMPClient override exists?"] --> I{"Yes"}
    I --> J["Use FluentdOpAMPClient override first"]
    I --> K["Else use mixin/base implementation"]
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
