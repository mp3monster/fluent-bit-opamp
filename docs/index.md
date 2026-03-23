# Documentation

Welcome to the OpAMP workspace docs. This page links to the core guides and outlines where to look for configuration, scripts, and feature notes.

## Core guides

- [docs/README.md](README.md) — full setup and run instructions (moved from root).
- [docs/features.md](features.md) — feature notes and design direction.
- [OpAMP posts on blog.mp3monster.org](https://blog.mp3monster.org/category/technology/fluent-observability/opamp/) — external blog posts and updates.
- [docs/command_process_implementation_note.md](command_process_implementation_note.md) — command API/queue/dispatch implementation details.
- [consumer/README.md](../consumer/README.md) — consumer configuration and CLI usage.
- [provider/README.md](../provider/README.md) — provider configuration and web UI notes.
- [shared/scripts/notes.md](../shared/scripts/notes.md) — shared script notes.
- [future_features.md](../future_features.md) — backlog and ideas for future work.

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
