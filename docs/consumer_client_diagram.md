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

