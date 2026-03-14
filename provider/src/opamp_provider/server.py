# Copyright 2026 mp3monster.org
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    parser.add_argument("--host", type=str, default="127.0.0.1", help="bind address")
    parser.add_argument(
        "--port",
        type=int,
        help="port for the OpAMP provider/web UI (defaults to config webui_port)",
    )
    args = parser.parse_args()

    config = provider_config.load_config_with_overrides(
        config_path=pathlib.Path(args.config_path) if args.config_path else None,
        server_capabilities=args.server_capabilities,
    )
    provider_config.set_config(config)

    logging.basicConfig(level=logging.DEBUG)
    port = args.port if args.port is not None else config.webui_port
    app.run(host=args.host, port=port)


if __name__ == "__main__":
    main()
