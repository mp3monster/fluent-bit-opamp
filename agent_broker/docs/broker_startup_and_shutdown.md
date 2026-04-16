# Broker Startup and Shutdown

This runbook describes how to start `opamp_broker`, stop it cleanly, and configure logging.

## Startup

### 1. Configure environment

Required Slack values:

- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `SLACK_APP_TOKEN`

LLM planner value (recommended):

- `OPENAI_API_KEY` (used when `planner.llm_enabled` is true with default config)

Important API key mapping note:

1. The broker reads the key name defined by `planner.api_key_env_var`.
2. Default is `OPENAI_API_KEY`.
3. If you set `planner.api_key_env_var` to another name, `.env` must provide that exact env var.
4. There is no automatic aliasing between env var names.

Optional runtime/config values:

- `BROKER_CONFIG_PATH` (defaults to `./opamp_broker/config/broker.example.json` when using `start_broker` scripts)

Use the helper setup script if needed:

- Linux/macOS: `./scripts/configure_slack.sh`
- Windows PowerShell: `.\scripts\configure_slack.ps1`

### 2. `.env` vs `broker.json`

The broker intentionally uses both an environment file and a JSON config file.

Use `.env` for:

1. Secrets and deployment-specific credentials.
2. Values that differ per machine/environment.
3. Environment variable wiring (`BROKER_CONFIG_PATH`, API key env vars).

Typical `.env` values:

- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `SLACK_APP_TOKEN`
- `OPENAI_API_KEY`
- `BROKER_CONFIG_PATH`

Use `broker.json` for:

1. Broker runtime behavior and defaults.
2. Non-secret operational settings you want versioned/reviewed.
3. User-facing messages, timeouts, and planner/config paths.

Typical `broker.json` values:

- `broker.log_level`
- `messages.help`
- `messages.server_offline`
- `messages.slack_error_reply`
- `mcp.request_timeout_seconds`
- `mcp.connection_mode`
- `mcp.startup_discovery_max_attempts`
- `planner.model`
- `paths.opamp_config_path`

Why keep them separate:

1. Better security posture by keeping secrets out of committed config JSON.
2. Same `broker.json` can be reused across environments with different `.env` values.
3. Easier operations: rotate credentials without rewriting behavioral config.

### 3. Configure `broker.json`

The broker runtime config file is JSON and is loaded in this order:

1. `--config-path` CLI value (if provided)
2. `BROKER_CONFIG_PATH` environment variable (if set)
3. bundled default file: `opamp_broker/config/broker.example.json`

The file is merged with internal defaults, so you can provide a full file or a partial override.

If no config file is provided, the broker still starts using built-in defaults.
In that mode:

1. Runtime behavior falls back to default values from the loader.
2. OpAMP route derivation falls back to `http://localhost:8080` when no OpAMP config is found.
3. Planner falls back to deterministic rule-first mode if required AI key env var is missing.

Even with default config behavior, Slack credentials are still required for Slack mode:

- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `SLACK_APP_TOKEN`

Recommended minimum values to set explicitly:

1. `paths.opamp_config_path`
2. `social_collaboration.implementation`
3. `planner.provider`, `planner.base_url`, and `planner.api_key_env_var` if you are not using default AI service settings

Example `broker.json`:

```json
{
  "broker": {
    "name": "opamp-conversation-broker",
    "log_level": "INFO",
    "idle_timeout_seconds": 1200,
    "sweeper_interval_seconds": 30,
    "send_idle_goodbye": true,
    "send_shutdown_goodbye": true
  },
  "slack": {
    "command_name": "/opamp",
    "app_mention_enabled": true,
    "dm_enabled": true
  },
  "social_collaboration": {
    "implementation": "slack"
  },
  "messages": {
    "idle_goodbye": "I've been idle for a while, so I've cleared my working context for this thread. Reply here to start again.",
    "shutdown_goodbye": "I'm going to bed now, so I'm clearing my working context for this thread. When I wake up, please remind me what you want to do.",
    "restart_notice": "I'm awake again, but I don't have my earlier working context for this thread. Tell me what you want to check.",
    "server_offline": "The OpAMP server is currently offline. Please try again shortly.",
    "slack_error_reply": "soory a bit dizzy at the moment",
    "help": "Try `/opamp status collector-a`, `/opamp health collector-a`, or mention me with a question like `@OpAMP why is collector-a unhealthy?`"
  },
  "paths": {
    "opamp_project_root": "../fluent-opamp",
    "opamp_config_path": "../fluent-opamp/config/opamp.json"
  },
  "mcp": {
    "request_timeout_seconds": 30,
    "connection_mode": "auto",
    "protocol_version_attempts": ["2025-06-18", "2025-03-26"],
    "startup_discovery_max_attempts": 5,
    "startup_discovery_initial_backoff_seconds": 0.5,
    "startup_discovery_max_backoff_seconds": 5.0,
    "startup_discovery_backoff_multiplier": 2.0,
    "startup_discovery_jitter_seconds": 0.25
  },
  "planner": {
    "mode": "rule-first",
    "llm_enabled": true,
    "provider": "openai",
    "model": "gpt-5.2",
    "request_timeout_seconds": 30,
    "temperature": 0.0,
    "api_key_env_var": "OPENAI_API_KEY",
    "base_url": "https://api.openai.com/v1",
    "max_completion_tokens": 1024,
    "verify_max_completion_tokens_attempts": [64, 512],
    "prompts_config_path": "planner_prompts.json"
  }
}
```

Field reference:

1. `broker`
   Runtime behavior controls for logging level, idle timeout, and shutdown/idle message behavior.
2. `slack`
   Slack interaction behavior, including slash command name and whether mention/DM handlers are enabled.
3. `social_collaboration`
   Which social adapter to use at startup.
4. `messages`
   User-facing text for help, offline behavior, lifecycle messages, and Slack error fallback responses (`messages.slack_error_reply`).
5. `paths`
   File locations used to discover OpAMP provider/consumer settings. `paths.opamp_config_path` is the key value for deriving MCP route URLs.
6. `mcp`
   MCP client behavior, including connection strategy (`auto`/`json`/`sse`), protocol-version attempts, request timeout, and startup discovery retry/backoff controls.
7. `planner`
   AI planner behavior (provider, model, timeout, temperature, token limits, API key env var, base URL, and prompts file path).

### 4. Start the broker

Recommended startup commands:

- Linux/macOS: `./scripts/start_broker.sh`
- Windows PowerShell: `.\scripts\start_broker.ps1`

These scripts set:

- `PYTHONUNBUFFERED=1`
- `BROKER_CONFIG_PATH` (if not already set)

They also ensure dependencies are installed before launch by:

1. Creating/using `.venv`
2. Running `pip install -r requirements.txt`
3. Launching the broker runtime

They then call `run.sh`/`run.ps1` to start:

- `python -m opamp_broker.broker_app`

### Background service convenience scripts

If you want the broker to run in the background with a PID file:

- Linux/macOS start: `./scripts/start_broker_service.sh`
- Linux/macOS stop (graceful): `./scripts/stop_broker_service.sh`
- Windows start: `.\scripts\start_broker_service.ps1`
- Windows stop: `.\scripts\stop_broker_service.ps1`

Runtime artifact defaults:

1. PID file: `agent_broker/.broker/broker.pid`
2. Log file: `agent_broker/.broker/broker.log`
3. Windows stderr log file (PowerShell service start): `agent_broker/.broker/broker.log.err`

Optional environment overrides:

1. `BROKER_RUNTIME_DIR`
2. `BROKER_PID_FILE`
3. `BROKER_LOG_FILE`
4. `BROKER_ERR_LOG_FILE` (PowerShell service start only)
5. `BROKER_SHUTDOWN_TIMEOUT_SECONDS`

Shutdown behavior:

1. Linux/macOS stop script sends `SIGTERM` to allow graceful broker cleanup.
2. PowerShell stop script performs a best-effort graceful close first, then falls back to process stop if needed.

Windows note:

- If `.venv` was previously created from WSL/Linux (for example contains `bin/python` instead of `Scripts/python.exe`), `start_broker.ps1`/`run.ps1` will fall back to `python` on PATH instead of failing.

### 5. Broker CLI options

The broker supports runtime behavior selection from the command line.

Command format:

- `python -m opamp_broker.broker_app [OPTIONS]`

#### Option reference

1. `--config-path <path>`
   Use an explicit runtime config file instead of `BROKER_CONFIG_PATH` or bundled defaults.
   Example: `--config-path ./opamp_broker/config/broker.example.json`
2. `--social-collaboration <name>`
   Selects the social collaboration adapter implementation.
   Default: `slack`
   Current supported value: `slack`
   Resolution precedence: CLI value, then `social_collaboration.implementation` from config, then default `slack`.
3. `--verify-startup <mode>`
   Runs startup connectivity checks and exits without entering the long-running broker event loop.
   Allowed values: `none`, `social`, `ai_svc`, `all`
   Default: `none`
   Exit code behavior in verification mode: `0` when all requested checks pass, `1` when any requested check fails.

#### Verification modes

1. `social`
   Verifies connection/authentication for the selected social collaboration adapter (Slack by default).
2. `ai_svc`
   Verifies AI service connectivity/authentication using planner settings (`planner.model`, `planner.base_url`, and API key env var).
3. `all`
   Runs both `social` and `ai_svc` verification checks.

#### Verification output behavior

1. Logs per-check success/failure details.
2. Logs a final verification summary event.
3. Exits immediately after checks complete.

#### Examples

- Normal broker startup:
  `python -m opamp_broker.broker_app`
- Start with explicit adapter:
  `python -m opamp_broker.broker_app --social-collaboration slack`
- Start with explicit runtime config:
  `python -m opamp_broker.broker_app --config-path ./opamp_broker/config/broker.example.json`
- Check social adapter connectivity only:
  `python -m opamp_broker.broker_app --verify-startup social`
- Check AI service connectivity only:
  `python -m opamp_broker.broker_app --verify-startup ai_svc`
- Check both social adapter and AI service:
  `python -m opamp_broker.broker_app --verify-startup all`

#### Common dependency error

If startup fails with:

- `ModuleNotFoundError: No module named 'aiohttp'`

Install/update dependencies in your active environment:

- `pip install -r requirements.txt`

### 6. LLM planner configuration

The broker planner processes user requests using an LLM and is constrained to
the MCP tools currently discovered from the provider.

Planner config fields (in broker config JSON):

- `planner.llm_enabled` (default: `true`)
- `planner.provider` (default: `openai`)
- `planner.model` (default: `gpt-5.2`)
- `planner.request_timeout_seconds` (default: `30`)
- `planner.temperature` (default: `0.0`)
- `planner.api_key_env_var` (default: `OPENAI_API_KEY`)
- `planner.base_url` (default: `https://api.openai.com/v1`)
- `planner.max_completion_tokens` (default: `1024`)
- `planner.verify_max_completion_tokens_attempts` (default: `[64, 512]`)
- `planner.prompts_config_path` (default: `planner_prompts.json`)

`ai_svc` is a generic AI service label. By default it is configured for OpenAI.
To use a different compatible API, override:

- `planner.provider`
- `planner.base_url`
- `planner.api_key_env_var`

Supported provider values in this build:

- `openai` (default)
- `openai-compatible` / `openai_compatible` (alias of `openai`)
- `template` (scaffold only, intentionally non-runnable)

Ensure `.env` contains the env var named by `planner.api_key_env_var`.

Token settings:

1. `planner.max_completion_tokens` limits each planner call response budget.
2. `planner.verify_max_completion_tokens_attempts` controls retry token caps for startup verification.
3. Startup verification output includes configured token limits, attempt count, and token usage.

Prompt configuration:

1. Prompt text is loaded from the JSON file referenced by `planner.prompts_config_path`.
2. Required keys in that file are `system_prompt` and `verification_prompt`.
3. Prompt strings do not have code defaults; if the prompt file is missing or invalid, broker startup fails with a configuration error.
4. `system_prompt` controls response style. The bundled prompt is tuned so capability questions like `tools` / `what can you do` return tool descriptions and argument hints, not only tool names.

For extension details, see:

- [AI Provider Connection Extension Guide](./ai_provider_connections.md)

Runtime behavior:

1. If `llm_enabled=true` and API key is present, LLM planner is used.
2. If API key is missing, broker falls back to deterministic rule-based planning.
3. Tool execution remains restricted to discovered MCP tool names.

### 7. MCP connectivity configuration

Broker MCP connectivity is fixed to the OpAMP provider MCP endpoint derived at runtime:

- `<provider_base_url>/mcp`

If broker logs show `HTTP ... POST <provider_base_url>/mcp ... 404`, the provider is reachable but not exposing streamable HTTP MCP on `/mcp`.
With current provider builds, `/mcp` is exposed by default. If you still see 404:

1. Restart the provider with the latest code/build.
2. Confirm provider startup logs include MCP streamable HTTP exposure at `/mcp`.
3. Re-run broker startup or verification.

The broker uses provider MCP JSON-RPC calls in this sequence:

1. `initialize`
2. `tools/list`
3. `tools/call`

Supported MCP config fields:

- `mcp.request_timeout_seconds` (default: `30`)
- `mcp.connection_mode` (default: `auto`, supported: `auto`, `json`, `sse`)
- `mcp.protocol_version_attempts` (default: `["2025-06-18", "2025-03-26"]`)
- `mcp.startup_discovery_max_attempts` (default: `5`)
- `mcp.startup_discovery_initial_backoff_seconds` (default: `0.5`)
- `mcp.startup_discovery_max_backoff_seconds` (default: `5.0`)
- `mcp.startup_discovery_backoff_multiplier` (default: `2.0`)
- `mcp.startup_discovery_jitter_seconds` (default: `0.25`)

Connection behavior notes:

1. `connection_mode=auto` negotiates JSON or SSE response handling based on provider response content type.
2. `connection_mode=json` forces JSON body parsing and uses `Accept: application/json`.
3. `connection_mode=sse` forces streamed SSE parsing and uses `Accept: text/event-stream`.
4. Broker MCP mode must match provider/server behavior:
   - if provider responds with streamable HTTP/SSE (`text/event-stream`), use `sse` or `auto`
   - if provider responds with plain JSON (`application/json`), use `json` or `auto`
5. Forcing the wrong mode can cause decode/parsing failures even when the provider is reachable.

## Clean Shutdown

Use graceful termination so in-memory session cleanup and Slack shutdown messaging can run.

### Preferred

- Press `Ctrl+C` in the terminal (sends `SIGINT`)
- Or send `SIGTERM` to the process
- Or use convenience stop script on Linux/macOS: `./scripts/stop_broker_service.sh`
- Or use convenience stop script on Windows PowerShell: `.\scripts\stop_broker_service.ps1`

### Avoid

- Forcing termination with `SIGKILL` / `kill -9`

### What graceful shutdown does

On `SIGINT`/`SIGTERM`, the broker:

1. Stops the session sweeper task.
2. Optionally sends the configured `messages.shutdown_goodbye` text to active Slack threads.
3. Clears active in-memory sessions.
4. Closes the MCP client.
5. Cancels background tasks and exits.

Control shutdown message behavior with:

- `broker.send_shutdown_goodbye` in your broker config JSON.

## Logging Setup and Overrides

Broker logging is configured in the main entrypoint via Python `logging.config.dictConfig`.
`broker_logging.json` therefore follows the standard Python logging dictionary schema:

- https://docs.python.org/3/library/logging.config.html#logging-config-dictschema

### Default logging config file

By default, the broker loads:

- `opamp_broker/broker_logging.json`

### Override logging config file path

Set this environment variable to use a different logging config file:

- `OPAMP_BROKER_LOGGING_CONFIG`

Examples:

- Linux/macOS:
  - `export OPAMP_BROKER_LOGGING_CONFIG=/path/to/custom_broker_logging.json`
- Windows PowerShell:
  - `$env:OPAMP_BROKER_LOGGING_CONFIG = "C:\path\to\custom_broker_logging.json"`

### Runtime log level override

The broker config file field below can set runtime root logger level:

- `broker.log_level` (for example `DEBUG`, `INFO`, `WARNING`, `ERROR`)

Precedence behavior:

1. If a logging config file is present (`broker_logging.json` or `OPAMP_BROKER_LOGGING_CONFIG` path), that file is used as-is and `broker.log_level` is ignored.
2. When this happens, the broker logs a warning that `broker.log_level` was ignored due to file-based logging config.
3. If no logging config file is found, broker falls back to built-in logging config and applies `broker.log_level`.

### If config loading fails

If the custom logging config path is missing or invalid, the broker falls back to a built-in console logging configuration.
