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
import json
import sys

from opamp_provider import config as provider_config
from opamp_provider.app import app, set_state_restore_status
from opamp_provider.state import STORE
from opamp_provider.state_persistence import (
    RESTORE_AUTO,
    resolve_restore_snapshot_path,
    restore_state_snapshot,
)


def _provider_tls_run_kwargs(config: provider_config.ProviderConfig) -> dict[str, str]:
    """Return Quart TLS run kwargs for configured provider TLS settings."""
    tls_config = config.tls
    if tls_config is None:
        return {}
    return {
        "certfile": tls_config.cert_file,
        "keyfile": tls_config.key_file,
    }


def main() -> None:
    """Load config overrides and start the Quart app."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", type=str)
    # Intentionally omitted from CLI help/documentation.
    parser.add_argument("--diagnostic", action="store_true", help=argparse.SUPPRESS)
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
    parser.add_argument(
        "--restore",
        nargs="?",
        const=RESTORE_AUTO,
        default=None,
        metavar="SNAPSHOT_FILE",
        help="restore persisted provider state from latest snapshot or explicit file path",
    )
    args = parser.parse_args()
    root_logger = logging.getLogger()
    # Bootstrap startup logs before config load/restore so manual runs always show
    # config path + restore decisions even when no handlers were preconfigured.
    if not root_logger.handlers:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    else:
        root_logger.setLevel(logging.INFO)
    effective_config_path = provider_config.get_effective_config_path(args.config_path)
    logger = logging.getLogger(__name__)
    logger.info(
        "using provider config path: %s",
        effective_config_path,
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(effective_config_path)
    log_level_override = "DEBUG" if args.diagnostic else args.log_level

    try:
        config = provider_config.load_config_with_overrides(
            config_path=effective_config_path,
            log_level=log_level_override,
        )
    except Exception as exc:
        logger.warning(
            "failed loading provider config file path=%s",
            effective_config_path,
            exc_info=exc,
        )
        raise
    provider_config.set_config(config)
    logger.info(
        "state persistence file prefix: %s",
        config.state_persistence.state_file_prefix,
    )
    STORE.set_default_heartbeat_frequency(
        config.default_heartbeat_frequency,
        max_events=config.client_event_history_size,
        record_event=False,
    )

    if args.restore is None:
        set_state_restore_status("not_requested")
        logger.info(
            "state restore not requested; server will start with empty in-memory state"
        )
    elif config.state_persistence.enabled is not True:
        set_state_restore_status(
            "skipped",
            "state persistence disabled; restore request ignored",
        )
        logger.warning(
            "restore requested but state persistence is disabled"
        )
        logger.info(
            "state restore skipped; server will start with empty in-memory state"
        )
    else:
        try:
            restore_path = resolve_restore_snapshot_path(
                state_file_prefix=config.state_persistence.state_file_prefix,
                restore_option=args.restore,
            )
        except FileNotFoundError as exc:
            set_state_restore_status("missing", str(exc))
            logger.warning(
                "restore requested but snapshot missing: %s",
                exc,
            )
            logger.info(
                "state restore fallback: no snapshot file available, starting with empty in-memory state"
            )
        else:
            logger.info("state restore using snapshot file: %s", restore_path)
            try:
                summary = restore_state_snapshot(
                    store=STORE,
                    snapshot_path=restore_path,
                    logger=logger,
                )
                set_state_restore_status("restored", json.dumps(summary, sort_keys=True))
            except FileNotFoundError as exc:
                set_state_restore_status("missing", str(exc))
                logger.warning(
                    "restore snapshot missing: %s",
                    exc,
                )
                logger.info(
                    "state restore fallback: no snapshot file available, starting with empty in-memory state"
                )
            except Exception as exc:
                set_state_restore_status("failed", str(exc))
                logger.warning(
                    "failed restoring provider state from %s",
                    restore_path,
                    exc_info=exc,
                )
                logger.info(
                    "state restore fallback: invalid/corrupt snapshot, starting with empty in-memory state"
                )

    resolved_log_level = provider_config.resolve_log_level(config.log_level)
    root_logger = logging.getLogger()
    # Do not force-reconfigure handlers here. In tests/tools, handlers may be
    # preinstalled (for capture), and replacing them can break stream lifecycle.
    if not root_logger.handlers:
        logging.basicConfig(level=resolved_log_level, stream=sys.stdout)
    else:
        root_logger.setLevel(resolved_log_level)
    app.config["DIAGNOSTIC_MODE"] = bool(args.diagnostic)
    port = args.port if args.port is not None else config.webui_port
    app.run(
        host=args.host,
        port=port,
        **_provider_tls_run_kwargs(config),
    )


if __name__ == "__main__":
    main()
