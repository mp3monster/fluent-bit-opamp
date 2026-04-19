# OpAMP Conversation Broker

A standalone Python conversation broker that adds a conversational Slack surface to the
existing `fluent-opamp` MCP-enabled service.

## What it does

- Supports `/opamp` slash command
- Supports `@OpAMP` app mentions and direct-message chat
- Uses LangGraph for conversation management and planning
- Keeps short-lived conversation state in memory
- Expires idle threads and posts a polite sign-off
- Sends an explicit "going to bed" message on shutdown
- Reads the existing `fluent-opamp/config/opamp.json`
- Discovers MCP tools dynamically from the OpAMP provider
- Uses fixed OpAMP provider MCP JSON-RPC calls (`initialize`, `tools/list`, `tools/call`)
- Uses an LLM planner to interpret requests and choose from discovered tools only
- Uses structured JSON logging via Python's `logging`

## Project layout

- `opamp_broker/` application package
- `scripts/` helper scripts for run/package
- `docs/` design and transcript documents
  - docs index: `docs/README.md`
- `.broker/` runtime artifacts (created by service/start scripts)

## Folder purposes (agent_broker root)

- `docs/`: operational and design documentation, including setup/runbooks and architecture diagrams.
- `opamp_broker/`: main broker Python package and runtime entrypoint.
- `opamp_broker/config/`: broker runtime configuration and static config artifacts (for example broker defaults and Slack manifest).
- `opamp_broker/graph/`: conversation graph assembly, planning logic, and execution flow wiring.
- `opamp_broker/mcp/`: MCP transport client and tool registry integration used to call provider tools.
- `opamp_broker/session/`: in-memory session lifecycle management and idle-session sweeper logic.
- `opamp_broker/social_collaboration/`: abstract social-collaboration adapter interface and adapter factory.
- `opamp_broker/social_collaboration/adapters/`: concrete social-collaboration adapter implementations (for example Slack).
- `opamp_broker/slack/`: Slack-specific client and handler implementation used by the Slack social-collaboration adapter.
- `opamp_broker/utils/`: shared utility helpers used by broker modules.
- `scripts/`: helper scripts for Slack setup plus broker start/run workflows on Linux/macOS and Windows.
- `.broker/`: runtime state and logs when using service scripts (for example `broker.pid`, `broker.log`, `broker.log.err`).

## Pre-requisites

- Python 3.11+
- Slack app credentials:
  - bot token
  - signing secret
  - app token (for Socket Mode)
- Access to the existing `fluent-opamp` project checkout
- Network reachability from the broker to the provider's MCP endpoints
- `OPENAI_API_KEY` for LLM-backed planning (when `planner.llm_enabled=true`)

`ai_svc` naming is provider-neutral. Defaults target OpenAI:

- `planner.provider=openai`
- `planner.base_url=https://api.openai.com/v1`
- `planner.api_key_env_var=OPENAI_API_KEY`
- `planner.temperature=0.0`
- `planner.max_completion_tokens=1024`
- `planner.verify_max_completion_tokens_attempts=[64, 512]`
- `planner.prompts_config_path=planner_prompts.json`

## Recommended Slack scopes

- `app_mentions:read`
- `channels:history`
- `chat:write`
- `commands`
- `groups:history`
- `im:history`
- `im:write`
- `mpim:history`

## Quick start

1. Copy `opamp_broker/config/broker.example.json` to a runtime file, or rely on defaults.
2. Point `paths.opamp_config_path` at the existing `fluent-opamp/config/opamp.json`.
3. Configure Slack and env values:
   - Linux/macOS: `./scripts/configure_slack.sh`
   - Windows PowerShell: `.\scripts\configure_slack.ps1`
   - Manual guide: `docs/slack_configuration.md`
4. Export your LLM API key (recommended for tool-constrained LLM planning):
   - Linux/macOS: `export OPENAI_API_KEY=...`
   - Windows PowerShell: `$env:OPENAI_API_KEY = \"...\"`
   - The broker reads the env var named by `planner.api_key_env_var` (default `OPENAI_API_KEY`).
   - If you switch `planner.api_key_env_var` to a different key name, set that exact variable in `.env`/environment.
   - If you use a non-default provider, also set `planner.provider` in broker config.
5. Install dependencies:
   - `python -m venv .venv`
   - activate the venv
   - `pip install -r requirements.txt`
6. Run:
   - Preferred startup scripts (also ensure dependencies are installed each run):
     - Linux/macOS foreground: `./scripts/start_broker.sh`
     - Windows PowerShell foreground: `.\scripts\start_broker.ps1`
     - Linux/macOS background service mode: `./scripts/start_broker.sh --service`
     - Windows PowerShell background service mode: `.\scripts\start_broker.ps1 -Service`
   - Stop service mode:
     - Linux/macOS: `./scripts/stop_broker_service.sh`
     - Windows PowerShell: `.\scripts\stop_broker_service.ps1`
   - Optional explicit adapter selection: `python -m opamp_broker.broker_app --social-collaboration slack`
   - Optional startup verification only: `python -m opamp_broker.broker_app --verify-startup social`
   - Optional AI service verification only: `python -m opamp_broker.broker_app --verify-startup ai_svc`
   - Optional full startup verification: `python -m opamp_broker.broker_app --verify-startup all`
7. Operational docs:
   - startup/shutdown + logging: `docs/broker_startup_and_shutdown.md`
   - AI provider extension guide: `docs/ai_provider_connections.md`
   - code structure diagrams: `docs/broker_code_structure.md`
   - documentation index: `docs/README.md`

## Notes

- This broker is intentionally stateless across restarts except for Slack-visible thread history.
- In-memory thread state is cleared after the configured idle timeout.
- On shutdown the broker tells active threads it is "going to bed" and clears working context.
- MCP connectivity is intentionally simplified to the provider `/mcp` endpoint and supports configurable connection strategy (`auto`/`json`/`sse`), protocol version attempts, timeout, and startup discovery retry/backoff via `mcp.*` settings.
- Ensure broker `mcp.connection_mode` aligns with provider response mode (SSE/streaming vs JSON). `auto` is recommended unless you explicitly need to force one mode.
- Agent filters can be passed directly to the discovered listing tool, for example:
  - `/opamp tool_otel_agents service_instance_id=checkout host_name=prod-node invert_filter=true`
  - `/opamp show agents host_ip=10.0.0.5 client_version=1.2`
