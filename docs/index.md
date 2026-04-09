# Documentation

Welcome to the OpAMP workspace docs. This page links to the core guides and outlines where to look for configuration, scripts, and feature notes.

## Core guides

- [docs/README.md](README.md) — full setup and run instructions (moved from root).
- [docs/features.md](features.md) — feature notes and design direction.
- [OpAMP posts on blog.mp3monster.org](https://blog.mp3monster.org/category/technology/fluent-observability/opamp/) — external blog posts and updates.
- [docs/command_process_implementation_note.md](command_process_implementation_note.md) — command API/queue/dispatch implementation details.
- [docs/consumer_client_diagram.md](consumer_client_diagram.md) — consumer client architecture and runtime relationship diagrams.
- [docs/consumer_client_diagrams.md](consumer_client_diagrams.md) — rendered consumer diagrams with explanation per diagram panel.
- [docs/provider_server_diagram.md](provider_server_diagram.md) — provider/server Mermaid source diagrams.
- [docs/provider_server_diagrams.md](provider_server_diagrams.md) — rendered provider/server diagrams plus links to auth, endpoints, and command docs.
- [docs/consumer_mixins.md](consumer_mixins.md) — how consumer mixins are composed, dispatched, and overridden.
- [docs/consumer_update_controllers.md](consumer_update_controllers.md) — how full update controllers drive reporting flags and outbound message field cadence.
- [docs/authentication.md](authentication.md) — bearer token auth modes, static-token setup, Keycloak/JWT setup, and MCP token usage.
- [docs/self_signed_tls_setup.md](self_signed_tls_setup.md) — generate local self-signed cert/key and apply config values for HTTPS testing.
- [docs/api_gateway_requirements.md](api_gateway_requirements.md) — recommended API gateway controls, internal vs external client profiles, and required auth/route hardening updates.
- [docs/service_daemon_setup.md](service_daemon_setup.md) — running provider/consumer as `systemd` or Windows services, including Fluent Bit/Fluentd launch permissions.
- [consumer/README.md](../consumer/README.md) — consumer configuration and CLI usage.
- [provider/README.md](../provider/README.md) — provider configuration and web UI notes.
- [provider state restore notes](../provider/README.md#state-persistence-and-restore) — snapshot naming, `--restore` usage, fallback behavior, and retention.
- [docs/scripts.md](scripts.md) — script reference table by platform.

## Project layout (quick view)

- `config` — default configuration files (including `opamp.json`).
- `consumer` — the OpAMP consumer (client) package, tests, and config samples.
- `docs` — project documentation.
- `logs` — runtime logs created by scripts.
- `proto` — protobuf definitions and generated artifacts.
- `provider` — the OpAMP provider (server) package, UI, and tests.
- `scripts` — helper run and shutdown scripts.
- `shared` — shared utilities used by provider/consumer.
- `src` — top-level Python package glue (if needed for tooling).
- `tests` — repository-level tests.
