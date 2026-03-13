"""CLI entrypoint for the OpAMP provider server."""

from __future__ import annotations

import argparse
import logging
import pathlib

from opamp_provider import config as provider_config
from opamp_provider.app import app


def main() -> None:
    """Load config overrides and start the Quart app."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", type=str)
    parser.add_argument("--server-capabilities", nargs="*")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4320)
    args = parser.parse_args()

    config = provider_config.load_config_with_overrides(
        config_path=pathlib.Path(args.config_path) if args.config_path else None,
        server_capabilities=args.server_capabilities,
    )
    provider_config.set_config(config)

logging.basicConfig(level=logging.DEBUG)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
