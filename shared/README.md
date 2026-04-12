# Shared Utilities

This folder is the canonical source for cross-project OpAMP utility modules.

## What changed

To make the provider wheel self-contained, the provider now vendors copies of
runtime-required modules under:

- `provider/src/shared/`

The provider package no longer relies on an external `opamp-shared` dependency
at runtime.

## Why this was done

Provider code imports:

- `from shared.opamp_config import ...`
- `from shared.uuid_utils import ...`

When provider was launched in some MCP/client contexts, `shared` could be
missing from import resolution, leading to:

- `ModuleNotFoundError: No module named 'shared'`

Vendoring `shared` inside `provider/src` ensures those imports are present in
the built provider wheel artifact and in source-based launches that set
`PYTHONPATH` to `provider/src`.

## Sync note

`shared/` remains the source of truth. If you update:

- `shared/opamp_config.py`
- `shared/uuid_utils.py`

mirror the same changes into `provider/src/shared/` to keep provider runtime
and artifacts aligned.
