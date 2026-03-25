"""Print effective provider and consumer configuration."""

from __future__ import annotations

import logging
import pathlib
import sys


ROOT_PATH = pathlib.Path(__file__).resolve().parents[1]
PROVIDER_SRC = ROOT_PATH / "provider" / "src"
CONSUMER_SRC = ROOT_PATH / "consumer" / "src"
for path in (ROOT_PATH, PROVIDER_SRC, CONSUMER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from opamp_provider import config as provider_config  # noqa: E402
from opamp_consumer import config as consumer_config  # noqa: E402


def _repo_root() -> pathlib.Path:
    """Return repository root path."""
    return ROOT_PATH


def _ensure_repo_on_path() -> None:
    """No-op path helper retained for backward compatibility."""
    return None


def main() -> None:
    """Print key effective configuration values for provider and consumer."""
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    if provider_config is None:
        print("Provider config: unavailable (import failed)")
    else:
        print("Provider config:")
        print(f"  server_capabilities_mask: {provider_config.CONFIG.server_capabilities}")

    if consumer_config is None:
        print("Consumer config: unavailable (import failed)")
    else:
        print("Consumer config:")
        print(f"  server_url: {consumer_config.CONFIG.server_url}")
        print(f"  agent_config_path: {consumer_config.CONFIG.agent_config_path}")
        print(f"  agent_capabilities_mask: {consumer_config.CONFIG.agent_capabilities}")


if __name__ == "__main__":
    main()
