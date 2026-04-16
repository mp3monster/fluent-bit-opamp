# Documentation

Welcome to the Fluent Bit & Fluentd OpAMP implementation docs. This page links to the core guides and outlines where to look for configuration, scripts, and feature notes.

## Core guides

- [Setup README](README.md) — full setup and run instructions.
- [Features - spec alignment](features.md) — feature notes and design direction.
- [UI examples](screenshots.md) - Some of the elements of the UI to illustrate the user experience.
- [Design & Implementation principles]().
- [Command_process_implementation_notes](command_process_implementation_note.md) — command API/queue/dispatch implementation details.
- [How to add_your_own_custom_action](adding_your_own_custom_action.md) — how to implement and deploy a custom provider+consumer action using `nullcommand` as the baseline.
- [Client (consumer)_diagram (in Mermaid format)](consumer_client_diagram.md) — consumer client architecture and runtime relationship diagrams.
- [Client (consumer)_diagrams (as images)](consumer_client_diagrams.md) — rendered consumer diagrams with explanation per diagram panel.
- [Server (provider)_server_diagrams (in Mermaid format)](provider_server_diagram.md) — provider/server Mermaid source diagrams.
- [Server_(provider) diagrams (as images)](provider_server_diagrams.md) — rendered provider/server diagrams plus links to auth, endpoints, and command docs.
- [Client (consumer) use of mixins](consumer_mixins.md) — how consumer mixins are composed, dispatched, and overridden.
- [Client (consumer)_update_controllers](consumer_update_controllers.md) — how full update controllers drive reporting flags and outbound message field cadence.
- [Authentication](authentication.md) — bearer token auth modes, static-token setup, Keycloak/JWT setup, and MCP token usage.
- [Web Endpoints](endpoints.md) — provider endpoint inventory, including UI/API/tool/MCP routes and `/doc-set`.
- [Self_signed_TLS_setup](self_signed_tls_setup.md) — generate local self-signed cert/key and apply config values for HTTPS testing.
- [API_gateway_suggested use and requirements](api_gateway_requirements.md) — recommended API gateway controls, internal vs external client profiles, and required auth/route hardening updates.
- [Service_daemon_setup](service_daemon_setup.md) — running provider/consumer as `systemd` or Windows services, including Fluent Bit/Fluentd launch permissions.
- [Client README](../consumer/README.md) — client/agent (aka consumer) configuration and CLI usage.
- [Server README](../provider/README.md) — server (aka provider) configuration and web UI notes.
- [Server state persistence](../provider/README.md#state-persistence-and-restore) — snapshot naming, `--restore` usage, fallback behavior, and retention.
- [MCP scripts and usage](../mcp/README.md) — MCP wrapper/canonical script behavior, FastMCP client role, command-line parameters, and verification.
- [Agent broker README](../agent_broker/README.md) — optional standalone conversation broker overview and run steps.
- [Agent broker docs index](../agent_broker/docs/README.md) — broker runbooks (startup/shutdown/logging, Slack setup, architecture notes).
- [Scripts](scripts.md) — script reference table by platform.

## Optional components

- `agent_broker` is optional and runs as a separate process.
- Provider/server and consumer/client do not require the broker to run.
- If used, start and stop the broker independently from provider and consumer.

## Project layout (quick view)

- `agent_broker` — optional standalone conversation broker package and docs.
- `config` — default configuration files (including `opamp.json`).
- `consumer` — the OpAMP consumer (client) package, tests, and config samples.
- `dist` — SBOM (Software Bill of Materials) and Wheel files
- `docs` — project documentation.
- `logs` — runtime logs created by scripts.
- `server-state` — state snapshot folder created when provider state persistence writes snapshots (folder name follows `provider.state_persistence.state_file_prefix` parent path).
- `proto` — protobuf definitions and generated artifacts.
- `provider` — the OpAMP provider (server) package, UI, and tests.
- `scripts` — helper run and shutdown scripts.
- `shared` — shared utilities used by provider/consumer.
- `src` — top-level Python package glue (if needed for tooling).
- `tests` — repository-level tests.

## Reference 3rd Party Documents

- [Open Agent Management Protocol (OpAMP) Specification](https://opentelemetry.io/docs/specs/opamp/)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/specification/2025-11-25) specification - optional feature
- [Fluentd](https://www.fluentd.org/)
- [Fluent Bit](https://fluentbit.io/)
- [Quart](https://quart.palletsprojects.com/en/latest/) (foundation of the implementation)
- [HAProxy](https://www.haproxy.com/) (optional feature, to support advanced security permutations)
- [OpAMP posts on blog.mp3monster.org](https://blog.mp3monster.org/category/technology/fluent-observability/opamp/) — external blog posts and updates.
