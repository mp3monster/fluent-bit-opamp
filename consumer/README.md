# OpAMP Consumer Configuration

This document consolidates all consumer configuration options and their CLI override support.

## Table of Contents

- [Config Source](#config-source)
- [Override Precedence](#override-precedence)
- [Quick Start Minimal Config](#quick-start-minimal-config)
- [Run Scripts](#run-scripts)
- [Example `opamp.json`](#example-opampjson)
- [Consumer Config Keys](#consumer-config-keys)
- [Hardwired Capabilities](#hardwired-capabilities)
- [Connection Settings](#connection-settings)
- [Fluent Bit Comment Metadata](#fluent-bit-comment-metadata)
- [CLI Example](#cli-example)
- [Running As A Service/Daemon](#running-as-a-servicedaemon)
- [Installed CLI Commands](#installed-cli-commands)
- [Fluentd Consumer](#fluentd-consumer)
- [Required Fluentd Monitor Source](#required-fluentd-monitor-source)

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
    "server-authorization": "none",
    "agent_config_path": "./fluent-bit.conf",
    "agent_additional_params": [],
    "heartbeat_frequency": 30,
    "full_update_controller": {
      "fullResendAfter": 1
    },
    "full_update_controller_type": "SentCount"
  }
}
```

## Run Scripts

Helper scripts in repo root:
- `scripts/run_fluentbit_supervisor.cmd`
- `scripts/run_fluentbit_supervisor.sh`
- `scripts/run_fluentd_supervisor.cmd`
- `scripts/run_fluentd_supervisor.sh`
- `scripts/run_all_supervisors.cmd`
- `scripts/run_all_supervisors.sh`

Fluent Bit writes to `logs/supervisor_fluentbit.log` and Fluentd writes to
`logs/supervisor_fluentd.log` (each rotates on startup).

Default config resolution:
- Fluent Bit supervisor: `tests/opamp.json` -> `config/opamp.json`
- Fluentd supervisor: `consumer/opamp-fluentd.json` -> `tests/opamp.json` -> `config/opamp.json`
- Fluentd runtime config path: `consumer/fluentd.conf`

Graceful stop: create `OpAMPSupervisor.signal` in the supervisor working directory.

## Example `opamp.json`

```json
{
  "consumer": {
    "server_url": "http://localhost",
    "server_port": 4320,
    "client_status_port": 2020,
    "chat_ops_port": 8888,
    "transport": "http",
    "server-authorization": "none",
    "OpAMP-token": "optional-config-token",
    "idp-token-url": "https://idp.example.com/realms/opamp/protocol/openid-connect/token",
    "idp-client-id": "opamp-consumer",
    "idp-client-secret": "replace-me",
    "idp-scope": "opamp",
    "idp-grant-type": "client_credentials",
    "log_agent_api_responses": false,
    "agent_config_path": "./fluent-bit.conf",
    "agent_additional_params": ["-R"],
    "heartbeat_frequency": 30,
    "full_update_controller": {
      "fullResendAfter": 1
    },
    "full_update_controller_type": "SentCount",
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
| `consumer.full_update_controller` | object | Yes (`--full-update-controller`, JSON string) | Full update controller settings. `fullResendAfter` controls when all reporting flags are reset to `true`. | `{"fullResendAfter":1}` |
| `consumer.full_update_controller_type` | string | No | Full update controller implementation name (`SentCount`, `AlwaysSend`, `TimeSend`). | `"SentCount"` |
| `consumer.log_level` | string | Yes (`--log-level`) | Consumer log level name (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Resolved via Python `logging` names. | `"debug"` |
| `consumer.transport` | string | No | OpAMP transport mode (`http` or `websocket`). | `"http"` |
| `consumer.server-authorization` | string | No | Outbound provider auth mode: `none`, `env-var`, `config-var`, or `idp`. | `"none"` |
| `consumer.OpAMP-token` | string | No | Static token used when `server-authorization=config-var`. | `"token-value"` |
| `consumer.idp-token-url` | string | No | IdP OAuth token endpoint URL used when `server-authorization=idp`. | `"https://idp.example.com/.../token"` |
| `consumer.idp-client-id` | string | No | IdP OAuth client ID for `idp` mode. | `"opamp-consumer"` |
| `consumer.idp-client-secret` | string | No | IdP OAuth client secret for `idp` mode. | `"replace-me"` |
| `consumer.idp-scope` | string | No | Optional OAuth scope for `idp` mode. | `"opamp"` |
| `consumer.idp-grant-type` | string | No | OAuth grant type for `idp` mode. Default `client_credentials`. | `"client_credentials"` |
| `consumer.log_agent_api_responses` | boolean | No | Enables verbose logging of local API responses. | `false` |
| `consumer.allow_custom_capabilities` | boolean | No | Enables publishing/discovery of custom capabilities. | `true` |
| `consumer.service_name` | string | No | Reported service name in agent description. | `"Fluentbit"` |
| `consumer.service_namespace` | string | No | Reported service namespace in agent description. | `"FluentBitNS"` |
| `consumer.client_status_port` | integer | No | Local status polling port. If unset, parsed from agent config `http_port`. | `2020` |
| `consumer.chat_ops_port` | integer | No | Local ChatOps port used by custom command handler. Defaults to `8888` when unset. | `8888` |

Authorization mode behavior:
- `none`: no outbound `Authorization` header.
- `env-var`: token is read from `OpAMP-token` environment variable.
- `config-var`: token is read from `consumer.OpAMP-token`.
- `idp`: token is requested from the configured IdP token endpoint and cached in
  runtime config header fields (`server_authorization_header_name/value`).
  If provider returns auth errors (`401`/`403`), the client renegotiates and retries once.

## Hardwired Capabilities

`agent_capabilities` is not read from config. The consumer hardwires:
- `ReportsStatus`
- `AcceptsRestartCommand`
- `ReportsHealth`

## Connection Settings

We currently do not support `ReportsOwnTraces`, `ReportsOwnMetrics`, or
`ReportsOwnLogs` as configurable connection-settings features in this project.

Design rationale:

- Fluent Bit and Fluentd operational configuration is expected to define
  observability pipelines directly.
- The OpAMP protocol already lets us deploy updated agent configuration when
  pipeline changes are needed.
- In practice, include-based configuration structure and variable injection can
  make runtime connection-settings mutation error-prone and harder to operate
  safely across environments.

Recommended pattern:

- Keep each agent's standard configuration responsible for its own
  observability outputs.
- Use include files (for example environment-specific included fragments) to
  manage traces/metrics/logs destinations and credentials.
- Use OpAMP-delivered config updates to roll out those include/file changes in
  a controlled way.

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
python -m opamp_consumer.fluentbit_client \
  --config-path ./opamp.json \
  --server-url http://localhost:4320 \
  --server-port 4320 \
  --agent-config-path ./fluent-bit.conf \
  --agent-additional-params -R \
  --heartbeat-frequency 15 \
  --log-level INFO \
  --full-update-controller '{"fullResendAfter":1}'
```

## Running As A Service/Daemon

For Linux `systemd` and Windows service examples (including required permissions so the consumer can launch `fluent-bit` or `fluentd`), see:

- `../docs/service_daemon_setup.md`

## Installed CLI Commands

When installed as a package, console scripts are available:

- `opamp-consumer` -> `opamp_consumer.fluentbit_client:main`
- `opamp-consumer-fluentd` -> `opamp_consumer.fluentd_client:main`

## Fluentd Consumer

An alternate concrete consumer implementation is available for Fluentd use cases.

- Module entrypoint: `python -m opamp_consumer.fluentd_client`

### Required Fluentd Monitor Source

For OpAMP to read Fluentd health/version data, the Fluentd config must include a `monitor_agent` source (core Fluentd functionality).

Example:

```conf
<source>
  @type monitor_agent
  bind 0.0.0.0
  port 24220
  log_level info
</source>
```

If `monitor_agent` is not configured, the consumer cannot poll Fluentd runtime status endpoints.

Example:

```bash
python -m opamp_consumer.fluentd_client \
  --config-path ./opamp.json \
  --agent-config-path ./fluentd.conf \
  --server-url http://localhost:4320
```
