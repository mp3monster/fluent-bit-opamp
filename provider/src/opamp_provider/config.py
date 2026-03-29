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
from dataclasses import dataclass
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

DEFAULT_DELAYED_COMMS_SECONDS = 60  # Default delayed comms threshold in seconds.
DEFAULT_SIGNIFICANT_COMMS_SECONDS = 300  # Default significant comms threshold in seconds.
DEFAULT_WEBUI_PORT = 8080  # Default web UI listening port.
DEFAULT_MINUTES_KEEP_DISCONNECTED = 30  # Default retention window for disconnected clients in minutes.
DEFAULT_RETRY_AFTER_SECONDS = 30  # Default Retry-After duration in seconds.
DEFAULT_CLIENT_EVENT_HISTORY_SIZE = 50  # Default maximum number of retained client events.
DEFAULT_LOG_LEVEL = "INFO"  # Default provider log level.
DEFAULT_DEFAULT_HEARTBEAT_FREQUENCY = 30  # Default heartbeat frequency assigned to new clients.


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


def load_config() -> ProviderConfig:
    """Load provider config from disk."""
    raw = _load_json(_config_path())
    provider_raw = raw.get(CFG_PROVIDER, {})
    delayed = int(provider_raw.get(CFG_DELAYED_COMMS_SECONDS, DEFAULT_DELAYED_COMMS_SECONDS))
    significant = int(
        provider_raw.get(CFG_SIGNIFICANT_COMMS_SECONDS, DEFAULT_SIGNIFICANT_COMMS_SECONDS)
    )
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
    )


def load_config_with_overrides(
    *,
    config_path: pathlib.Path | None,
    log_level: str | None,
) -> ProviderConfig:
    """Load provider config with CLI overrides applied."""
    base_raw = _load_json(config_path or _config_path())
    provider_raw = base_raw.get(CFG_PROVIDER, {})
    delayed = int(provider_raw.get(CFG_DELAYED_COMMS_SECONDS, DEFAULT_DELAYED_COMMS_SECONDS))
    significant = int(
        provider_raw.get(CFG_SIGNIFICANT_COMMS_SECONDS, DEFAULT_SIGNIFICANT_COMMS_SECONDS)
    )
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
    )


def set_config(config: ProviderConfig) -> None:
    """Update the module-level config singleton."""
    global CONFIG
    CONFIG = config  # Module-level provider config singleton.


def update_comms_thresholds(
    *,
    delayed: int,
    significant: int,
    client_event_history_size: int | None = None,
) -> ProviderConfig:
    """Return a new config with updated server comm settings and set it."""
    history_size = (
        CONFIG.client_event_history_size
        if client_event_history_size is None
        else max(1, int(client_event_history_size))
    )
    config = ProviderConfig(
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=CONFIG.webui_port,
        minutes_keep_disconnected=CONFIG.minutes_keep_disconnected,
        retry_after_seconds=CONFIG.retry_after_seconds,
        client_event_history_size=history_size,
        log_level=CONFIG.log_level,
        default_heartbeat_frequency=CONFIG.default_heartbeat_frequency,
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
