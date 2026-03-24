# OpAMP Consumer Configuration

This document consolidates all consumer configuration options and their CLI override support.

## Config Source

The consumer reads `opamp.json` from the current working directory by default.

You can override config path with:
- environment variable: `OPAMP_CONFIG_PATH`
- CLI flag: `--config-path`

## Override Precedence

Configuration is applied in this order (later wins):
1. Built-in defaults
2. `opamp.json` values
3. CLI parameters (these are overrides for config file values)
4. Agent config file parsing (`agent_config_path`) for runtime HTTP settings

Notes:
- If a CLI parameter is provided, it overrides the corresponding `opamp.json` value.
- Values parsed from the agent config file (`http_port`, `http_listen`, `http_server`) populate runtime fields:
  - `client_status_port`
  - `agent_http_port`
  - `agent_http_listen`
  - `agent_http_server`

## Quick Start Minimal Config

Use this minimal config for a fast local startup:

```json
{
  "consumer": {
    "server_url": "http://localhost",
    "agent_config_path": "./fluent-bit.conf",
    "agent_additional_params": [],
    "heartbeat_frequency": 30
  }
}
```

## Example `opamp.json`

```json
{
  "consumer": {
    "server_url": "http://localhost",
    "server_port": 4320,
    "client_status_port": 2020,
    "chat_ops_port": 8888,
    "transport": "http",
    "log_agent_api_responses": false,
    "agent_config_path": "./fluent-bit.conf",
    "agent_additional_params": ["-R"],
    "heartbeat_frequency": 30,
    "allow_custom_capabilities": true,
    "log_level": "debug",
    "service_name": "Fluentbit",
    "service_namespace": "FluentBitNS"
  }
}
```

## Consumer Config Keys

`CLI` indicates direct CLI override support.

| Key | Type | CLI | Description | Example |
|---|---|---|---|---|
| `consumer.server_url` | string | Yes (`--server-url`) | OpAMP provider base URL. | `"http://localhost"` |
| `consumer.server_port` | integer | Yes (`--server-port`) | Optional port hint used by startup logic. | `4320` |
| `consumer.agent_config_path` | string | Yes (`--agent-config-path`) | Path to agent config file loaded by consumer. | `"./fluent-bit.conf"` |
| `consumer.agent_additional_params` | array[string] | Yes (`--agent-additional-params`) | Extra args passed to the launched agent process. | `["-R"]` |
| `consumer.heartbeat_frequency` | integer | Yes (`--heartbeat-frequency`) | Heartbeat interval in seconds. | `30` |
| `consumer.transport` | string | No | OpAMP transport mode (`http` or `websocket`). | `"http"` |
| `consumer.log_agent_api_responses` | boolean | No | Enables verbose logging of local API responses. | `false` |
| `consumer.allow_custom_capabilities` | boolean | No | Enables publishing/discovery of custom capabilities. | `true` |
| `consumer.log_level` | string | No | Consumer log level (`debug`, `info`, `warning`, `error`, `critical`). | `"debug"` |
| `consumer.service_name` | string | No | Reported service name in agent description. | `"Fluentbit"` |
| `consumer.service_namespace` | string | No | Reported service namespace in agent description. | `"FluentBitNS"` |
| `consumer.client_status_port` | integer | No | Local status polling port. If unset, parsed from agent config `http_port`. | `2020` |
| `consumer.chat_ops_port` | integer | No | Local ChatOps port used by custom command handler. Defaults to `8888` when unset. | `8888` |

## Hardwired Capabilities

`agent_capabilities` is not read from config. The consumer hardwires:
- `ReportsStatus`
- `AcceptsRestartCommand`
- `ReportsHealth`

## Legacy Compatibility

The following legacy keys/flags are still accepted:
- `consumer.fluentbit_config_path` -> alias for `consumer.agent_config_path`
- `consumer.additional_fluent_bit_params` -> alias for `consumer.agent_additional_params`
- `--fluentbit-config-path` -> alias for `--agent-config-path`
- `--additional-fluent-bit-params` -> alias for `--agent-additional-params`

## Fluent Bit Comment Metadata

The consumer reads optional metadata comments from the agent config file:
- `# agent_description: ...`
- `# service_instance_id: ...`

Supported tokens in `service_instance_id`:
- `__IP__` -> local host IP
- `__hostname__` -> local hostname
- `__mac-ad__` -> local MAC address

Example:

```ini
# service_instance_id: fb-__hostname__-__IP__-__mac-ad__
```

## CLI Example

```bash
python -m opamp_consumer.client \
  --config-path ./opamp.json \
  --server-url http://localhost:4320 \
  --server-port 4320 \
  --agent-config-path ./fluent-bit.conf \
  --agent-additional-params -R \
  --heartbeat-frequency 15
```

## Run Scripts

Helper scripts in repo root:
- `scripts/run_supervisor.cmd`
- `scripts/run_supervisor.sh`

Both write logs to `logs/supervisor.log` and rotate on startup.

Graceful stop: create `OpAMPSupervisor.signal` in the supervisor working directory.
