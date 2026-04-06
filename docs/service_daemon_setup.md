# Running As A Service Or Daemon

This guide explains how to run the provider or consumer as a long-running service and what permissions are required, especially when the consumer launches Fluent Bit or Fluentd as child processes.

## Overview

- Provider service: runs the Quart server and web UI.
- Consumer service: runs OpAMP client loop and launches/manages agent process (`fluent-bit` or `fluentd`).
- The consumer process user must have execute rights for the agent binary and read rights for agent config files.

## Linux (`systemd`)

### 1. Create a service user and folders

```bash
sudo useradd --system --create-home --home-dir /opt/opamp --shell /usr/sbin/nologin opamp
sudo mkdir -p /opt/opamp /var/log/opamp
sudo chown -R opamp:opamp /opt/opamp /var/log/opamp
```

Copy your repo/venv/config under `/opt/opamp` (or adjust paths in the units below).

### 2. Provider unit example

Create `/etc/systemd/system/opamp-provider.service`:

```ini
[Unit]
Description=OpAMP Provider
After=network.target

[Service]
Type=simple
User=opamp
Group=opamp
WorkingDirectory=/opt/opamp
Environment=OPAMP_CONFIG_PATH=/opt/opamp/config/opamp.json
ExecStart=/opt/opamp/.venv/bin/opamp-provider --config-path /opt/opamp/config/opamp.json
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/opamp/provider.log
StandardError=append:/var/log/opamp/provider.log

[Install]
WantedBy=multi-user.target
```

### 3. Consumer unit example (Fluent Bit)

Create `/etc/systemd/system/opamp-consumer-fluentbit.service`:

```ini
[Unit]
Description=OpAMP Consumer (Fluent Bit)
After=network.target

[Service]
Type=simple
User=opamp
Group=opamp
WorkingDirectory=/opt/opamp
Environment=OPAMP_CONFIG_PATH=/opt/opamp/config/opamp.json
ExecStart=/opt/opamp/.venv/bin/opamp-consumer --config-path /opt/opamp/config/opamp.json --agent-config-path /opt/opamp/consumer/fluent-bit.yaml
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/opamp/consumer-fluentbit.log
StandardError=append:/var/log/opamp/consumer-fluentbit.log

[Install]
WantedBy=multi-user.target
```

### 4. Consumer unit example (Fluentd)

Create `/etc/systemd/system/opamp-consumer-fluentd.service`:

```ini
[Unit]
Description=OpAMP Consumer (Fluentd)
After=network.target

[Service]
Type=simple
User=opamp
Group=opamp
WorkingDirectory=/opt/opamp
Environment=OPAMP_CONFIG_PATH=/opt/opamp/config/opamp.json
ExecStart=/opt/opamp/.venv/bin/opamp-consumer-fluentd --config-path /opt/opamp/config/opamp.json --agent-config-path /opt/opamp/consumer/fluentd.conf
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/opamp/consumer-fluentd.log
StandardError=append:/var/log/opamp/consumer-fluentd.log

[Install]
WantedBy=multi-user.target
```

### 5. Enable/start units

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now opamp-provider.service
sudo systemctl enable --now opamp-consumer-fluentbit.service
# or:
# sudo systemctl enable --now opamp-consumer-fluentd.service
```

## Windows Service

Using [NSSM](https://nssm.cc/) is the simplest approach for Python entrypoints.

### 1. Service account requirements

- `Log on as a service` right.
- Read permissions for:
  - repo files
  - `config\\opamp.json`
  - agent config files (`fluent-bit.yaml` or `fluentd.conf`)
- Execute permissions for:
  - `python.exe` and virtualenv scripts
  - `fluent-bit.exe` or `fluentd` command
- Write permissions for logs/output directories.

### 2. Provider service example

```powershell
nssm install OpAMPProvider "D:\dev\opamp\.venv\Scripts\python.exe" "-m opamp_provider.app --config-path D:\dev\opamp\config\opamp.json"
nssm set OpAMPProvider AppDirectory "D:\dev\opamp"
nssm set OpAMPProvider AppEnvironmentExtra "OPAMP_CONFIG_PATH=D:\dev\opamp\config\opamp.json"
nssm start OpAMPProvider
```

### 3. Consumer service example (Fluent Bit)

```powershell
nssm install OpAMPConsumerFluentBit "D:\dev\opamp\.venv\Scripts\python.exe" "-m opamp_consumer.fluentbit_client --config-path D:\dev\opamp\config\opamp.json --agent-config-path D:\dev\opamp\consumer\fluent-bit.yaml"
nssm set OpAMPConsumerFluentBit AppDirectory "D:\dev\opamp"
nssm set OpAMPConsumerFluentBit AppEnvironmentExtra "OPAMP_CONFIG_PATH=D:\dev\opamp\config\opamp.json"
nssm start OpAMPConsumerFluentBit
```

### 4. Consumer service example (Fluentd)

```powershell
nssm install OpAMPConsumerFluentd "D:\dev\opamp\.venv\Scripts\python.exe" "-m opamp_consumer.fluentd_client --config-path D:\dev\opamp\config\opamp.json --agent-config-path D:\dev\opamp\consumer\fluentd.conf"
nssm set OpAMPConsumerFluentd AppDirectory "D:\dev\opamp"
nssm set OpAMPConsumerFluentd AppEnvironmentExtra "OPAMP_CONFIG_PATH=D:\dev\opamp\config\opamp.json"
nssm start OpAMPConsumerFluentd
```

## Permission Checklist For Launching Fluent Bit/Fluentd

For the user account running the consumer service:

- Execute `fluent-bit` or `fluentd` from `PATH` (or use absolute path in config/args).
- Read the agent config file (`consumer/fluent-bit.yaml` or `consumer/fluentd.conf`).
- Read/write any files or sockets referenced by that agent config.
- Be allowed to create child processes (required by `subprocess.Popen` in consumer runtime).
- Be allowed to signal/terminate its own child process (used during restart/shutdown operations).

## Notes

- The provider does not launch Fluent Bit or Fluentd; this permission requirement is consumer-specific.
- For Fluentd deployments, include a `monitor_agent` source in `fluentd.conf`; the consumer relies on it for local status polling.
- If you bind provider to a privileged Linux port (<1024), you need root or `CAP_NET_BIND_SERVICE`.
- If bearer auth is enabled, configure environment variables in the unit/service environment as documented in `docs/authentication.md`.
