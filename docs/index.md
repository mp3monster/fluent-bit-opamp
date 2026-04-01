# Documentation

Welcome to the OpAMP workspace docs. This page links to the core guides and outlines where to look for configuration, scripts, and feature notes.

## Core guides

- [docs/README.md](README.md) — full setup and run instructions (moved from root).
- [docs/features.md](features.md) — feature notes and design direction.
- [OpAMP posts on blog.mp3monster.org](https://blog.mp3monster.org/category/technology/fluent-observability/opamp/) — external blog posts and updates.
- [docs/command_process_implementation_note.md](command_process_implementation_note.md) — command API/queue/dispatch implementation details.
- [docs/consumer_client_diagram.md](consumer_client_diagram.md) — consumer client architecture and runtime relationship diagrams.
- [docs/consumer_mixins.md](consumer_mixins.md) — how consumer mixins are composed, dispatched, and overridden.
- [docs/consumer_update_controllers.md](consumer_update_controllers.md) — how full update controllers drive reporting flags and outbound message field cadence.
- [docs/authentication.md](authentication.md) — bearer token auth modes, static-token setup, Keycloak/JWT setup, and MCP token usage.
- [docs/service_daemon_setup.md](service_daemon_setup.md) — running provider/consumer as `systemd` or Windows services, including Fluent Bit/Fluentd launch permissions.
- [docs/opamp_tofu_design.md](opamp_tofu_design.md) — design plan for adding TOFU protection to `/v1/opamp` without changing current endpoint behavior yet.
- [consumer/README.md](../consumer/README.md) — consumer configuration and CLI usage.
- [provider/README.md](../provider/README.md) — provider configuration and web UI notes.
- [docs/scripts.md](scripts.md) — script reference table by platform.
- [docs/features.md](features.md) — backlog and ideas for future work.

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
