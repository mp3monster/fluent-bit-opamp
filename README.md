# OpAMP Workspace

This repository hosts a small OpAMP provider (server) and consumer (client) setup plus supporting tools, docs, and tests.

## Docs

- [docs/README.md](docs/README.md) — full setup and run instructions.
- [docs/index.md](docs/index.md) — documentation landing page and project overview.
- [docs/consumer_client_diagrams.md](docs/consumer_client_diagrams.md) — rendered consumer client diagrams with walkthrough notes.
- [docs/provider_server_diagrams.md](docs/provider_server_diagrams.md) — rendered provider/server diagrams with architecture walkthrough notes.
- [docs/features.md](docs/features.md) — feature notes and design direction.
- [docs/scripts.md](docs/scripts.md) — script reference table by platform.
- [consumer/README.md](consumer/README.md) — consumer configuration and CLI usage.
- [provider/README.md](provider/README.md) — provider configuration and web UI notes.

## Folder summary

- `config` — default configuration files (including `opamp.json`).
- `consumer` — the OpAMP consumer (client) package, tests, and config samples.
- `docs` — project documentation.
- `logs` — runtime logs created by scripts.
- `proto` — protobuf definitions and generated artifacts.
- `provider` — the OpAMP provider (server) package, UI, and tests.
- `scripts` — helper run and shutdown scripts.
- `shared` — shared utilities used by provider/consumer.
- `tests` — repository-level tests.
