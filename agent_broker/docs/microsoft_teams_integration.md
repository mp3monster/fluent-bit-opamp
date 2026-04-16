# Microsoft Teams Integration Blueprint

This document describes what is required to implement a Microsoft Teams alternative to the current Slack integration in `opamp_broker`.

## Current Status

The broker already supports a social collaboration abstraction layer:

1. Adapter interface: `opamp_broker/social_collaboration/base.py`
2. Adapter factory: `opamp_broker/social_collaboration/factory.py`
3. Current implementation: Slack adapter in `opamp_broker/social_collaboration/slack.py`
4. Startup selection in `opamp_broker/broker_app.py` via:
   - `--social-collaboration`
   - `social_collaboration.implementation` config
   - default `slack`

This means Teams can be added as a new adapter without changing graph, session, or MCP logic.

## Objective

Provide feature parity for broker chat workflows in Teams:

1. Receive prompts in channel and direct chat contexts.
2. Route prompts through the existing graph + MCP path.
3. Send normal responses, idle-timeout messages, and shutdown messages.
4. Preserve existing session semantics (`team_id`, `channel_id`, `thread_ts`, `user_id`).

## Implementation Work

## 1) Add Teams adapter module

Create a new module, for example:

- `opamp_broker/social_collaboration/teams.py`

Implement the same contract used by Slack:

1. `register_handlers(...)`
2. `start()`
3. `post_message(...)`

## 2) Extend factory selection

Update `opamp_broker/social_collaboration/factory.py`:

1. Add `teams` to supported implementations.
2. Instantiate a Teams adapter when `implementation == "teams"`.
3. Keep `slack` behavior unchanged.

## 3) Add Teams runtime config

Extend broker config defaults and example config:

1. Keep `social_collaboration.implementation` selector.
2. Add a new `teams` section for Teams-specific behavior/settings.

Possible config keys:

1. `teams.app_id`
2. `teams.tenant_id`
3. `teams.endpoint_path` (if self-hosted inbound endpoint path is configurable)
4. optional behavior toggles similar to Slack enable/disable switches

## 4) Add Teams credential/env handling

Define and validate required credentials for Teams runtime.

Typical values:

1. `TEAMS_APP_ID`
2. `TEAMS_APP_PASSWORD` (or cert-based auth equivalents)
3. optional cloud/authority overrides when required

## Teams Transport and Hosting Requirements

Unlike Slack Socket Mode, Teams bots usually rely on HTTPS callback delivery.

Expected work:

1. Expose an HTTPS endpoint for bot activities.
2. Validate/authenticate inbound activity requests.
3. Normalize activity payloads into broker session keys.
4. Preserve conversation reference metadata for proactive messages.

Operational implication:

1. Deployment model may need an internet-reachable HTTPS endpoint.
2. Local development may require a tunnel and callback registration.

## Message and Session Mapping

Normalize Teams payloads into broker context fields:

1. `team_id`: tenant/team scope identifier.
2. `channel_id`: conversation/channel identifier.
3. `thread_ts`: message thread key or stable conversation/message reference.
4. `user_id`: sender identity identifier.
5. `text`: cleaned text (remove mention artifacts before graph invocation).

For proactive broker messages (idle/shutdown), persist enough conversation-reference data so `post_message(...)` can target the original context.

## Command/UX Parity Decisions

Decide and document expected Teams UX behavior before implementation:

1. Slack slash-command equivalent strategy.
2. Mention handling behavior in channels.
3. DM behavior and defaults.
4. Response visibility model where Slack ephemeral behavior has no exact equivalent.

## Testing Plan

Add tests in these areas:

1. Unit tests for Teams activity normalization.
2. Unit tests for Teams adapter `post_message(...)` behavior.
3. Factory tests for `teams` selection and unsupported values.
4. Broker startup tests for adapter selection precedence (CLI > config > default).
5. Integration tests using representative Teams payload fixtures.

Regression requirement:

1. Existing Slack adapter tests must remain green.

## Documentation and Scripts

Add Teams-specific onboarding assets:

1. `docs/teams_configuration.md`
2. `scripts/configure_teams.sh`
3. `scripts/configure_teams.ps1`

Also update existing docs to reference that multiple social collaboration implementations are supported and Slack remains the default.

## Risks and Open Questions

1. Teams hosting/auth model is different from Slack Socket Mode and may change deployment topology.
2. Command UX in Teams is not 1:1 with Slack slash commands.
3. Multi-tenant identity and permissions policy may add complexity.
4. Proactive messaging depends on reliable conversation reference storage.
