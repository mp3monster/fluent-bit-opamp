# OpAMP Consumer Configuration

This document describes how to configure and run the OpAMP consumer using a config file or CLI overrides.

## Config file

The consumer reads `opamp.json` from the current working directory by default. You can override the
config file location with the `OPAMP_CONFIG_PATH` environment variable or the `--config-path`
CLI argument.

Example `opamp.json`:

```json
{
  "consumer": {
    "server_url": "http://localhost:4320",
    "server_port": 4320,
    "client_status_port": 2020,
    "chat_ops_port": 8888,
    "transport": "http",
    "log_agent_api_responses": false,
    "fluentbit_config_path": "./fluent-bit.conf",
    "additional_fluent_bit_params": ["-R"],
    "heartbeat_frequency": 30,
    "allow_custom_capabilities": true,
    "log_level": "debug",
    "service_name": "Fluentbit",
    "service_namespace": "FluentBitNS",
    "agent_capabilities": [
      "ReportsStatus",
      "ReportsHealth",
      "ReportsHeartbeat"
    ]
  }
}
```

### Fields

- `consumer.server_url` (string, required)
  OpAMP server base URL.
- `consumer.server_port` (integer, optional)
  Optional server port override used when building default URLs.
- `consumer.transport` (string, optional, default `http`)
  Transport to use when sending OpAMP messages. Supported values: `http`, `websocket`.
- `consumer.client_status_port` (integer, optional)
  Port used for polling the local agent status endpoints. If omitted, it is read from the Fluent Bit
  `http_port` setting.
- `consumer.chat_ops_port` (integer, optional)
  Port used by the ChatOps custom handler for local HTTP commands. If omitted, defaults to `8888`.
- `consumer.log_agent_api_responses` (boolean, optional, default `false`)
  When true, heartbeat polling logs full Fluent Bit API responses; when false, it logs response codes only.
- `consumer.fluentbit_config_path` (string, required)
  Path to the Fluent Bit configuration file.
- `consumer.additional_fluent_bit_params` (array of strings, required)
  Extra command-line arguments passed to `fluentbit`.
- `consumer.heartbeat_frequency` (integer, optional, default `30`)
  Heartbeat interval in seconds.
- `consumer.allow_custom_capabilities` (boolean, optional, default `false` when omitted)
  Enables custom handler registry discovery and custom capability publishing. Set this to `true` to
  allow custom capability detection; when the field is missing the consumer behaves as `false`.
- `consumer.log_level` (string, optional, default `debug`)
  Log level for the consumer (`debug`, `info`, `warning`, `error`, `critical`).
- `consumer.service_name` (string, optional)
  Service name reported in the agent description.
- `consumer.service_namespace` (string, optional)
  Service namespace reported in the agent description.
- `consumer.agent_capabilities` (array of strings, required)
  Capabilities list. Names must match `AgentCapabilities` enum values in `shared/opamp_config.py`.

## CLI overrides

CLI flags override config file values. When a CLI value is provided, the file value is ignored and
this decision is logged by the application.

```bash
python -m opamp_consumer.client \
  --config-path ./opamp.json \
  --server-url http://localhost:4320 \
  --fluentbit-config-path ./fluent-bit.conf \
  --additional-fluent-bit-params -R \
  --heartbeat-frequency 15 \
  --agent-capabilities ReportsStatus ReportsHealth ReportsHeartbeat
```

### CLI flags

- `--config-path` Path to the config file. If omitted, defaults to `./opamp.json`.
- `--server-url` Override `consumer.server_url`.
- `--fluentbit-config-path` Override `consumer.fluentbit_config_path`.
- `--additional-fluent-bit-params` Override `consumer.additional_fluent_bit_params`.
- `--heartbeat-frequency` Override `consumer.heartbeat_frequency`.
- `--agent-capabilities` Override `consumer.agent_capabilities`.

## Run scripts

Helper scripts live in `scripts/` at the repo root:

- Windows CMD: `scripts/run_supervisor.cmd`
- Bash: `scripts/run_supervisor.sh`

Both scripts write logs to `logs/supervisor.log` and rotate it on startup.

You can also gracefully stop the supervisor by creating a semaphore file named
`OpAMPSupervisor.signal` in the folder where the supervisor was started.
