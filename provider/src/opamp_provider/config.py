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

"""Configuration loader for the OpAMP provider."""

from __future__ import annotations

import json
import logging
import os
import pathlib
import shutil
import sys
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

ROOT_PATH = pathlib.Path(__file__).resolve().parents[3]  # Repository root used for default config path resolution.
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from shared.opamp_config import UTF8_ENCODING

ENV_OPAMP_CONFIG_PATH = "OPAMP_CONFIG_PATH"  # Environment variable overriding provider config file location.
CFG_PROVIDER = "provider"  # Top-level JSON section name for provider settings.
CFG_DELAYED_COMMS_SECONDS = "delayed_comms_seconds"  # Provider JSON key for delayed comms threshold.
CFG_SIGNIFICANT_COMMS_SECONDS = "significant_comms_seconds"  # Provider JSON key for significant comms threshold.
CFG_WEBUI_PORT = "webui_port"  # Provider JSON key for web UI listen port.
CFG_MINUTES_KEEP_DISCONNECTED = "minutes_keep_disconnected"  # Provider JSON key for disconnected-client retention window.
CFG_RETRY_AFTER_SECONDS = "retryAfterSeconds"  # Provider JSON key for Retry-After value on throttled responses.
CFG_CLIENT_EVENT_HISTORY_SIZE = "client_event_history_size"  # Provider JSON key for per-client event history length.
CFG_LOG_LEVEL = "log_level"  # Provider JSON key for logging level override.
CFG_DEFAULT_HEARTBEAT_FREQUENCY = "default_heartbeat_frequency"  # Provider JSON key for default client heartbeat interval.
CFG_LATEST_DOCS_URL = "latest_docs_url"  # Provider JSON key for Latest docs redirect URL.
CFG_HUMAN_IN_LOOP_APPROVAL = "human_in_loop_approval"  # Provider JSON key toggling manual agent approval workflow.
CFG_OPAMP_USE_AUTHORIZATION = "opamp-use-authorization"  # Provider JSON key controlling OpAMP transport bearer authorization mode.
CFG_UI_USE_AUTHORIZATION = "ui-use-authorization"  # Provider JSON key controlling non-OpAMP HTTP/WebSocket bearer authorization mode.
CFG_TLS = "tls"  # Provider JSON key for shared TLS server settings.
CFG_TLS_ENABLED = "enabled"  # Provider TLS key toggling HTTPS/TLS listener mode.
CFG_TLS_CERT_FILE = "cert_file"  # Provider TLS key for server certificate path.
CFG_TLS_KEY_FILE = "key_file"  # Provider TLS key for server private key path.
CFG_TLS_TRUST_ANCHOR_MODE = "trust_anchor_mode"  # Provider TLS key for trust-anchor policy mode.
CFG_STATE_PERSISTENCE = "state_persistence"  # Provider JSON key for runtime state persistence settings.
CFG_STATE_PERSISTENCE_ENABLED = "enabled"  # Provider state persistence key toggling snapshot persistence.
CFG_STATE_FILE_PREFIX = "state_file_prefix"  # Provider state persistence key for snapshot path prefix.
CFG_STATE_RETENTION_COUNT = "retention_count"  # Provider state persistence key for number of retained snapshots.
CFG_STATE_FLUSH_MODE = "flush_mode"  # Provider state persistence key for flush strategy.
CFG_STATE_AUTOSAVE_INTERVAL = (
    "autosave_interval_seconds_since_change"
)  # Provider state persistence key for autosave interval in seconds.

DEFAULT_DELAYED_COMMS_SECONDS = 60  # Default delayed comms threshold in seconds.
DEFAULT_SIGNIFICANT_COMMS_SECONDS = 300  # Default significant comms threshold in seconds.
DEFAULT_WEBUI_PORT = 8080  # Default web UI listening port.
DEFAULT_MINUTES_KEEP_DISCONNECTED = 30  # Default retention window for disconnected clients in minutes.
DEFAULT_RETRY_AFTER_SECONDS = 30  # Default Retry-After duration in seconds.
DEFAULT_CLIENT_EVENT_HISTORY_SIZE = 50  # Default maximum number of retained client events.
DEFAULT_LOG_LEVEL = "INFO"  # Default provider log level.
DEFAULT_DEFAULT_HEARTBEAT_FREQUENCY = 30  # Default heartbeat frequency assigned to new clients.
DEFAULT_LATEST_DOCS_URL = "https://github.com/mp3monster/fluent-opamp/blob/main/README.md"  # Default redirect target for /doc-set.
DEFAULT_HUMAN_IN_LOOP_APPROVAL = False  # Default behavior leaves human approval workflow disabled.
OPAMP_USE_AUTHORIZATION_NONE = "none"  # Disable OpAMP endpoint bearer auth checks.
OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN = (
    "config-token"  # Validate OpAMP bearer token against OPAMP_AUTH_STATIC_TOKEN.
)
OPAMP_USE_AUTHORIZATION_IDP = (
    "idp"  # Validate OpAMP bearer token via IdP JWT verification settings.
)
DEFAULT_OPAMP_USE_AUTHORIZATION = OPAMP_USE_AUTHORIZATION_NONE  # Default OpAMP auth mode.
DEFAULT_UI_USE_AUTHORIZATION = OPAMP_USE_AUTHORIZATION_NONE  # Default non-OpAMP auth mode.
DEFAULT_TLS_ENABLED = True  # Default TLS enabled state when provider.tls section is present.
TLS_TRUST_ANCHOR_PARTIAL_CHAIN = "partial_chain"  # Trust-anchor mode allowing intermediate anchors.
TLS_TRUST_ANCHOR_FULL_CHAIN_TO_ROOT = "full_chain_to_root"  # Trust-anchor mode requiring root anchors.
TLS_TRUST_ANCHOR_NONE = "none"  # Trust-anchor mode for local self-signed development without CA-anchor checks.
DEFAULT_TLS_TRUST_ANCHOR_MODE = TLS_TRUST_ANCHOR_FULL_CHAIN_TO_ROOT  # Default provider trust-anchor mode.
DEFAULT_STATE_PERSISTENCE_ENABLED = False  # Default persistence behavior remains in-memory only.
DEFAULT_STATE_FILE_PREFIX = "runtime/opamp_server_state"  # Default snapshot file prefix.
DEFAULT_STATE_RETENTION_COUNT = 5  # Default retained snapshot count.
DEFAULT_STATE_FLUSH_MODE = "graceful_shutdown"  # Default persistence flush mode.
DEFAULT_STATE_AUTOSAVE_INTERVAL = 600  # Default autosave interval in seconds.


@dataclass(frozen=True)
class ProviderTLSConfig:
    cert_file: str
    key_file: str
    trust_anchor_mode: str = DEFAULT_TLS_TRUST_ANCHOR_MODE


@dataclass(frozen=True)
class ProviderStatePersistenceConfig:
    enabled: bool = DEFAULT_STATE_PERSISTENCE_ENABLED
    state_file_prefix: str = DEFAULT_STATE_FILE_PREFIX
    retention_count: int = DEFAULT_STATE_RETENTION_COUNT
    flush_mode: str = DEFAULT_STATE_FLUSH_MODE
    autosave_interval_seconds_since_change: int = DEFAULT_STATE_AUTOSAVE_INTERVAL


@dataclass(frozen=True)
class ProviderConfig:
    delayed_comms_seconds: int
    significant_comms_seconds: int
    webui_port: int
    minutes_keep_disconnected: int
    retry_after_seconds: int
    client_event_history_size: int
    log_level: str
    default_heartbeat_frequency: int = DEFAULT_DEFAULT_HEARTBEAT_FREQUENCY
    latest_docs_url: str = DEFAULT_LATEST_DOCS_URL
    human_in_loop_approval: bool = DEFAULT_HUMAN_IN_LOOP_APPROVAL
    opamp_use_authorization: str = DEFAULT_OPAMP_USE_AUTHORIZATION
    ui_use_authorization: str = DEFAULT_UI_USE_AUTHORIZATION
    tls: ProviderTLSConfig | None = None
    state_persistence: ProviderStatePersistenceConfig = field(
        default_factory=ProviderStatePersistenceConfig
    )


def resolve_log_level(log_level: str | None) -> int:
    """Resolve a log level name to a logging level using logging's level map."""
    normalized_level = str(log_level or DEFAULT_LOG_LEVEL).strip().upper()
    # Use getLevelName() for compatibility with Python 3.10 where
    # getLevelNamesMapping() is not available.
    level = logging.getLevelName(normalized_level)
    if isinstance(level, int):
        return level
    return logging.INFO


def _repo_root() -> pathlib.Path:
    """Return the repository root path."""
    return ROOT_PATH


def _ensure_shared_on_path() -> None:
    """Compatibility no-op for shared import handling."""
    return None


def _config_path() -> pathlib.Path:
    """Resolve the provider config path from environment or default."""
    path = os.environ.get(ENV_OPAMP_CONFIG_PATH)
    if path:
        return pathlib.Path(path)
    return _repo_root() / "config" / "opamp.json"


def get_effective_config_path(config_path: str | pathlib.Path | None = None) -> pathlib.Path:
    """Return the effective provider config path used for loading configuration."""
    if config_path is not None:
        return pathlib.Path(config_path)
    return _config_path()


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    """Load JSON from a path, raising when missing."""
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    return json.loads(path.read_text(encoding=UTF8_ENCODING))


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce common JSON/env boolean forms while preserving explicit defaults."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default if value is None else bool(value)


def _normalize_authorization_mode(
    value: Any,
    *,
    cfg_key: str,
    default_mode: str,
) -> str:
    """Normalize auth mode from canonical provider config values."""
    if value is None:
        return default_mode
    normalized = str(value).strip().lower()
    if not normalized:
        return default_mode
    if normalized in {
        OPAMP_USE_AUTHORIZATION_NONE,
        OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN,
        OPAMP_USE_AUTHORIZATION_IDP,
    }:
        return normalized
    logging.getLogger(__name__).warning(
        "invalid provider %s value %r; defaulting to %s",
        cfg_key,
        value,
        default_mode,
    )
    return default_mode


def _normalize_trust_anchor_mode(value: Any) -> str:
    """Normalize trust-anchor mode from provider TLS config values."""
    if value is None:
        return DEFAULT_TLS_TRUST_ANCHOR_MODE
    normalized = str(value).strip().lower()
    if not normalized:
        return DEFAULT_TLS_TRUST_ANCHOR_MODE
    if normalized in {
        TLS_TRUST_ANCHOR_NONE,
        TLS_TRUST_ANCHOR_PARTIAL_CHAIN,
        TLS_TRUST_ANCHOR_FULL_CHAIN_TO_ROOT,
    }:
        return normalized
    raise ValueError(
        f"{CFG_PROVIDER}.{CFG_TLS}.{CFG_TLS_TRUST_ANCHOR_MODE} has unsupported value "
        f"{value!r}"
    )


def _validate_required_file_path(*, cfg_key: str, value: Any) -> str:
    """Validate required file path settings and return normalized path string."""
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{cfg_key} is required")
    path = pathlib.Path(normalized)
    if not path.exists() or not path.is_file():
        raise ValueError(f"{cfg_key} must reference an existing file")
    return normalized


def _load_provider_tls_config(provider_raw: dict[str, Any]) -> ProviderTLSConfig | None:
    """Load provider TLS settings from provider config mapping."""
    tls_raw = provider_raw.get(CFG_TLS)
    if tls_raw is None:
        return None
    if not isinstance(tls_raw, dict):
        raise ValueError(f"{CFG_PROVIDER}.{CFG_TLS} must be an object")
    tls_enabled = _as_bool(tls_raw.get(CFG_TLS_ENABLED), DEFAULT_TLS_ENABLED)
    if not tls_enabled:
        return None
    cert_file = _validate_required_file_path(
        cfg_key=f"{CFG_PROVIDER}.{CFG_TLS}.{CFG_TLS_CERT_FILE}",
        value=tls_raw.get(CFG_TLS_CERT_FILE),
    )
    key_file = _validate_required_file_path(
        cfg_key=f"{CFG_PROVIDER}.{CFG_TLS}.{CFG_TLS_KEY_FILE}",
        value=tls_raw.get(CFG_TLS_KEY_FILE),
    )
    return ProviderTLSConfig(
        cert_file=cert_file,
        key_file=key_file,
        trust_anchor_mode=_normalize_trust_anchor_mode(
            tls_raw.get(CFG_TLS_TRUST_ANCHOR_MODE)
        ),
    )


def _validate_state_persistence_directory(
    *,
    state_file_prefix: str,
) -> tuple[bool, str]:
    """Validate state snapshot directory readability/writability; create when missing."""
    prefix_path = pathlib.Path(str(state_file_prefix).strip() or DEFAULT_STATE_FILE_PREFIX)
    directory = prefix_path.parent
    if str(directory).strip() in {"", "."}:
        directory = pathlib.Path.cwd()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return False, f"failed to create state persistence directory {directory}: {exc}"
    if not directory.exists() or not directory.is_dir():
        return False, f"state persistence directory is not a directory: {directory}"
    if not os.access(directory, os.R_OK | os.W_OK):
        return False, f"state persistence directory must be readable and writable: {directory}"
    return True, str(directory)


def _load_state_persistence_config(
    provider_raw: dict[str, Any],
) -> ProviderStatePersistenceConfig:
    """Load and validate provider state persistence settings from config mapping."""
    raw = provider_raw.get(CFG_STATE_PERSISTENCE)
    if raw is None:
        return ProviderStatePersistenceConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"{CFG_PROVIDER}.{CFG_STATE_PERSISTENCE} must be an object")
    enabled = _as_bool(
        raw.get(CFG_STATE_PERSISTENCE_ENABLED),
        DEFAULT_STATE_PERSISTENCE_ENABLED,
    )
    state_file_prefix = str(
        raw.get(CFG_STATE_FILE_PREFIX, DEFAULT_STATE_FILE_PREFIX) or DEFAULT_STATE_FILE_PREFIX
    ).strip()
    if not state_file_prefix:
        state_file_prefix = DEFAULT_STATE_FILE_PREFIX
    retention_count = max(
        1,
        int(raw.get(CFG_STATE_RETENTION_COUNT, DEFAULT_STATE_RETENTION_COUNT)),
    )
    autosave_interval_seconds_since_change = max(
        1,
        int(raw.get(CFG_STATE_AUTOSAVE_INTERVAL, DEFAULT_STATE_AUTOSAVE_INTERVAL)),
    )
    flush_mode = str(raw.get(CFG_STATE_FLUSH_MODE, DEFAULT_STATE_FLUSH_MODE)).strip()
    if not flush_mode:
        flush_mode = DEFAULT_STATE_FLUSH_MODE
    config = ProviderStatePersistenceConfig(
        enabled=enabled,
        state_file_prefix=state_file_prefix,
        retention_count=retention_count,
        flush_mode=flush_mode,
        autosave_interval_seconds_since_change=autosave_interval_seconds_since_change,
    )
    if not config.enabled:
        return config
    valid, reason = _validate_state_persistence_directory(
        state_file_prefix=config.state_file_prefix
    )
    if valid:
        return config
    logging.getLogger(__name__).error(
        "state persistence disabled for this run: %s",
        reason,
    )
    return ProviderStatePersistenceConfig(
        enabled=False,
        state_file_prefix=config.state_file_prefix,
        retention_count=config.retention_count,
        flush_mode=config.flush_mode,
        autosave_interval_seconds_since_change=config.autosave_interval_seconds_since_change,
    )


def load_config() -> ProviderConfig:
    """Load provider config from disk."""
    raw = _load_json(_config_path())
    provider_raw = raw.get(CFG_PROVIDER, {})
    tls_config = _load_provider_tls_config(provider_raw)
    state_persistence_config = _load_state_persistence_config(provider_raw)
    delayed = int(provider_raw.get(CFG_DELAYED_COMMS_SECONDS, DEFAULT_DELAYED_COMMS_SECONDS))
    significant = int(
        provider_raw.get(CFG_SIGNIFICANT_COMMS_SECONDS, DEFAULT_SIGNIFICANT_COMMS_SECONDS)
    )
    opamp_use_authorization_raw = provider_raw.get(CFG_OPAMP_USE_AUTHORIZATION)
    ui_use_authorization_raw = provider_raw.get(CFG_UI_USE_AUTHORIZATION)
    latest_docs_url = str(
        provider_raw.get(CFG_LATEST_DOCS_URL, DEFAULT_LATEST_DOCS_URL)
        or DEFAULT_LATEST_DOCS_URL
    ).strip()
    if not latest_docs_url:
        latest_docs_url = DEFAULT_LATEST_DOCS_URL
    return ProviderConfig(
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=int(provider_raw.get(CFG_WEBUI_PORT, DEFAULT_WEBUI_PORT)),
        minutes_keep_disconnected=int(
            provider_raw.get(CFG_MINUTES_KEEP_DISCONNECTED, DEFAULT_MINUTES_KEEP_DISCONNECTED)
        ),
        retry_after_seconds=int(
            provider_raw.get(CFG_RETRY_AFTER_SECONDS, DEFAULT_RETRY_AFTER_SECONDS)
        ),
        client_event_history_size=max(
            1,
            int(
                provider_raw.get(
                    CFG_CLIENT_EVENT_HISTORY_SIZE, DEFAULT_CLIENT_EVENT_HISTORY_SIZE
                )
            ),
        ),
        log_level=str(provider_raw.get(CFG_LOG_LEVEL, DEFAULT_LOG_LEVEL)),
        default_heartbeat_frequency=max(
            1,
            int(
                provider_raw.get(
                    CFG_DEFAULT_HEARTBEAT_FREQUENCY,
                    DEFAULT_DEFAULT_HEARTBEAT_FREQUENCY,
                )
            ),
        ),
        latest_docs_url=latest_docs_url,
        human_in_loop_approval=_as_bool(
            provider_raw.get(
                CFG_HUMAN_IN_LOOP_APPROVAL,
                DEFAULT_HUMAN_IN_LOOP_APPROVAL,
            ),
            DEFAULT_HUMAN_IN_LOOP_APPROVAL,
        ),
        opamp_use_authorization=_normalize_authorization_mode(
            opamp_use_authorization_raw,
            cfg_key=CFG_OPAMP_USE_AUTHORIZATION,
            default_mode=DEFAULT_OPAMP_USE_AUTHORIZATION,
        ),
        ui_use_authorization=_normalize_authorization_mode(
            ui_use_authorization_raw,
            cfg_key=CFG_UI_USE_AUTHORIZATION,
            default_mode=DEFAULT_UI_USE_AUTHORIZATION,
        ),
        tls=tls_config,
        state_persistence=state_persistence_config,
    )


def load_config_with_overrides(
    *,
    config_path: pathlib.Path | None,
    log_level: str | None,
) -> ProviderConfig:
    """Load provider config with CLI overrides applied."""
    base_raw = _load_json(config_path or _config_path())
    provider_raw = base_raw.get(CFG_PROVIDER, {})
    tls_config = _load_provider_tls_config(provider_raw)
    state_persistence_config = _load_state_persistence_config(provider_raw)
    delayed = int(provider_raw.get(CFG_DELAYED_COMMS_SECONDS, DEFAULT_DELAYED_COMMS_SECONDS))
    significant = int(
        provider_raw.get(CFG_SIGNIFICANT_COMMS_SECONDS, DEFAULT_SIGNIFICANT_COMMS_SECONDS)
    )
    opamp_use_authorization_raw = provider_raw.get(CFG_OPAMP_USE_AUTHORIZATION)
    ui_use_authorization_raw = provider_raw.get(CFG_UI_USE_AUTHORIZATION)
    latest_docs_url = str(
        provider_raw.get(CFG_LATEST_DOCS_URL, DEFAULT_LATEST_DOCS_URL)
        or DEFAULT_LATEST_DOCS_URL
    ).strip()
    if not latest_docs_url:
        latest_docs_url = DEFAULT_LATEST_DOCS_URL
    return ProviderConfig(
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=int(provider_raw.get(CFG_WEBUI_PORT, DEFAULT_WEBUI_PORT)),
        minutes_keep_disconnected=int(
            provider_raw.get(CFG_MINUTES_KEEP_DISCONNECTED, DEFAULT_MINUTES_KEEP_DISCONNECTED)
        ),
        retry_after_seconds=int(
            provider_raw.get(CFG_RETRY_AFTER_SECONDS, DEFAULT_RETRY_AFTER_SECONDS)
        ),
        client_event_history_size=max(
            1,
            int(
                provider_raw.get(
                    CFG_CLIENT_EVENT_HISTORY_SIZE, DEFAULT_CLIENT_EVENT_HISTORY_SIZE
                )
            ),
        ),
        log_level=str(provider_raw.get(CFG_LOG_LEVEL, DEFAULT_LOG_LEVEL))
        if log_level is None
        else str(log_level),
        default_heartbeat_frequency=max(
            1,
            int(
                provider_raw.get(
                    CFG_DEFAULT_HEARTBEAT_FREQUENCY,
                    DEFAULT_DEFAULT_HEARTBEAT_FREQUENCY,
                )
            ),
        ),
        latest_docs_url=latest_docs_url,
        human_in_loop_approval=_as_bool(
            provider_raw.get(
                CFG_HUMAN_IN_LOOP_APPROVAL,
                DEFAULT_HUMAN_IN_LOOP_APPROVAL,
            ),
            DEFAULT_HUMAN_IN_LOOP_APPROVAL,
        ),
        opamp_use_authorization=_normalize_authorization_mode(
            opamp_use_authorization_raw,
            cfg_key=CFG_OPAMP_USE_AUTHORIZATION,
            default_mode=DEFAULT_OPAMP_USE_AUTHORIZATION,
        ),
        ui_use_authorization=_normalize_authorization_mode(
            ui_use_authorization_raw,
            cfg_key=CFG_UI_USE_AUTHORIZATION,
            default_mode=DEFAULT_UI_USE_AUTHORIZATION,
        ),
        tls=tls_config,
        state_persistence=state_persistence_config,
    )


def set_config(config: ProviderConfig) -> None:
    """Update the module-level config singleton."""
    global CONFIG
    CONFIG = config  # Module-level provider config singleton.


def update_comms_thresholds(
    *,
    delayed: int,
    significant: int,
    minutes_keep_disconnected: int | None = None,
    client_event_history_size: int | None = None,
    human_in_loop_approval: bool | None = None,
    state_persistence_enabled: bool | None = None,
    state_save_folder: str | None = None,
    retention_count: int | None = None,
    autosave_interval_seconds_since_change: int | None = None,
) -> ProviderConfig:
    """Return a new config with updated server comm settings and set it."""
    keep_minutes = (
        CONFIG.minutes_keep_disconnected
        if minutes_keep_disconnected is None
        else int(minutes_keep_disconnected)
    )
    if keep_minutes <= 0:
        raise ValueError("minutes_keep_disconnected must be positive")
    history_size = (
        CONFIG.client_event_history_size
        if client_event_history_size is None
        else max(1, int(client_event_history_size))
    )
    effective_human_in_loop_approval = (
        CONFIG.human_in_loop_approval
        if human_in_loop_approval is None
        else bool(human_in_loop_approval)
    )
    persistence = CONFIG.state_persistence
    if state_persistence_enabled is not None:
        persistence = ProviderStatePersistenceConfig(
            enabled=bool(state_persistence_enabled),
            state_file_prefix=persistence.state_file_prefix,
            retention_count=persistence.retention_count,
            flush_mode=persistence.flush_mode,
            autosave_interval_seconds_since_change=(
                persistence.autosave_interval_seconds_since_change
            ),
        )
    if state_save_folder is not None:
        folder = str(state_save_folder).strip()
        if not folder:
            raise ValueError("state_save_folder must be a non-empty string")
        current_prefix = pathlib.Path(persistence.state_file_prefix)
        base_name = current_prefix.name or "opamp_server_state"
        proposed_prefix = str(pathlib.Path(folder) / base_name)
        valid, reason = _validate_state_persistence_directory(
            state_file_prefix=proposed_prefix
        )
        if not valid:
            raise ValueError(reason)
        persistence = ProviderStatePersistenceConfig(
            enabled=persistence.enabled,
            state_file_prefix=proposed_prefix,
            retention_count=persistence.retention_count,
            flush_mode=persistence.flush_mode,
            autosave_interval_seconds_since_change=(
                persistence.autosave_interval_seconds_since_change
            ),
        )
    if autosave_interval_seconds_since_change is not None:
        interval = int(autosave_interval_seconds_since_change)
        if interval <= 0:
            raise ValueError("autosave_interval_seconds_since_change must be positive")
        persistence = ProviderStatePersistenceConfig(
            enabled=persistence.enabled,
            state_file_prefix=persistence.state_file_prefix,
            retention_count=persistence.retention_count,
            flush_mode=persistence.flush_mode,
            autosave_interval_seconds_since_change=interval,
        )
    if retention_count is not None:
        keep = int(retention_count)
        if keep <= 0:
            raise ValueError("retention_count must be positive")
        persistence = ProviderStatePersistenceConfig(
            enabled=persistence.enabled,
            state_file_prefix=persistence.state_file_prefix,
            retention_count=keep,
            flush_mode=persistence.flush_mode,
            autosave_interval_seconds_since_change=(
                persistence.autosave_interval_seconds_since_change
            ),
        )
    config = ProviderConfig(
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=CONFIG.webui_port,
        minutes_keep_disconnected=keep_minutes,
        retry_after_seconds=CONFIG.retry_after_seconds,
        client_event_history_size=history_size,
        log_level=CONFIG.log_level,
        default_heartbeat_frequency=CONFIG.default_heartbeat_frequency,
        latest_docs_url=CONFIG.latest_docs_url,
        human_in_loop_approval=effective_human_in_loop_approval,
        opamp_use_authorization=CONFIG.opamp_use_authorization,
        ui_use_authorization=CONFIG.ui_use_authorization,
        tls=CONFIG.tls,
        state_persistence=persistence,
    )
    set_config(config)
    return config


def update_default_heartbeat_frequency(*, default_heartbeat_frequency: int) -> ProviderConfig:
    """Return a new config with updated default heartbeat frequency and set it."""
    config = ProviderConfig(
        delayed_comms_seconds=CONFIG.delayed_comms_seconds,
        significant_comms_seconds=CONFIG.significant_comms_seconds,
        webui_port=CONFIG.webui_port,
        minutes_keep_disconnected=CONFIG.minutes_keep_disconnected,
        retry_after_seconds=CONFIG.retry_after_seconds,
        client_event_history_size=CONFIG.client_event_history_size,
        log_level=CONFIG.log_level,
        default_heartbeat_frequency=max(1, int(default_heartbeat_frequency)),
        latest_docs_url=CONFIG.latest_docs_url,
        human_in_loop_approval=CONFIG.human_in_loop_approval,
        opamp_use_authorization=CONFIG.opamp_use_authorization,
        ui_use_authorization=CONFIG.ui_use_authorization,
        tls=CONFIG.tls,
        state_persistence=CONFIG.state_persistence,
    )
    set_config(config)
    return config


def persist_provider_config(
    config: ProviderConfig | None = None,
    *,
    config_path: str | pathlib.Path | None = None,
) -> pathlib.Path:
    """Write provider config values back to opamp.json."""
    resolved_path = get_effective_config_path(config_path)
    raw = _load_json(resolved_path)
    provider_raw = raw.get(CFG_PROVIDER)
    if not isinstance(provider_raw, dict):
        provider_raw = {}
        raw[CFG_PROVIDER] = provider_raw

    effective = config or CONFIG
    provider_raw[CFG_DELAYED_COMMS_SECONDS] = int(effective.delayed_comms_seconds)
    provider_raw[CFG_SIGNIFICANT_COMMS_SECONDS] = int(
        effective.significant_comms_seconds
    )
    provider_raw[CFG_WEBUI_PORT] = int(effective.webui_port)
    provider_raw[CFG_MINUTES_KEEP_DISCONNECTED] = int(
        effective.minutes_keep_disconnected
    )
    provider_raw[CFG_RETRY_AFTER_SECONDS] = int(effective.retry_after_seconds)
    provider_raw[CFG_CLIENT_EVENT_HISTORY_SIZE] = int(effective.client_event_history_size)
    provider_raw[CFG_LOG_LEVEL] = str(effective.log_level)
    provider_raw[CFG_DEFAULT_HEARTBEAT_FREQUENCY] = int(
        effective.default_heartbeat_frequency
    )
    provider_raw[CFG_LATEST_DOCS_URL] = str(effective.latest_docs_url)
    provider_raw[CFG_HUMAN_IN_LOOP_APPROVAL] = bool(effective.human_in_loop_approval)
    provider_raw[CFG_OPAMP_USE_AUTHORIZATION] = str(effective.opamp_use_authorization)
    provider_raw[CFG_UI_USE_AUTHORIZATION] = str(effective.ui_use_authorization)
    provider_raw[CFG_STATE_PERSISTENCE] = {
        CFG_STATE_PERSISTENCE_ENABLED: bool(effective.state_persistence.enabled),
        CFG_STATE_FILE_PREFIX: str(effective.state_persistence.state_file_prefix),
        CFG_STATE_RETENTION_COUNT: int(effective.state_persistence.retention_count),
        CFG_STATE_FLUSH_MODE: str(effective.state_persistence.flush_mode),
        CFG_STATE_AUTOSAVE_INTERVAL: int(
            effective.state_persistence.autosave_interval_seconds_since_change
        ),
    }

    backup_path = _build_backup_path(resolved_path)
    logging.getLogger(__name__).info(
        "persist_provider_config backing up %s to %s before write",
        resolved_path,
        backup_path,
    )
    shutil.copy2(resolved_path, backup_path)

    resolved_path.write_text(
        f"{json.dumps(raw, indent=2)}\n",
        encoding=UTF8_ENCODING,
    )
    return resolved_path


def _build_backup_path(config_path: pathlib.Path) -> pathlib.Path:
    """Return a unique timestamped backup path like opamp.json.<date time>."""
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup_path = config_path.with_name(f"{config_path.name}.{timestamp}")
    suffix = 1
    while backup_path.exists():
        backup_path = config_path.with_name(f"{config_path.name}.{timestamp}.{suffix}")
        suffix += 1
    return backup_path


CONFIG = load_config()  # Module-level provider config singleton loaded at import time.
