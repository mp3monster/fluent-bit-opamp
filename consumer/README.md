# OpAMP Consumer Configuration

This document describes how to configure the OpAMP consumer using a config file or CLI overrides.

## Config file

The consumer reads `opamp.json` from the current working directory by default. You can override the
config file location with the `OPAMP_CONFIG_PATH` environment variable or the `--config-path`
CLI argument.

Example `opamp.json`:

```json
{
  "consumer": {
    "server_url": "http://localhost:4320",
    "fluentbit_config_path": "./fluent-bit.conf",
    "additional_fluent_bit_params": ["-R"],
    "heartbeat_frequency": 30,
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
- `consumer.fluentbit_config_path` (string, required)
  Path to the Fluent Bit configuration file.
- `consumer.additional_fluent_bit_params` (array of strings, required)
  Extra command-line arguments passed to `fluentbit`.
- `consumer.heartbeat_frequency` (integer, optional, default `30`)
  Heartbeat interval in seconds.
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
