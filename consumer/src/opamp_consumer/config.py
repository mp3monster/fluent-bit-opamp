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

ROOT_PATH = pathlib.Path(__file__).resolve().parents[3]  # Repository root for resolving shared imports and defaults.
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from shared.opamp_config import UTF8_ENCODING, AgentCapabilities, parse_capabilities

ENV_OPAMP_CONFIG_PATH = "OPAMP_CONFIG_PATH"  # Environment variable overriding config file location.
DEFAULT_CONFIG_FILENAME = "opamp.json"  # Default configuration filename.
DEFAULT_TRANSPORT = "http"  # Fallback transport mode when none is configured.
CFG_CONSUMER = "consumer"  # Top-level JSON section name for consumer settings.
CFG_SERVER_URL = "server_url"  # Consumer JSON key for provider URL.
CFG_SERVER_PORT = "server_port"  # Consumer JSON key for provider port.
CFG_AGENT_CONFIG_PATH = "agent_config_path"  # Consumer JSON key for agent config file path.
CFG_AGENT_ADDITIONAL_PARAMS = "agent_additional_params"  # Consumer JSON key for extra agent CLI args.
CFG_HEARTBEAT_FREQUENCY = "heartbeat_frequency"  # Consumer JSON key for heartbeat interval seconds.
CFG_LOG_LEVEL = "log_level"  # Consumer JSON key for logging level override.
CFG_SERVICE_NAME = "service_name"  # Consumer JSON key for service.name override.
CFG_SERVICE_NAMESPACE = "service_namespace"  # Consumer JSON key for service.namespace override.
CFG_TRANSPORT = "transport"  # Consumer JSON key for selected transport mode.
CFG_TLS = "tls"  # Consumer JSON key for TLS transport settings block.
CFG_TLS_VERIFY_SERVER = "verify_server"  # Consumer TLS key controlling HTTPS certificate validation.
CFG_TLS_CA_FILE = "ca_file"  # Consumer TLS key for custom CA bundle path.
CFG_SERVER_AUTHORIZATION = "server-authorization"  # Consumer JSON key controlling outbound provider authorization mode.
CFG_OPAMP_TOKEN = "OpAMP-token"  # Consumer JSON key for static OpAMP token value.
CFG_IDP_TOKEN_URL = "idp-token-url"  # Consumer JSON key for IdP token endpoint URL.
CFG_IDP_CLIENT_ID = "idp-client-id"  # Consumer JSON key for IdP client ID.
CFG_IDP_CLIENT_SECRET = "idp-client-secret"  # Consumer JSON key for IdP client secret.
CFG_IDP_SCOPE = "idp-scope"  # Consumer JSON key for IdP OAuth scope.
CFG_IDP_GRANT_TYPE = "idp-grant-type"  # Consumer JSON key for IdP OAuth grant type.
CFG_LOG_AGENT_API_RESPONSES = "log_agent_api_responses"  # Consumer JSON key enabling verbose API logging.
CFG_ALLOW_CUSTOM_CAPABILITIES = "allow_custom_capabilities"  # Consumer JSON key allowing dynamic custom capabilities.
CFG_CLIENT_STATUS_PORT = "client_status_port"  # Consumer JSON key for local status endpoint port.
CFG_CHAT_OPS_PORT = "chat_ops_port"  # Consumer JSON key for local ChatOps endpoint port.
CFG_FULL_UPDATE_CONTROLLER = "full_update_controller"  # Consumer JSON key for full-update controller config object.
CFG_FULL_UPDATE_CONTROLLER_TYPE = "full_update_controller_type"  # Consumer JSON key for full-update controller implementation type.
HARDWIRED_AGENT_CAPABILITY_NAMES = (  # Built-in capabilities always advertised by this consumer.
    "ReportsStatus",
    "AcceptsRestartCommand",
    "ReportsHealth",
)
DEFAULT_LOG_LEVEL = "debug"  # Default consumer log level when unspecified.
DEFAULT_TLS_VERIFY_SERVER = True  # Default behavior validates provider server certificate.
DEFAULT_FULL_UPDATE_CONTROLLER: dict[str, int] = {"fullResendAfter": 1}  # Default controller settings payload.
DEFAULT_FULL_UPDATE_CONTROLLER_TYPE = "SentCount"  # Default full-update controller implementation name.
SERVER_AUTHORIZATION_NONE = "none"  # Disable outbound provider Authorization header usage.
SERVER_AUTHORIZATION_ENV_VAR = "env-var"  # Read outbound provider token from environment.
SERVER_AUTHORIZATION_CONFIG_VAR = "config-var"  # Read outbound provider token from config file.
SERVER_AUTHORIZATION_IDP = "idp"  # Obtain outbound provider token from an IdP token endpoint.
DEFAULT_SERVER_AUTHORIZATION = SERVER_AUTHORIZATION_NONE  # Default outbound provider authorization mode.
DEFAULT_IDP_GRANT_TYPE = "client_credentials"  # Default OAuth grant type for IdP token requests.


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
        None
        # Local ChatOps endpoint port for custom command handling.
        # This aligns with the HTTP input configuration.
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
    config_version: str | None = (
        None  # Optional comment-sourced config version metadata.
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
    tls_verify_server: bool = DEFAULT_TLS_VERIFY_SERVER  # Enable outbound HTTPS/WSS certificate verification.
    tls_ca_file: str | None = None  # Optional custom CA file used for outbound HTTPS/WSS validation.
    server_authorization: str = (
        DEFAULT_SERVER_AUTHORIZATION
        # Outbound provider authorization mode: none | env-var | config-var | idp.
    )
    opamp_token: str | None = (
        None  # Optional static OpAMP token used when server_authorization=config-var.
    )
    idp_token_url: str | None = None  # IdP token endpoint used when server_authorization=idp.
    idp_client_id: str | None = None  # IdP OAuth client ID.
    idp_client_secret: str | None = None  # IdP OAuth client secret.
    idp_scope: str | None = None  # Optional IdP OAuth scope.
    idp_grant_type: str = DEFAULT_IDP_GRANT_TYPE  # IdP OAuth grant type.
    server_authorization_header_name: str = (
        "Authorization"  # Runtime header name used for outbound authorization.
    )
    server_authorization_header_value: str | None = (
        None  # Runtime header value used for outbound authorization.
    )
    log_agent_api_responses: bool | None = (
        None  # Whether to log verbose API response payloads.
    )
    allow_custom_capabilities: bool = (
        False  # Allow custom capability discovery/registration.
    )
    agent_http_port: int | None = None  # Parsed agent internal HTTP endpoint port.
    agent_http_listen: str | None = None  # Parsed agent internal HTTP listen address.
    agent_http_server: str | None = None  # Parsed agent internal HTTP server setting.
    full_update_controller: dict[str, Any] | str | None = (
        None  # Controller config object from file or CLI JSON string.
    )
    full_update_controller_type: str = (
        DEFAULT_FULL_UPDATE_CONTROLLER_TYPE
        # Concrete full update controller implementation name.
    )

    def __setitem__(self, key, value):
        """Support dict-style assignment by forwarding writes to dataclass attributes.

        Args:
            key: Attribute name to set.
            value: Value to assign to the target attribute.
        """
        return setattr(self, key, value)


def resolve_log_level(log_level: str) -> int:
    """Resolve a log level name to a logging level using logging's level map."""
    normalized_level = str(log_level or DEFAULT_LOG_LEVEL).strip().upper()
    # Use getLevelName() for compatibility with Python 3.10 where
    # getLevelNamesMapping() is not available.
    level = logging.getLevelName(normalized_level)
    if isinstance(level, int):
        return level
    return logging.DEBUG


def _repo_root() -> pathlib.Path:
    """Return the repository root path."""
    return ROOT_PATH


def _ensure_shared_on_path() -> None:
    """Compatibility no-op for shared import handling."""
    return None


def _config_path() -> pathlib.Path:
    """Resolve the consumer config path from env var or known repo defaults."""
    env_path = os.environ.get(ENV_OPAMP_CONFIG_PATH)
    logger = logging.getLogger(__name__)
    if env_path:
        resolved = pathlib.Path(env_path)
        logger.info("using %s from environment: %s", ENV_OPAMP_CONFIG_PATH, resolved)
        return resolved

    candidates = (
        pathlib.Path.cwd() / DEFAULT_CONFIG_FILENAME,
        _repo_root() / "consumer" / DEFAULT_CONFIG_FILENAME,
        _repo_root() / "config" / DEFAULT_CONFIG_FILENAME,
    )
    for candidate in candidates:
        if candidate.exists():
            logger.info("using discovered config path: %s", candidate)
            return candidate

    logger.warning("defaulting config path to %s", candidates[0])
    return candidates[0]


def get_effective_config_path(
    config_path: str | pathlib.Path | None = None,
) -> pathlib.Path:
    """Return the effective config path used for loading consumer configuration."""
    if config_path is not None:
        return pathlib.Path(config_path)
    return _config_path()


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    """Load JSON config from disk, raising for missing files."""
    logger = logging.getLogger(__name__)

    if not path:
        logger.error("No file to load")
        return None
    else:
        logger.debug("Have a path - %s", path)

    if not path.exists():
        logger.error("path doesn't exist")
        raise FileNotFoundError("config file not found: %s", path)

    logger.error("loading %s", path)
    return json.loads(path.read_text(encoding=UTF8_ENCODING))


def _resolve_config_value(
    *,
    mapping: dict[str, Any],
    key: str,
    logger: logging.Logger,
    override: Any | None = None,
    default: Any | None = None,
) -> Any:
    """Resolve a config value from canonical key and CLI override."""
    value = mapping.get(key, default)
    if override is not None:
        logger.info("cli override %s.%s; ignoring config value", CFG_CONSUMER, key)
        return override
    return value


def _coerce_optional_int(value: Any) -> int | None:
    """Convert optional numeric input to int or None."""
    return int(value) if value is not None else None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Convert common JSON boolean forms to bool with a default fallback."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _coerce_optional_str(value: Any) -> str | None:
    """Convert optional values to stripped strings, preserving None/empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_tls_section(consumer_raw: dict[str, Any]) -> dict[str, Any]:
    """Return normalized consumer TLS config mapping."""
    tls_raw = consumer_raw.get(CFG_TLS)
    if tls_raw is None:
        return {}
    if isinstance(tls_raw, dict):
        return tls_raw
    logging.getLogger(__name__).warning(
        "%s.%s must be an object; ignoring invalid value %r",
        CFG_CONSUMER,
        CFG_TLS,
        tls_raw,
    )
    return {}


def _validate_optional_file_path(*, path_value: str | None, cfg_key: str) -> str | None:
    """Validate optional file paths and return normalized string path."""
    normalized_path = _coerce_optional_str(path_value)
    if not normalized_path:
        return None
    path = pathlib.Path(normalized_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"{cfg_key} must reference an existing file")
    return normalized_path


def _normalize_server_authorization(value: Any) -> str:
    """Normalize server authorization mode from canonical config values."""
    if value is None:
        return DEFAULT_SERVER_AUTHORIZATION
    normalized = str(value).strip().lower()
    if not normalized:
        return DEFAULT_SERVER_AUTHORIZATION
    if normalized in {
        SERVER_AUTHORIZATION_NONE,
        SERVER_AUTHORIZATION_ENV_VAR,
        SERVER_AUTHORIZATION_CONFIG_VAR,
        SERVER_AUTHORIZATION_IDP,
    }:
        return normalized
    logging.getLogger(__name__).warning(
        "invalid %s.%s value %r; defaulting to %s",
        CFG_CONSUMER,
        CFG_SERVER_AUTHORIZATION,
        value,
        DEFAULT_SERVER_AUTHORIZATION,
    )
    return DEFAULT_SERVER_AUTHORIZATION


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
    tls_raw = _resolve_tls_section(consumer_raw)
    tls_verify_server = _coerce_bool(
        tls_raw.get(CFG_TLS_VERIFY_SERVER),
        default=DEFAULT_TLS_VERIFY_SERVER,
    )
    tls_ca_file = _validate_optional_file_path(
        path_value=tls_raw.get(CFG_TLS_CA_FILE),
        cfg_key=f"{CFG_CONSUMER}.{CFG_TLS}.{CFG_TLS_CA_FILE}",
    )
    server_authorization_raw = consumer_raw.get(CFG_SERVER_AUTHORIZATION)
    server_authorization = _normalize_server_authorization(server_authorization_raw)
    opamp_token = _coerce_optional_str(consumer_raw.get(CFG_OPAMP_TOKEN))
    idp_token_url = _coerce_optional_str(consumer_raw.get(CFG_IDP_TOKEN_URL))
    idp_client_id = _coerce_optional_str(consumer_raw.get(CFG_IDP_CLIENT_ID))
    idp_client_secret = _coerce_optional_str(consumer_raw.get(CFG_IDP_CLIENT_SECRET))
    idp_scope = _coerce_optional_str(consumer_raw.get(CFG_IDP_SCOPE))
    idp_grant_type = str(consumer_raw.get(CFG_IDP_GRANT_TYPE) or DEFAULT_IDP_GRANT_TYPE)
    log_agent_api_responses = consumer_raw.get(CFG_LOG_AGENT_API_RESPONSES, False)
    allow_custom_capabilities = bool(
        consumer_raw.get(CFG_ALLOW_CUSTOM_CAPABILITIES, False)
    )
    mask: None

    log_level = consumer_raw.get(CFG_LOG_LEVEL, DEFAULT_LOG_LEVEL) or DEFAULT_LOG_LEVEL

    if not server_url:
        logger.warning("%s.%s is required", CFG_CONSUMER, CFG_SERVER_URL)
    agent_config_path = consumer_raw.get(CFG_AGENT_CONFIG_PATH, ".")

    if not agent_config_path:
        logger.warning("%s.%s is expected", CFG_CONSUMER, CFG_AGENT_CONFIG_PATH)
    additional_params = consumer_raw.get(CFG_AGENT_ADDITIONAL_PARAMS)

    if additional_params is None:
        logger.info("%s.%s no settings", CFG_CONSUMER, CFG_AGENT_ADDITIONAL_PARAMS)
    if not isinstance(additional_params, list):
        logger.info("%s.%s must be a list", CFG_CONSUMER, CFG_AGENT_ADDITIONAL_PARAMS)

    heartbeat_frequency = consumer_raw.get(CFG_HEARTBEAT_FREQUENCY, 30)
    if heartbeat_frequency is None:
        heartbeat_frequency = 30
    if heartbeat_frequency == 0:
        raise ValueError(
            f"{CFG_CONSUMER}.{CFG_HEARTBEAT_FREQUENCY} must be a non-negative integer"
        )

    mask = parse_capabilities(HARDWIRED_AGENT_CAPABILITY_NAMES, AgentCapabilities)
    client_status_port = consumer_raw.get(CFG_CLIENT_STATUS_PORT)
    chat_ops_port = consumer_raw.get(CFG_CHAT_OPS_PORT)
    full_update_controller = consumer_raw.get(
        CFG_FULL_UPDATE_CONTROLLER, DEFAULT_FULL_UPDATE_CONTROLLER
    )
    full_update_controller_type = (
        consumer_raw.get(
            CFG_FULL_UPDATE_CONTROLLER_TYPE,
            DEFAULT_FULL_UPDATE_CONTROLLER_TYPE,
        )
        or DEFAULT_FULL_UPDATE_CONTROLLER_TYPE
    )

    logger.info("loaded consumer server_url: %s", server_url)
    logger.info("loaded consumer server_port: %s", server_port)
    logger.info("loaded consumer service_name: %s", service_name)
    logger.info("loaded consumer service_namespace: %s", service_namespace)
    logger.info("loaded consumer transport: %s", transport)
    logger.info("loaded consumer tls_verify_server: %s", tls_verify_server)
    logger.info("loaded consumer tls_ca_file: %s", tls_ca_file)
    logger.info("loaded consumer server_authorization: %s", server_authorization)
    logger.info(
        "loaded consumer opamp_token configured: %s",
        bool(opamp_token),
    )
    logger.info("loaded consumer idp_token_url: %s", idp_token_url)
    logger.info("loaded consumer idp_client_id: %s", idp_client_id)
    logger.info(
        "loaded consumer idp_client_secret configured: %s",
        bool(idp_client_secret),
    )
    logger.info("loaded consumer idp_scope: %s", idp_scope)
    logger.info("loaded consumer idp_grant_type: %s", idp_grant_type)
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
    logger.info("loaded consumer full_update_controller: %s", full_update_controller)
    logger.info(
        "loaded consumer full_update_controller_type: %s",
        full_update_controller_type,
    )
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
        tls_verify_server=tls_verify_server,
        tls_ca_file=tls_ca_file,
        server_authorization=server_authorization,
        opamp_token=opamp_token,
        idp_token_url=idp_token_url,
        idp_client_id=idp_client_id,
        idp_client_secret=idp_client_secret,
        idp_scope=idp_scope,
        idp_grant_type=idp_grant_type,
        log_agent_api_responses=bool(log_agent_api_responses),
        allow_custom_capabilities=allow_custom_capabilities,
        client_status_port=(
            int(client_status_port) if client_status_port is not None else None
        ),
        chat_ops_port=int(chat_ops_port) if chat_ops_port is not None else None,
        full_update_controller=full_update_controller,
        full_update_controller_type=str(full_update_controller_type),
    )


def load_config_with_overrides(
    *,
    config_path: pathlib.Path | None,
    server_url: str | None,
    server_port: int | None,
    agent_config_path: str | None,
    agent_additional_params: list[str] | None,
    heartbeat_frequency: int | None,
    log_level: str | None,
    full_update_controller: str | None,
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
    )
    resolved_additional_params = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_AGENT_ADDITIONAL_PARAMS,
        logger=logger,
        override=agent_additional_params,
    )
    resolved_heartbeat_frequency = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_HEARTBEAT_FREQUENCY,
        logger=logger,
        override=heartbeat_frequency,
        default=30,
    )
    resolved_log_level = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_LOG_LEVEL,
        logger=logger,
        override=log_level,
        default=DEFAULT_LOG_LEVEL,
    )
    resolved_full_update_controller = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_FULL_UPDATE_CONTROLLER,
        logger=logger,
        override=full_update_controller,
        default=DEFAULT_FULL_UPDATE_CONTROLLER,
    )
    resolved_full_update_controller_type = _resolve_config_value(
        mapping=consumer_raw,
        key=CFG_FULL_UPDATE_CONTROLLER_TYPE,
        logger=logger,
        default=DEFAULT_FULL_UPDATE_CONTROLLER_TYPE,
    )
    resolved_server_authorization = _normalize_server_authorization(
        _resolve_config_value(
            mapping=consumer_raw,
            key=CFG_SERVER_AUTHORIZATION,
            logger=logger,
            default=None,
        )
    )
    resolved_opamp_token = _coerce_optional_str(consumer_raw.get(CFG_OPAMP_TOKEN))
    resolved_idp_token_url = _coerce_optional_str(consumer_raw.get(CFG_IDP_TOKEN_URL))
    resolved_idp_client_id = _coerce_optional_str(consumer_raw.get(CFG_IDP_CLIENT_ID))
    resolved_idp_client_secret = _coerce_optional_str(
        consumer_raw.get(CFG_IDP_CLIENT_SECRET)
    )
    resolved_idp_scope = _coerce_optional_str(consumer_raw.get(CFG_IDP_SCOPE))
    resolved_idp_grant_type = str(
        consumer_raw.get(CFG_IDP_GRANT_TYPE) or DEFAULT_IDP_GRANT_TYPE
    )
    tls_raw = _resolve_tls_section(consumer_raw)
    resolved_tls_verify_server = _coerce_bool(
        tls_raw.get(CFG_TLS_VERIFY_SERVER),
        default=DEFAULT_TLS_VERIFY_SERVER,
    )
    resolved_tls_ca_file = _validate_optional_file_path(
        path_value=tls_raw.get(CFG_TLS_CA_FILE),
        cfg_key=f"{CFG_CONSUMER}.{CFG_TLS}.{CFG_TLS_CA_FILE}",
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
        tls_verify_server=resolved_tls_verify_server,
        tls_ca_file=resolved_tls_ca_file,
        server_authorization=resolved_server_authorization,
        opamp_token=resolved_opamp_token,
        idp_token_url=resolved_idp_token_url,
        idp_client_id=resolved_idp_client_id,
        idp_client_secret=resolved_idp_client_secret,
        idp_scope=resolved_idp_scope,
        idp_grant_type=resolved_idp_grant_type,
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
        log_level=str(resolved_log_level or DEFAULT_LOG_LEVEL),
        full_update_controller=resolved_full_update_controller,
        full_update_controller_type=str(
            resolved_full_update_controller_type or DEFAULT_FULL_UPDATE_CONTROLLER_TYPE
        ),
    )


def set_config(config: ConsumerConfig) -> None:
    """Update the module-level config singleton."""
    global CONFIG
    CONFIG = config  # Module-level consumer config singleton.


CONFIG = load_config()  # Module-level consumer config singleton loaded at import time.
