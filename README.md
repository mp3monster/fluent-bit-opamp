# OpAMP Server & Supervisor for Fluent Bit & Fluentd

This repository hosts an implementation of the OpenTelemetry [Open Agent Management Protocol (OpAMP)](https://opentelemetry.io/docs/specs/opamp/). The OpAMP protocol allows us to perform tasks such as:

- manage & monitor any compliant agent
- Command and configure agents

The protocol is oriented towards agents supporting the observability domain such as OTel Collectors. The protocol does not mandate that the capabilities have to be directly embedded in the agent, infact the protocol documentation calls out explicitly the idea of a supervisor model, where a separate process manages the agent.

This repository provide an agent implementation that specifically adopts the supervisor model, but also understands the characteristics of Fluent Bit and Fluentd to service the different operations.

Here we have provided both the agent/client(supervisor) and server functionality. Although the protocol is defined in such a manner, that it should be possible to mix and match.

Aside from providing out of the box support for Fluent Bit and Fluentd it provides a means to extend and customize features including:

- Modifying the way an agent is supervised (so the supervisor could be something other than Fluentd or Fluent Bit).
- Dynamic deployment and execution of custom commands.
- Easy tailoring of several areas such as full status updates - given the 'openness of the spec'.

The following documentation provides more information, including the deployment and configuration of the server and client/agent. More detail on the design ideas, and how it the functionality could be further extended. As the protocol definition is very flexible (part of the protocol is an exchange of what client and server operations can be performed) we've identified which features are supported, and which aren't with suggestions on how the non-supported features could be addressed in a Fluentd / Fluent Bit context.

The documentation includes background such as the implementation philosophies that have informed the capability, such as being able to get something running quickly.

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
