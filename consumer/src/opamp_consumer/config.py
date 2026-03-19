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
CFG_CONSUMER = "consumer"
CFG_SERVER_URL = "server_url"
CFG_SERVER_PORT = "server_port"
CFG_FLUENTBIT_CONFIG_PATH = "fluentbit_config_path"
CFG_ADDITIONAL_FLUENTBIT_PARAMS = "additional_fluent_bit_params"
CFG_HEARTBEAT_FREQUENCY = "heartbeat_frequency"
CFG_AGENT_CAPABILITIES = "agent_capabilities"
CFG_LOG_LEVEL = "log_level"
CFG_SERVICE_NAME = "service_name"
CFG_SERVICE_NAMESPACE = "service_namespace"
CFG_TRANSPORT = "transport"
CFG_LOG_AGENT_API_RESPONSES = "log_agent_api_responses"


@dataclass
class ConsumerConfig:
    server_url: str | None = None
    server_port: int | None = None
    fluentbit_config_path: str | None = None
    additional_fluent_bit_params: list[str] | None = None
    heartbeat_frequency: int | None = None
    agent_capabilities: int | None = None
    http_port: int | None = None
    http_listen: str | None = None
    http_server: str | None = None
    log_level: str | None = None
    fluentbit_config_text: str | None = None
    agent_description: str | None = None
    service_instance_id: str | None = None
    service_name: str | None = None
    service_namespace: str | None = None
    transport: str | None = None
    log_agent_api_responses: bool | None = None
    fluentbit_http_port: int | None = None
    fluentbit_http_listen: str | None = None
    fluentbit_http_server: str | None = None

    def __setitem__(self, key, value):
        return setattr(self, key, value)


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
        logger.warning(f"config path is {pathlib.Path.cwd()}")
        return pathlib.Path(path)
    logger.warning(f"defaulting path to {pathlib.Path.cwd()}/opamp.json")
    return pathlib.Path.cwd() / "opamp.json"


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    """Load JSON config from disk, raising for missing files."""
    logger = logging.getLogger(__name__)

    if not path:
        logger.error(f"No file to load")
        return None
    else:
        logger.debug(f"Have a path - {path}")

    if not path.exists():
        logger.error(f"path doesnt exist")
        raise FileNotFoundError(f"config file not found: {path}")

    logger.error(f"loading {path}")
    return json.loads(path.read_text(encoding=UTF8_ENCODING))


def load_config() -> ConsumerConfig:
    """Load consumer configuration from disk."""
    logger = logging.getLogger(__name__)
    raw = _load_json(_config_path())
    consumer_raw = raw.get(CFG_CONSUMER, {})
    server_url = consumer_raw.get(CFG_SERVER_URL)
    server_port = consumer_raw.get(CFG_SERVER_PORT)
    service_name = consumer_raw.get(CFG_SERVICE_NAME)
    service_namespace = consumer_raw.get(CFG_SERVICE_NAMESPACE)
    transport = consumer_raw.get(CFG_TRANSPORT, "http")
    log_agent_api_responses = consumer_raw.get(
        CFG_LOG_AGENT_API_RESPONSES, False
    )
    mask: None

    if not server_url:
        logger.warning(msg=f"{CFG_CONSUMER}.{CFG_SERVER_URL} is required")
    fluentbit_config_path = consumer_raw.get(CFG_FLUENTBIT_CONFIG_PATH, ".")

    if not fluentbit_config_path:
        logger.warning(msg=f"{CFG_CONSUMER}.{CFG_FLUENTBIT_CONFIG_PATH} is expected")
    additional_params = consumer_raw.get(CFG_ADDITIONAL_FLUENTBIT_PARAMS)

    if additional_params is None:
        logger.info(msg=f"{CFG_CONSUMER}.{CFG_ADDITIONAL_FLUENTBIT_PARAMS} no settings")
    if not isinstance(additional_params, list):
        logger.info(
            msg=f"{CFG_CONSUMER}.{CFG_ADDITIONAL_FLUENTBIT_PARAMS} must be a list"
        )

    heartbeat_frequency = consumer_raw.get(CFG_HEARTBEAT_FREQUENCY, 30)
    if heartbeat_frequency is None:
        heartbeat_frequency = 30
    if heartbeat_frequency == 0:
        raise ValueError(
            f"{CFG_CONSUMER}.{CFG_HEARTBEAT_FREQUENCY} must be a non-negative integer"
        )

    capability_names = consumer_raw.get(CFG_AGENT_CAPABILITIES)
    if not capability_names:
        logger.warning(
            f"{CFG_CONSUMER}.{CFG_AGENT_CAPABILITIES} must be a non-empty list"
        )
        capability_names = ["ReportsStatus"]

    mask = parse_capabilities(capability_names, AgentCapabilities)
    log_level = consumer_raw.get(CFG_LOG_LEVEL, "debug") or "debug"

    logger.info("loaded consumer server_url: %s", server_url)
    logger.info("loaded consumer server_port: %s", server_port)
    logger.info("loaded consumer service_name: %s", service_name)
    logger.info("loaded consumer service_namespace: %s", service_namespace)
    logger.info("loaded consumer transport: %s", transport)
    logger.info(
        "loaded consumer log_agent_api_responses: %s",
        log_agent_api_responses,
    )
    logger.info("loaded consumer fluentbit_config_path: %s", fluentbit_config_path)
    logger.info("loaded consumer additional_fluent_bit_params: %s", additional_params)
    logger.info("loaded consumer heartbeat_frequency: %s", heartbeat_frequency)
    logger.info("loaded consumer capabilities: %s", capability_names)
    logger.info("loaded consumer log_level: %s", log_level)
    return ConsumerConfig(
        server_url=server_url,
        server_port=server_port,
        fluentbit_config_path=fluentbit_config_path,
        additional_fluent_bit_params=additional_params,
        heartbeat_frequency=heartbeat_frequency,
        agent_capabilities=mask,
        service_name=service_name,
        service_namespace=service_namespace,
        transport=transport,
        log_agent_api_responses=bool(log_agent_api_responses),
    )


def apply_override(
    key: str,
    parentId: str | None,
    overrideValue: any | None,
    configValue: any | None,
    config: ConsumerConfig,
) -> ConsumerConfig:
    """Apply a CLI override when provided and return the updated config."""
    config[key] = configValue
    if overrideValue is not None:
        logging.getLogger(__name__).info(
            "cli override %s.%s; ignoring config value", parentId, key
        )
        config[key] = overrideValue

    return config


def load_config_with_overrides(
    *,
    config_path: pathlib.Path | None,
    server_url: str | None,
    server_port: int | None,
    fluentbit_config_path: str | None,
    additional_fluent_bit_params: list[str] | None,
    heartbeat_frequency: int | None,
) -> ConsumerConfig:
    """Load config and apply CLI overrides for the consumer."""
    logger = logging.getLogger(__name__)

    config: ConsumerConfig = ConsumerConfig(
        server_url,
    )
    base_raw = _load_json(config_path or _config_path())
    consumer_raw = base_raw.get(CFG_CONSUMER, {})

    config = apply_override(
        CFG_SERVER_URL,
        CFG_CONSUMER,
        server_url,
        consumer_raw.get(CFG_SERVER_URL),
        config,
    )

    config = apply_override(
        CFG_SERVER_PORT,
        CFG_CONSUMER,
        server_port,
        consumer_raw.get(CFG_SERVER_PORT),
        config,
    )
    config = apply_override(
        CFG_TRANSPORT,
        CFG_CONSUMER,
        None,
        consumer_raw.get(CFG_TRANSPORT, "http"),
        config,
    )
    config = apply_override(
        CFG_LOG_AGENT_API_RESPONSES,
        CFG_CONSUMER,
        None,
        consumer_raw.get(CFG_LOG_AGENT_API_RESPONSES, False),
        config,
    )

    config = apply_override(
        CFG_FLUENTBIT_CONFIG_PATH,
        CFG_CONSUMER,
        fluentbit_config_path,
        consumer_raw[CFG_FLUENTBIT_CONFIG_PATH],
        config,
    )

    if additional_fluent_bit_params is not None:
        logger.info(
            "cli override %s.%s; ignoring config value",
            CFG_CONSUMER,
            CFG_ADDITIONAL_FLUENTBIT_PARAMS,
        )
        consumer_raw[CFG_ADDITIONAL_FLUENTBIT_PARAMS] = additional_fluent_bit_params
    if heartbeat_frequency is not None:
        logger.info(
            "cli override %s.%s; ignoring config value",
            CFG_CONSUMER,
            CFG_HEARTBEAT_FREQUENCY,
        )
        consumer_raw[CFG_HEARTBEAT_FREQUENCY] = heartbeat_frequency

    temp_raw = {CFG_CONSUMER: consumer_raw}
    raw = temp_raw
    server_url = raw.get(CFG_CONSUMER, {}).get(CFG_SERVER_URL)

    logger.error(msg=f"100 {server_url}")

    if not server_url:
        logger.info(
            f"{CFG_CONSUMER}.{CFG_SERVER_URL} will be taken from the Fluent Bit config file"
        )
    fluentbit_config_path = raw.get(CFG_CONSUMER, {}).get(CFG_FLUENTBIT_CONFIG_PATH)

    if not server_port:
        logger.info(
            f"{CFG_CONSUMER}.{CFG_SERVER_PORT} is will be taken from the Fluent Bit config file"
        )

    fluentbit_config_path = raw.get(CFG_CONSUMER, {}).get(CFG_FLUENTBIT_CONFIG_PATH)
    if not fluentbit_config_path:
        raise ValueError(f"{CFG_CONSUMER}.{CFG_FLUENTBIT_CONFIG_PATH} is required")
    additional_params = raw.get(CFG_CONSUMER, {}).get(CFG_ADDITIONAL_FLUENTBIT_PARAMS)
    if additional_params is None:
        raise ValueError(
            f"{CFG_CONSUMER}.{CFG_ADDITIONAL_FLUENTBIT_PARAMS} is required"
        )
    if not isinstance(additional_params, list):
        raise ValueError(
            f"{CFG_CONSUMER}.{CFG_ADDITIONAL_FLUENTBIT_PARAMS} must be a list"
        )
    heartbeat_frequency = raw.get(CFG_CONSUMER, {}).get(CFG_HEARTBEAT_FREQUENCY, 30)
    if heartbeat_frequency is None:
        heartbeat_frequency = 30
    if not isinstance(heartbeat_frequency, int) or heartbeat_frequency < 0:
        raise ValueError(
            f"{CFG_CONSUMER}.{CFG_HEARTBEAT_FREQUENCY} must be a non-negative integer"
        )
    config.heartbeat_frequency = heartbeat_frequency
    log_agent_api_responses = raw.get(CFG_CONSUMER, {}).get(
        CFG_LOG_AGENT_API_RESPONSES, False
    )
    config.log_agent_api_responses = bool(log_agent_api_responses)

    log_level = raw.get(CFG_CONSUMER, {}).get(CFG_LOG_LEVEL, "debug") or "debug"
    return config


def set_config(config: ConsumerConfig) -> None:
    """Update the module-level config singleton."""
    global CONFIG
    CONFIG = config


CONFIG = load_config()
