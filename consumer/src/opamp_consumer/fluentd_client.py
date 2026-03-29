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

"""Fluentd-specific OpAMP consumer implementation."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import logging
import pathlib
import re
import subprocess
import sys
import time
import tracemalloc

from opamp_consumer import config as consumer_config
from opamp_consumer.client import (
    AbstractOpAMPClient,
    CONFIG_DOCS_URL,
    KEY_SERVICE_INSTANCE_ID_COMMENT,
    KEY_SERVICE_TYPE,
    LOCALHOST_BASE,
    run_client,
    resolve_service_instance_id_template,
)
from opamp_consumer.config import CFG_AGENT_CONFIG_PATH, ConsumerConfig
from opamp_consumer.proto import opamp_pb2

FLUENTD_CMD = "fluentd"  # Executable used to launch Fluentd.
FLUENTD_CONFIG_FLAG = "-c"  # CLI flag for Fluentd config file path.
FLUENTD_VERSION_FLAG = "--version"  # CLI flag that prints Fluentd version.
VALUE_AGENT_TYPE_FLUENTD = "Fluentd"  # Agent type value reported in AgentDescription.
KEY_FLUENTD_PORT = "port"  # Fluentd monitor-agent config key for HTTP port.
KEY_FLUENTD_BIND = "bind"  # Fluentd monitor-agent config key for listen/bind host.
KEY_AGENT_DESCRIPTION = "agent_description"  # Comment key for agent description metadata.
CONFIG_PATH_ARGS = ("--config-path",)  # Supported CLI aliases for config file path.
AGENT_CONFIG_PATH_ARGS = ("--agent-config-path", "--fluentd-config-path")  # CLI aliases for fluentd config path.
AGENT_ADDITIONAL_ARGS = ("--agent-additional-params", "--additional-fluentd-params")  # CLI aliases for extra Fluentd args.

_FLUENTD_MONITOR_AGENT_KV = re.compile(
    r"^\s*(?P<key>port|bind)\s+(?P<value>\S.*)$",
    re.IGNORECASE,
)
_COMMENT_KV = re.compile(
    rf"^\s*#\s*(?P<key>{KEY_AGENT_DESCRIPTION}|{KEY_SERVICE_INSTANCE_ID_COMMENT})\s*"
    r"[:=]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)


def _config_parameters_payload(config: ConsumerConfig) -> dict[str, object]:
    """Build config parameters payload with documentation URL."""
    config_params: dict[str, object] = asdict(config)
    config_params["documentation_url"] = CONFIG_DOCS_URL
    return config_params


def _apply_fluentd_comment(
    config: consumer_config.ConsumerConfig,
    logger: logging.Logger,
    match: re.Match[str],
) -> None:
    """Apply supported metadata comments to the consumer config."""
    key = match.group("key").lower()
    value = match.group("value").strip()
    if key == KEY_SERVICE_INSTANCE_ID_COMMENT:
        value = resolve_service_instance_id_template(value)
    config[key] = value
    logger.info("located fluentd comment >%s< with value >%s<", key, value)


def load_fluentd_config(config: consumer_config.ConsumerConfig) -> ConsumerConfig:
    """Load Fluentd monitor-agent values and metadata into the config object."""
    logger = logging.getLogger(__name__)
    path = config.agent_config_path
    if not path:
        raise ValueError(f"{CFG_AGENT_CONFIG_PATH} is not set")

    with open(path, encoding=consumer_config.UTF8_ENCODING) as handle:
        for raw_line in handle:
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue

            comment_match = _COMMENT_KV.match(raw_line)
            if comment_match is not None:
                _apply_fluentd_comment(config, logger, comment_match)
                continue

            fluentd_match = _FLUENTD_MONITOR_AGENT_KV.match(raw_line)
            if fluentd_match is None:
                continue

            key = fluentd_match.group("key").lower()
            value = fluentd_match.group("value").strip()
            if key == KEY_FLUENTD_PORT:
                parsed_port = int(value)
                config.client_status_port = parsed_port
                config.agent_http_port = parsed_port
                config.agent_http_server = "on"
            elif key == KEY_FLUENTD_BIND:
                config.agent_http_listen = value
            logger.info("located fluentd setting >%s< with value >%s<", key, value)

    return config


class FluentdOpAMPClient(AbstractOpAMPClient):
    """Concrete OpAMP client implementation for Fluentd-based agents."""

    def __init__(self, base_url: str, config: ConsumerConfig | None = None) -> None:
        """Initialize client and set agent-type metadata to Fluentd."""
        super().__init__(base_url, config)
        self.data.agent_type_name = VALUE_AGENT_TYPE_FLUENTD

    def get_custom_handler_folder(self) -> pathlib.Path:
        """Return the default custom-handler folder bundled with the consumer."""
        return pathlib.Path(__file__).resolve().parent / "custom_handlers"

    def launch_agent_process(self) -> bool:
        """Launch the Fluentd process using configured params."""
        logger = logging.getLogger(__name__)
        command = [
            FLUENTD_CMD,
            *(self.config.agent_additional_params or []),
            FLUENTD_CONFIG_FLAG,
            self.config.agent_config_path,
        ]
        logger.debug("About to start Fluentd with cmd %s", command)
        with self.data.process_lock:
            process_response: subprocess.Popen[bytes] = subprocess.Popen(command)
            self.data.agent_process = process_response
            self.data.launched_at = time.time_ns()
        logger.info("Fluentd launch result = %s", process_response)
        return True

    def add_agent_version(self, port: int) -> None:
        """Load Fluentd version text from the local `fluentd --version` command."""
        del port  # Unused for Fluentd version retrieval.
        logger = logging.getLogger(__name__)
        try:
            raw_version = subprocess.check_output(
                [FLUENTD_CMD, FLUENTD_VERSION_FLAG],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
            if not raw_version:
                return
            version_text = raw_version
            normalized = raw_version.lower()
            if normalized.startswith("fluentd "):
                version_text = raw_version.split(" ", 1)[1].strip()
            self.data.agent_version = version_text
            self.data.agent_type_name = VALUE_AGENT_TYPE_FLUENTD
        except Exception as err:  # pragma: no cover - system-dependent command availability
            logger.warning("failed to parse Fluentd version response: %s", err)

    def _health_from_metrics(
        self, msg: opamp_pb2.AgentToServer, text: str
    ) -> opamp_pb2.AgentToServer:
        """Return health unchanged for Fluentd metrics payloads.

        Fluentd metrics formats vary by plugin/endpoint; this implementation keeps
        the default heartbeat health behavior and leaves component-level health
        map enrichment to future Fluentd-specific parsing.
        """
        del text
        return msg

    def get_agent_description(
        self, instance_uid: bytes | str | None = None
    ) -> opamp_pb2.AgentDescription:
        """Build agent description and override service type to Fluentd."""
        description = super().get_agent_description(instance_uid)
        for attribute in description.identifying_attributes:
            if attribute.key == KEY_SERVICE_TYPE:
                attribute.value.string_value = VALUE_AGENT_TYPE_FLUENTD
                break
        return description


def main() -> None:
    """Load config, read Fluentd settings, launch Fluentd, and start heartbeat."""
    try:
        tracemalloc.start()
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("-h", "--help", action="store_true")
        parser.add_argument(*CONFIG_PATH_ARGS, type=str)
        parser.add_argument("--server-url", type=str)
        parser.add_argument("--server-port", type=int)
        parser.add_argument(*AGENT_CONFIG_PATH_ARGS, dest="agent_config_path", type=str)
        parser.add_argument(
            *AGENT_ADDITIONAL_ARGS,
            dest="agent_additional_params",
            nargs="*",
        )
        parser.add_argument("--heartbeat-frequency", type=int)
        parser.add_argument(
            "--log-level",
            type=str,
            help="logging level name override (for example DEBUG, INFO, WARNING)",
        )
        parser.add_argument(
            "--full-update-controller",
            type=str,
            help='JSON string for full update controller (for example {"fullResendAfter":1})',
        )
        args = parser.parse_args()
        effective_config_path = consumer_config.get_effective_config_path(
            args.config_path
        )
        logging.getLogger(__name__).info(
            "using consumer config path: %s",
            effective_config_path,
        )

        config = consumer_config.load_config_with_overrides(
            config_path=effective_config_path,
            server_url=args.server_url,
            server_port=args.server_port,
            agent_config_path=args.agent_config_path,
            agent_additional_params=args.agent_additional_params,
            heartbeat_frequency=args.heartbeat_frequency,
            log_level=args.log_level,
            full_update_controller=args.full_update_controller,
        )
        resolved_log_level = consumer_config.resolve_log_level(config.log_level)
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            logging.basicConfig(level=resolved_log_level)
        else:
            root_logger.setLevel(resolved_log_level)
        logger = logging.getLogger(__name__)

        if args.help:
            print(
                json.dumps(
                    _config_parameters_payload(config),
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        config = load_fluentd_config(config)
        if config.client_status_port is None:
            raise ValueError("client_status_port not found in Fluentd config")

        if config.server_url is None and config.server_port is not None:
            config.server_url = f"{LOCALHOST_BASE}:{config.server_port}"
        if config.server_url is None:
            raise ValueError("server_url is not configured")

        logger.debug("setting up OpAMP Fluentd client")
        client = FluentdOpAMPClient(config.server_url, config)
        client.launch_agent_process()
        client.add_agent_version(config.client_status_port)
        logger.info("introducing fluentd client to server")
        asyncio.run(run_client(client))
        asyncio.run(client._heartbeat_loop(config.client_status_port))
        client.terminate_agent_process()
    except KeyboardInterrupt as keyboard_interrupt:
        print("... bzzzz keyboard\n %s", keyboard_interrupt)
    except SystemExit as system_exit:
        print("... bzzzz brutal exit\n %s", system_exit)
    except Exception:
        print("... bzzzzzzzzzzz")


if __name__ == "__main__":
    main()
    print("... Bye")
    sys.exit(1)
