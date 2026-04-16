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

"""Bootstrap and config-loading helpers for the default OpAMP client."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import logging.config
import os
import pathlib
import re
import socket
import sys
import threading
import tracemalloc
import uuid
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from opamp_consumer import config as consumer_config
from opamp_consumer.config import CFG_AGENT_CONFIG_PATH, ConsumerConfig
from opamp_consumer.proto import opamp_pb2
from shared.opamp_config import UTF8_ENCODING

KEY_AGENT_DESCRIPTION = "agent_description"  # Comment key carrying free-form agent description.
KEY_CONFIG_VERSION_COMMENT = (
    "config_version"  # Comment key for agent configuration version metadata.
)
KEY_SERVICE_INSTANCE_ID_COMMENT = (
    "service_instance_id"  # Comment key for service instance template.
)
KEY_HTTP_PORT = "http_port"  # Fluent Bit/agent config key for local status HTTP port.
KEY_HTTP_LISTEN = "http_listen"  # Fluent Bit/agent config key for bind/listen address.
KEY_HTTP_SERVER = "http_server"  # Fluent Bit/agent config key that enables HTTP server support.
TOKEN_IP = "__IP__"  # Template token replaced with resolved local IP.
TOKEN_HOSTNAME = "__hostname__"  # Template token replaced with local hostname.
TOKEN_MAC_ADDR = "__mac-ad__"  # Template token replaced with local MAC address.
MATCH_GROUP_KEY = "key"  # Regex named group containing parsed config/comment key.
MATCH_GROUP_VALUE = "value"  # Regex named group containing parsed config/comment value.
AGENT_CONFIG_KEYS_PATTERN = (
    f"{KEY_HTTP_PORT}|{KEY_HTTP_LISTEN}|{KEY_HTTP_SERVER}"
)  # Regex alternation for supported Fluent Bit HTTP keys.

_COMMENT_KV = re.compile(
    rf"^\s*#\s*(?P<{MATCH_GROUP_KEY}>{KEY_AGENT_DESCRIPTION}|{KEY_CONFIG_VERSION_COMMENT}|{KEY_SERVICE_INSTANCE_ID_COMMENT})\s*"
    rf"[:=]\s*(?P<{MATCH_GROUP_VALUE}>.+?)\s*$",
    re.IGNORECASE,
)
_AGENT_CONFIG_KV = re.compile(
    rf"^\s*(?P<{MATCH_GROUP_KEY}>{AGENT_CONFIG_KEYS_PATTERN})\s*(?:[:=]|\s+)\s*"
    rf"(?P<{MATCH_GROUP_VALUE}>\S.*)$",
    re.IGNORECASE,
)

# Supported CLI option names for the consumer config path.
DEFAULT_CONFIG_PATH_ARGS = ("--config-path",)
# Supported CLI option names for the launched-agent config path.
DEFAULT_AGENT_CONFIG_PATH_ARGS = ("--agent-config-path",)
# Supported CLI option names for additional launched-agent command parameters.
DEFAULT_AGENT_ADDITIONAL_ARGS = ("--agent-additional-params",)
ENV_CONSUMER_LOGGING_CONFIG_PATH = "OPAMP_CONSUMER_LOGGING_CONFIG"
DEFAULT_CONSUMER_LOGGING_CONFIG_FILENAME = "consumer_logging.json"


def _default_logging_config(level_name: str) -> dict[str, object]:
    """Return fallback logging dictConfig when no config file exists."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
            }
        },
        "root": {"level": level_name, "handlers": ["console"]},
    }


def _load_logging_config(level_name: str) -> dict[str, object]:
    """Load consumer logging dictConfig from env/default path with fallback."""
    configured_path = os.getenv(ENV_CONSUMER_LOGGING_CONFIG_PATH)
    config_path = (
        pathlib.Path(configured_path)
        if configured_path
        else pathlib.Path(__file__).with_name(DEFAULT_CONSUMER_LOGGING_CONFIG_FILENAME)
    )
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding=UTF8_ENCODING))
            if isinstance(config, dict):
                config.setdefault("version", 1)
                config.setdefault("disable_existing_loggers", False)
                root = config.setdefault("root", {})
                if isinstance(root, dict):
                    root["level"] = level_name
                return config
        except Exception as exc:  # pragma: no cover - defensive fallback.
            print(
                f"failed to load consumer logging config {config_path}: {exc}",
                file=sys.stderr,
            )
    return _default_logging_config(level_name)


def build_common_cli_parser(
    *,
    config_path_args: tuple[str, ...] = DEFAULT_CONFIG_PATH_ARGS,
    agent_config_path_args: tuple[str, ...] = DEFAULT_AGENT_CONFIG_PATH_ARGS,
    agent_additional_args: tuple[str, ...] = DEFAULT_AGENT_ADDITIONAL_ARGS,
) -> argparse.ArgumentParser:
    """Build the shared consumer CLI parser."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument(*config_path_args, dest="config_path", type=str)
    parser.add_argument("--server-url", type=str)
    parser.add_argument("--server-port", type=int)
    parser.add_argument(*agent_config_path_args, dest="agent_config_path", type=str)
    parser.add_argument(
        *agent_additional_args,
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
    return parser


def load_config_from_cli_args(args: argparse.Namespace) -> ConsumerConfig:
    """Load consumer config using values parsed by `build_common_cli_parser`.

    Args:
        args: Parsed CLI argument namespace from the shared consumer parser.

    Returns:
        Consumer configuration resolved from file plus CLI overrides.
    """
    effective_config_path = consumer_config.get_effective_config_path(
        getattr(args, "config_path", None)
    )
    logging.getLogger(__name__).info(
        "using consumer config path: %s",
        effective_config_path,
    )
    override_fields = (
        "server_url",
        "server_port",
        "agent_config_path",
        "agent_additional_params",
        "heartbeat_frequency",
        "log_level",
        "full_update_controller",
    )
    override_values = {
        field: getattr(args, field, None) for field in override_fields
    }
    return consumer_config.load_config_with_overrides(
        config_path=effective_config_path,
        **override_values,
    )


def configure_logging_for_config(config: ConsumerConfig) -> logging.Logger:
    """Configure root logging based on config log level and return module logger."""
    resolved_log_level = consumer_config.resolve_log_level(config.log_level)
    resolved_log_level_name = logging.getLevelName(resolved_log_level)
    if not isinstance(resolved_log_level_name, str):
        resolved_log_level_name = "DEBUG"
    root_logger = logging.getLogger()
    if root_logger.handlers:
        logging.config.dictConfig(
            {
                "version": 1,
                "incremental": True,
                "root": {"level": resolved_log_level_name.upper()},
            }
        )
    else:
        logging.config.dictConfig(
            _load_logging_config(resolved_log_level_name.upper())
        )
    return logging.getLogger(__name__)


def maybe_print_config_help(
    *,
    args: argparse.Namespace,
    config: ConsumerConfig,
    config_parameters_payload_builder: Callable[[ConsumerConfig], dict[str, object]],
) -> bool:
    """Print config help payload when `--help` is requested.

    Returns:
        True when help was printed and caller should exit early.
    """
    if not bool(getattr(args, "help", False)):
        return False
    print(
        json.dumps(
            config_parameters_payload_builder(config),
            indent=2,
            sort_keys=True,
        )
    )
    return True


def validate_runtime_server_config(
    *,
    config: ConsumerConfig,
    localhost_base: str,
    missing_status_port_error: str,
) -> ConsumerConfig:
    """Validate and normalize runtime server/port configuration fields."""
    if config.client_status_port is None:
        raise ValueError(missing_status_port_error)
    if config.server_url is None and config.server_port is not None:
        config.server_url = f"{localhost_base}:{config.server_port}"
    if config.server_url is not None and config.server_port is not None:
        split_url = urlsplit(config.server_url)
        if split_url.netloc and split_url.port is None:
            auth_prefix = ""
            if "@" in split_url.netloc:
                auth_prefix = f"{split_url.netloc.rsplit('@', 1)[0]}@"
            host_token = split_url.hostname or ""
            if ":" in host_token and not host_token.startswith("["):
                host_token = f"[{host_token}]"
            config.server_url = urlunsplit(
                (
                    split_url.scheme,
                    f"{auth_prefix}{host_token}:{int(config.server_port)}",
                    split_url.path,
                    split_url.query,
                    split_url.fragment,
                )
            )
    if config.server_url is None:
        raise ValueError("server_url is not configured")
    return config


def _apply_agent_comment(
    config: consumer_config.ConsumerConfig,
    logger: logging.Logger,
    match: re.Match[str],
    resolve_service_instance_id_template_fn: Callable[[str | None], str | None],
) -> None:
    """Apply supported metadata comment values to the consumer config."""
    key = match.group(MATCH_GROUP_KEY).lower()
    value = match.group(MATCH_GROUP_VALUE)
    if key == KEY_SERVICE_INSTANCE_ID_COMMENT:
        value = resolve_service_instance_id_template_fn(value)
    config[key] = value
    logger.info("located >%s< with value >%s<", key, value)


def _apply_agent_setting(
    config: consumer_config.ConsumerConfig,
    logger: logging.Logger,
    match: re.Match[str],
) -> None:
    """Apply supported Fluent Bit HTTP settings to the consumer config."""
    key = match.group(MATCH_GROUP_KEY).lower()
    value = match.group(MATCH_GROUP_VALUE).strip()
    if key == KEY_HTTP_PORT:
        port_value = int(value)
        config.client_status_port = port_value
        config.agent_http_port = port_value
    elif key == KEY_HTTP_LISTEN:
        config.agent_http_listen = value
    elif key == KEY_HTTP_SERVER:
        config.agent_http_server = value
    else:
        config[key] = value
    logger.info("located >%s< with value >%s<", key, value)


def load_agent_config(
    config: consumer_config.ConsumerConfig,
    *,
    resolve_service_instance_id_template_fn: Callable[[str | None], str | None]
    | None = None,
) -> ConsumerConfig:
    """Load Fluent Bit config values and agent metadata into the config object.

    Args:
        config: Consumer configuration to enrich from Fluent Bit config file content.

    Returns:
        The same config object with parsed HTTP and metadata values applied.
    """
    logger = logging.getLogger(__name__)
    logger.warning("All config is %s", config)
    if resolve_service_instance_id_template_fn is None:
        resolve_service_instance_id_template_fn = resolve_service_instance_id_template
    path = config.agent_config_path
    if not path:
        raise ValueError(f"{CFG_AGENT_CONFIG_PATH} is not set")

    with open(path, encoding=UTF8_ENCODING) as handle:
        for raw_line in handle:
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue
            comment_match = _COMMENT_KV.match(raw_line)
            if comment_match is not None:
                _apply_agent_comment(
                    config,
                    logger,
                    comment_match,
                    resolve_service_instance_id_template_fn,
                )
                continue
            config_match = _AGENT_CONFIG_KV.match(raw_line)
            if config_match is not None:
                _apply_agent_setting(config, logger, config_match)

    return config


def build_minimal_agent(
    instance_uid: bytes | None = None,
    capabilities: int | None = None,
) -> opamp_pb2.AgentToServer:
    """Create a minimal AgentToServer message with configured capabilities.

    Args:
        instance_uid: Optional instance UID bytes to assign.
        capabilities: Optional capabilities bitmask.

    Returns:
        Minimal AgentToServer protobuf message for tests or bootstrap flows.
    """
    message = opamp_pb2.AgentToServer()
    if instance_uid is not None:
        message.instance_uid = instance_uid
    message.capabilities = capabilities or 0
    return message


async def run_client(client) -> None:
    """Trigger a single send cycle for the provided client instance.

    Args:
        client: OpAMP client object exposing an async `send()` method.
    """
    await client.send()


def _force_exit_on_lingering_threads() -> None:
    """Force process exit when non-daemon threads keep the interpreter alive."""
    alive_threads = [
        thread
        for thread in threading.enumerate()
        if thread is not threading.main_thread()
        and thread.is_alive()
        and not thread.daemon
    ]
    if not alive_threads:
        return
    print(
        "forcing process exit; non-daemon threads still alive: %s",
        [thread.name for thread in alive_threads],
    )
    os._exit(0)


def _get_local_ip() -> str:
    """Return a best-effort local host IP address."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def _get_local_mac() -> str:
    """Return local MAC address in colon-delimited lower-case format."""
    node = int(uuid.getnode())
    return ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))


def resolve_service_instance_id_template(value: str | None) -> str | None:
    """Resolve service_instance_id template tokens into runtime host values."""
    return resolve_service_instance_id_template_with_values(
        value=value,
        hostname=socket.gethostname(),
        ip_address=_get_local_ip(),
        mac_address=_get_local_mac(),
    )


def resolve_service_instance_id_template_with_values(
    *,
    value: str | None,
    hostname: str,
    ip_address: str,
    mac_address: str,
) -> str | None:
    """Resolve service_instance_id template tokens with provided host values."""
    if value is None:
        return None
    resolved = str(value)
    if TOKEN_IP in resolved:
        resolved = resolved.replace(TOKEN_IP, ip_address)
    if TOKEN_HOSTNAME in resolved:
        resolved = resolved.replace(TOKEN_HOSTNAME, hostname)
    if TOKEN_MAC_ADDR in resolved:
        resolved = resolved.replace(TOKEN_MAC_ADDR, mac_address)
    return resolved


def run_default_client_main(
    *,
    client_class,
    config_parameters_payload_builder: Callable[[ConsumerConfig], dict[str, object]],
    load_agent_config_fn: Callable[[ConsumerConfig], ConsumerConfig],
    localhost_base: str,
) -> None:
    """Run the default Fluent Bit-backed client CLI bootstrap flow."""
    try:
        tracemalloc.start()
        parser = build_common_cli_parser()
        args = parser.parse_args()
        config = load_config_from_cli_args(args)
        logger = configure_logging_for_config(config)

        if maybe_print_config_help(
            args=args,
            config=config,
            config_parameters_payload_builder=config_parameters_payload_builder,
        ):
            return

        logger.info("about to process FLB config")
        config = load_agent_config_fn(config)
        config = validate_runtime_server_config(
            config=config,
            localhost_base=localhost_base,
            missing_status_port_error="client_status_port not found in Fluent Bit config",
        )

        logger.debug(msg="setting up OpAMP")
        client = client_class(config.server_url, config)

        client.launch_agent_process()
        client.add_agent_version(config.client_status_port)

        logger.info("introducing self to server")
        asyncio.run(run_client(client))

        asyncio.run(client._heartbeat_loop(config.client_status_port))
        client.terminate_agent_process()

    except KeyboardInterrupt as keyboard_interrupt:
        print("... bzzzz keyboard\n %s", keyboard_interrupt)
    except SystemExit as system_exit:
        print("... bzzzz brutal exit\n %s", system_exit)
    except Exception:
        print("... bzzzzzzzzzzz")


def run_default_client_program_entrypoint(
    *,
    client_class,
    config_parameters_payload_builder: Callable[[ConsumerConfig], dict[str, object]],
    load_agent_config_fn: Callable[[ConsumerConfig], ConsumerConfig],
    localhost_base: str,
) -> None:
    """Run main flow and terminate process with legacy Fluent Bit semantics."""
    run_default_client_main(
        client_class=client_class,
        config_parameters_payload_builder=config_parameters_payload_builder,
        load_agent_config_fn=load_agent_config_fn,
        localhost_base=localhost_base,
    )
    print("... Bye")
    sys.exit(1)
