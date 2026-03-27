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
import os

from opamp_provider import config as provider_config
from opamp_provider.app import app
from opamp_provider.state import STORE


def main() -> None:
    """Load config overrides and start the Quart app."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", type=str)
    parser.add_argument("--host", type=str, default="127.0.0.1", help="bind address")
    parser.add_argument(
        "--port",
        type=int,
        help="port for the OpAMP provider/web UI (defaults to config webui_port)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        help="logging level name override (for example DEBUG, INFO, WARNING)",
    )
    args = parser.parse_args()
    effective_config_path = provider_config.get_effective_config_path(args.config_path)
    logging.getLogger(__name__).info(
        "using provider config path: %s",
        effective_config_path,
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(effective_config_path)

    config = provider_config.load_config_with_overrides(
        config_path=effective_config_path,
        log_level=args.log_level,
    )
    provider_config.set_config(config)
    STORE.set_default_heartbeat_frequency(
        config.default_heartbeat_frequency,
        max_events=config.client_event_history_size,
    )

    resolved_log_level = provider_config.resolve_log_level(config.log_level)
    root_logger = logging.getLogger()
    # Do not force-reconfigure handlers here. In tests/tools, handlers may be
    # preinstalled (for capture), and replacing them can break stream lifecycle.
    if not root_logger.handlers:
        logging.basicConfig(level=resolved_log_level)
    else:
        root_logger.setLevel(resolved_log_level)
    port = args.port if args.port is not None else config.webui_port
    app.run(host=args.host, port=port)


if __name__ == "__main__":
    main()
