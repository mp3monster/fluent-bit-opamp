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

"""Configuration loader for the OpAMP consumer."""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

ROOT_PATH = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from shared.opamp_config import AgentCapabilities, UTF8_ENCODING, parse_capabilities

ENV_OPAMP_CONFIG_PATH = "OPAMP_CONFIG_PATH"
DEFAULT_CONFIG_FILENAME = "opamp.json"
DEFAULT_TRANSPORT = "http"
CFG_CONSUMER = "consumer"
CFG_SERVER_URL = "server_url"
CFG_SERVER_PORT = "server_port"
CFG_AGENT_CONFIG_PATH = "agent_config_path"
CFG_FLUENTBIT_CONFIG_PATH = "fluentbit_config_path"  # Backward-compatible legacy key.
CFG_AGENT_ADDITIONAL_PARAMS = "agent_additional_params"
CFG_ADDITIONAL_AGENT_PARAMS = (
    "additional_agent_params"  # Backward-compatible legacy key.
)
CFG_ADDITIONAL_FLUENTBIT_PARAMS = (
    "additional_fluent_bit_params"  # Backward-compatible legacy key.
)
CFG_HEARTBEAT_FREQUENCY = "heartbeat_frequency"
CFG_LOG_LEVEL = "log_level"
CFG_SERVICE_NAME = "service_name"
CFG_SERVICE_NAMESPACE = "service_namespace"
CFG_TRANSPORT = "transport"
CFG_LOG_AGENT_API_RESPONSES = "log_agent_api_responses"
CFG_ALLOW_CUSTOM_CAPABILITIES = "allow_custom_capabilities"
CFG_CLIENT_STATUS_PORT = "client_status_port"
CFG_CHAT_OPS_PORT = "chat_ops_port"
HARDWIRED_AGENT_CAPABILITY_NAMES = (
    "ReportsStatus",
    "AcceptsRestartCommand",
    "ReportsHealth",
)
DEFAULT_LOG_LEVEL = "debug"


@dataclass
class ConsumerConfig:
    server_url: str | None = None  # Base URL of the OpAMP provider server.
    server_port: int | None = (
        None  # Optional port definition for the OpAMP server connection.
    )
    agent_config_path: str | None = None  # Filesystem path to agent runtime config.
    agent_additional_params: list[str] | None = (
        None  # Extra CLI args for agent process launch.
    )
    heartbeat_frequency: int | None = (
        None  # Seconds between consumer heartbeat/status updates.
    )
    agent_capabilities: int | None = (
        None  # Bitmask of advertised OpAMP AgentCapabilities.
    )
    client_status_port: int | None = (
        None  # Local HTTP port used for status/health/version probes.
    )
    chat_ops_port: int | None = (
        None  # Local ChatOps endpoint port for custom command handling.This aligns with the HTTP input configuration
    )
    log_level: str | None = (
        None  # Application logging verbosity (for example debug/info).
    )
    agent_config_text: str | None = (
        None  # Cached raw agent configuration text when loaded.
    )
    agent_description: str | None = (
        None  # Optional override/metadata used for agent identification.
    )
    service_instance_id: str | None = (
        None  # Instance identifier reported in service metadata.
    )
    service_name: str | None = (
        None  # Service name reported in AgentDescription attributes.
    )
    service_namespace: str | None = (
        None  # Service namespace reported in AgentDescription attributes.
    )
    transport: str | None = None  # Active OpAMP transport mode (http or websocket).
    log_agent_api_responses: bool | None = (
        None  # Whether to log verbose API response payloads.
    )
    allow_custom_capabilities: bool = (
        False  # Allow custom capability discovery/registration.
    )
    agent_http_port: int | None = None  # Parsed agent internal HTTP endpoint port.
    agent_http_listen: str | None = None  # Parsed agent internal HTTP listen address.
    agent_http_server: str | None = None  # Parsed agent internal HTTP server setting.

    def __setitem__(self, key, value):
        return setattr(self, key, value)

    @property
    def http_listen(self) -> str | None:
        """Backward-compatible alias for `agent_http_listen`."""
        return self.agent_http_listen

    @http_listen.setter
    def http_listen(self, value: str | None) -> None:
        """Keep legacy `http_listen` assignments synchronized to `agent_http_listen`."""
        if value:
            self.agent_http_listen = value

    @property
    def http_server(self) -> str | None:
        """Backward-compatible alias for `agent_http_server`."""
        return self.agent_http_server

    @http_server.setter
    def http_server(self, value: str | None) -> None:
        """Keep legacy `http_server` assignments synchronized to `agent_http_server`."""
        if value:
            self.agent_http_server = value


def resolve_log_level(log_level: str) -> int:
    """Map a string log level to a logging module constant."""
    normalized_level = log_level.strip().upper()
    level_map = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    return level_map.get(normalized_level, logging.DEBUG)


def _repo_root() -> pathlib.Path:
    """Return the repository root path."""
    return ROOT_PATH


def _ensure_shared_on_path() -> None:
    """Compatibility no-op for shared import handling."""
    return None


def _config_path() -> pathlib.Path:
    """Resolve the consumer config path from environment or working directory."""
    path = os.environ.get(ENV_OPAMP_CONFIG_PATH)
    logger = logging.getLogger(__name__)
    if path:
        logger.warning("config path is %s", pathlib.Path.cwd())
        return pathlib.Path(path)
    logger.warning("defaulting path to %s/%s", pathlib.Path.cwd(), DEFAULT_CONFIG_FILENAME)
    return pathlib.Path.cwd() / DEFAULT_CONFIG_FILENAME


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    """Load JSON config from disk, raising for missing files."""
    logger = logging.getLogger(__name__)

    if not path:
        logger.error("No file to load")
        return None
    else:
        logger.debug("Have a path - %d", path)

    if not path.exists():
        logger.error("path doesn't exist")
        raise FileNotFoundError("config file not found: %s", path)

    logger.error("loading %s", path)
    return json.loads(path.read_text(encoding=UTF8_ENCODING))


def _pick_first_defined(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-None value found for the provided keys."""
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _resolve_config_value(
    *,
    mapping: dict[str, Any],
    key: str,
    logger: logging.Logger,
    override: Any | None = None,
    default: Any | None = None,
    legacy_keys: tuple[str, ...] = (),
) -> Any:
    """Resolve a config value from canonical key, optional legacy keys, and CLI override."""
    value = mapping.get(key, default)
    if value is None and legacy_keys:
        value = _pick_first_defined(mapping, legacy_keys)
    if override is not None:
        logger.info("cli override %s.%s; ignoring config value", CFG_CONSUMER, key)
        return override
    return value


def _coerce_optional_int(value: Any) -> int | None:
    """Convert optional numeric input to int or None."""
    return int(value) if value is not None else None


def _validate_heartbeat_frequency(value: Any) -> int:
    """Validate heartbeat frequency and return normalized integer value."""
    if value is None:
        return 30
    if not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{CFG_CONSUMER}.{CFG_HEARTBEAT_FREQUENCY} must be a non-negative integer"
        )
    return value


def load_config() -> ConsumerConfig:
    """Load consumer configuration from disk."""
    logger = logging.getLogger(__name__)
    raw = _load_json(_config_path())
    consumer_raw = raw.get(CFG_CONSUMER, {})
    server_url = consumer_raw.get(CFG_SERVER_URL)
    server_port = consumer_raw.get(CFG_SERVER_PORT)
    service_name = consumer_raw.get(CFG_SERVICE_NAME)
    service_namespace = consumer_raw.get(CFG_SERVICE_NAMESPACE)
    transport = consumer_raw.get(CFG_TRANSPORT, DEFAULT_TRANSPORT)
    log_agent_api_responses = consumer_raw.get(CFG_LOG_AGENT_API_RESPONSES, False)
    allow_custom_capabilities = bool(
        consumer_raw.get(CFG_ALLOW_CUSTOM_CAPABILITIES, False)
    )
    mask: None

    if not server_url:
        logger.warning(msg=f"{CFG_CONSUMER}.{CFG_SERVER_URL} is required")
    agent_config_path = consumer_raw.get(CFG_AGENT_CONFIG_PATH)
    if agent_config_path is None:
        agent_config_path = consumer_raw.get(CFG_FLUENTBIT_CONFIG_PATH, ".")

    if not agent_config_path:
        logger.warning(msg=f"{CFG_CONSUMER}.{CFG_AGENT_CONFIG_PATH} is expected")
    additional_params = consumer_raw.get(CFG_AGENT_ADDITIONAL_PARAMS)
    if additional_params is None:
        additional_params = consumer_raw.get(CFG_ADDITIONAL_AGENT_PARAMS)
    if additional_params is None:
        additional_params = consumer_raw.get(CFG_ADDITIONAL_FLUENTBIT_PARAMS)

    if additional_params is None:
        logger.info(msg=f"{CFG_CONSUMER}.{CFG_AGENT_ADDITIONAL_PARAMS} no settings")
    if not isinstance(additional_params, list):
        logger.info(msg=f"{CFG_CONSUMER}.{CFG_AGENT_ADDITIONAL_PARAMS} must be a list")

    heartbeat_frequency = consumer_raw.get(CFG_HEARTBEAT_FREQUENCY, 30)
    if heartbeat_frequency is None:
        heartbeat_frequency = 30
    if heartbeat_frequency == 0:
        raise ValueError(
            f"{CFG_CONSUMER}.{CFG_HEARTBEAT_FREQUENCY} must be a non-negative integer"
        )

    mask = parse_capabilities(HARDWIRED_AGENT_CAPABILITY_NAMES, AgentCapabilities)
    log_level = consumer_raw.get(CFG_LOG_LEVEL, DEFAULT_LOG_LEVEL) or DEFAULT_LOG_LEVEL
    client_status_port = consumer_raw.get(CFG_CLIENT_STATUS_PORT)
    chat_ops_port = consumer_raw.get(CFG_CHAT_OPS_PORT)

    logger.info("loaded consumer server_url: %s", server_url)
    logger.info("loaded consumer server_port: %s", server_port)
    logger.info("loaded consumer service_name: %s", service_name)
    logger.info("loaded consumer service_namespace: %s", service_namespace)
    logger.info("loaded consumer transport: %s", transport)
    logger.info(
        "loaded consumer log_agent_api_responses: %s",
        log_agent_api_responses,
    )
    logger.info(
        "loaded consumer allow_custom_capabilities: %s",
        allow_custom_capabilities,
    )
    logger.info("loaded consumer agent_config_path: %s", agent_config_path)
    logger.info("loaded consumer agent_additional_params: %s", additional_params)
    logger.info("loaded consumer heartbeat_frequency: %s", heartbeat_frequency)
    logger.info(
        "loaded consumer capabilities (hardwired): %s",
        HARDWIRED_AGENT_CAPABILITY_NAMES,
    )
    logger.info("loaded consumer log_level: %s", log_level)
    logger.info("loaded consumer client_status_port: %s", client_status_port)
    logger.info("loaded consumer chat_ops_port: %s", chat_ops_port)
    return ConsumerConfig(
        server_url=server_url,
        server_port=server_port,
        agent_config_path=agent_config_path,
        agent_additional_params=additional_params,
        heartbeat_frequency=heartbeat_frequency,
        agent_capabilities=mask,
        service_name=service_name,
        service_namespace=service_namespace,
        transport=transport,
        log_agent_api_responses=bool(log_agent_api_responses),
        allow_custom_capabilities=allow_custom_capabilities,
        client_status_port=(
            int(client_status_port) if client_status_port is not None else None
        ),
        chat_ops_port=int(chat_ops_port) if chat_ops_port is not None else None,
    )


def load_config_with_overrides(
    *,
    config_path: pathlib.Path | None,
    server_url: str | None,
    server_port: int | None,
    agent_config_path: str | None,
    agent_additional_params: list[str] | None,
    heartbeat_frequency: int | None,
) -> ConsumerConfig:
    """Load config and apply CLI overrides for the consumer."""
    logger = logging.getLogger(__name__)
    base_raw = _load_json(config_path or _config_path())
    consumer_raw = dict(base_raw.get(CFG_CONSUMER, {}))

    resolved_server_url = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_SERVER_URL,
        logger=logger,
        override=server_url,
    )
    resolved_server_port = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_SERVER_PORT,
        logger=logger,
        override=server_port,
    )
    resolved_agent_config_path = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_AGENT_CONFIG_PATH,
        logger=logger,
        override=agent_config_path,
        legacy_keys=(CFG_FLUENTBIT_CONFIG_PATH,),
    )
    resolved_additional_params = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_AGENT_ADDITIONAL_PARAMS,
        logger=logger,
        override=agent_additional_params,
        legacy_keys=(CFG_ADDITIONAL_AGENT_PARAMS, CFG_ADDITIONAL_FLUENTBIT_PARAMS),
    )
    resolved_heartbeat_frequency = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_HEARTBEAT_FREQUENCY,
        logger=logger,
        override=heartbeat_frequency,
        default=30,
    )

    if not resolved_agent_config_path:
        raise ValueError(f"{CFG_CONSUMER}.{CFG_AGENT_CONFIG_PATH} is required")
    if resolved_additional_params is None:
        raise ValueError(f"{CFG_CONSUMER}.{CFG_AGENT_ADDITIONAL_PARAMS} is required")
    if not isinstance(resolved_additional_params, list):
        raise ValueError(f"{CFG_CONSUMER}.{CFG_AGENT_ADDITIONAL_PARAMS} must be a list")
    resolved_heartbeat_frequency = _validate_heartbeat_frequency(
        resolved_heartbeat_frequency
    )

    return ConsumerConfig(
        server_url=resolved_server_url,
        server_port=resolved_server_port,
        agent_config_path=resolved_agent_config_path,
        agent_additional_params=resolved_additional_params,
        heartbeat_frequency=resolved_heartbeat_frequency,
        agent_capabilities=parse_capabilities(
            HARDWIRED_AGENT_CAPABILITY_NAMES, AgentCapabilities
        ),
        service_name=consumer_raw.get(CFG_SERVICE_NAME),
        service_namespace=consumer_raw.get(CFG_SERVICE_NAMESPACE),
        transport=consumer_raw.get(CFG_TRANSPORT, DEFAULT_TRANSPORT),
        log_agent_api_responses=bool(
            consumer_raw.get(CFG_LOG_AGENT_API_RESPONSES, False)
        ),
        allow_custom_capabilities=bool(
            consumer_raw.get(CFG_ALLOW_CUSTOM_CAPABILITIES, False)
        ),
        client_status_port=_coerce_optional_int(
            consumer_raw.get(CFG_CLIENT_STATUS_PORT)
        ),
        chat_ops_port=_coerce_optional_int(consumer_raw.get(CFG_CHAT_OPS_PORT)),
        log_level=consumer_raw.get(CFG_LOG_LEVEL, DEFAULT_LOG_LEVEL)
        or DEFAULT_LOG_LEVEL,
    )


def set_config(config: ConsumerConfig) -> None:
    """Update the module-level config singleton."""
    global CONFIG
    CONFIG = config


CONFIG = load_config()
