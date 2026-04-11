# Implementation Philosophy

The following are the ideals that have tried to follow for this solution.

- Use Python 3 as this is typically already installed in the environments and secured.
- Support Fluent Bit and Fluentd in a supervisor model, so not invasive and can be used in default deployments.
- Minimal dependencies that need to be deployed in advance of the OpAMP solution e.g. no heavy DBs mandated. Aside from basic libraries for HTTP, JSON and app server any additional functionality should only be needed for use cases beyond the basics.
- Easy to get from 0 to something with minimal effort.
- Support the ChatOps concept described at [blog.mp3monster.org](https://blog.mp3monster.org/2026/03/23/opamp-with-fluent-bit/) - includes MCP exposure.
- Make it easy to extend and adapt.