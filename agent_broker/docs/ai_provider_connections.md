# AI Provider Connection Extension Guide

This document explains how the broker AI connection layer is abstracted and how
to add a new provider in future.

## Current architecture

The planner is split into two concerns:

1. `AISvcPlanner` decides planning prompts and output schema constraints.
2. `AIConnection` implementations handle provider-specific HTTP/auth behavior.

Factory selection happens in:

- `opamp_broker/planner/ai_connection_factory.py`

Current built-in provider:

- `openai` (OpenAI-compatible `/chat/completions` API)
- `template` (non-runnable scaffold for implementing a new provider)

## Runtime configuration

Planner settings in `broker.json`:

```json
{
  "planner": {
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

`provider` is resolved by the factory and used for both:

1. Runtime planner calls.
2. `--verify-startup ai_svc` connectivity verification.

Token usage logging:

1. Each planner call logs prompt/completion/total token usage.
2. Verification attempts log token usage per attempt.
3. Verification results include attempt count, token limits, and usage details.

Prompt loading:

1. Prompt strings are loaded from `planner.prompts_config_path`.
2. Required fields are:
   - `system_prompt`
   - `verification_prompt`
3. There are no in-code defaults for prompt strings.
4. Use `system_prompt` to tune conversational behavior (for example, richer capability responses that explain each discovered tool and expected arguments).

Template example:

```json
{
  "planner": {
    "provider": "template",
    "model": "gpt-5.2",
    "temperature": 0.0,
    "api_key_env_var": "MY_PROVIDER_API_KEY",
    "base_url": "https://example.invalid/v1",
    "prompts_config_path": "planner_prompts.json"
  }
}
```

`template` intentionally returns a non-ok verification result and does not run
planner traffic. It exists as a safe starting point.

## Adding a new provider

1. Add a new connection class implementing `AIConnection`:
   - File location suggestion: `opamp_broker/planner/<provider>_connection.py`
   - You can copy `opamp_broker/planner/template_ai_connection.py` as a baseline.
   - Required methods:
     - `has_api_key()`
     - `request_json_schema_completion(...)`
     - `verify_connection(...)`
2. Register the provider in `ai_connection_factory.py`:
   - Add alias mappings in `_PROVIDER_ALIASES`.
   - Extend `create_ai_connection(...)` with the new concrete class.
3. Add/update defaults as needed:
   - `opamp_broker/config/loader.py`
   - `opamp_broker/config/broker.example.json`
4. Add tests:
   - Factory provider selection and unsupported-provider handling.
   - Connection verification behavior.
   - Planner integration path (ensuring `AISvcPlanner` uses the connection).
5. Update docs:
   - This file.
   - `docs/broker_startup_and_shutdown.md` planner config section.

## Provider implementation notes

When implementing a new provider, keep these constraints:

1. Planner output must remain schema-constrained JSON and compatible with `sanitize_plan`.
2. Tool selection must remain limited to discovered MCP tools only.
3. Startup verification should return actionable errors for auth/network failures.
