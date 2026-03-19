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
import sys
from dataclasses import dataclass
from typing import Any

ROOT_PATH = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from shared.opamp_config import ServerCapabilities, UTF8_ENCODING, parse_capabilities

ENV_OPAMP_CONFIG_PATH = "OPAMP_CONFIG_PATH"
CFG_PROVIDER = "provider"
CFG_SERVER_CAPABILITIES = "server_capabilities"
CFG_DELAYED_COMMS_SECONDS = "delayed_comms_seconds"
CFG_SIGNIFICANT_COMMS_SECONDS = "significant_comms_seconds"
CFG_WEBUI_PORT = "webui_port"
CFG_MINUTES_KEEP_DISCONNECTED = "minutes_keep_disconnected"
CFG_RETRY_AFTER_SECONDS = "retryAfterSeconds"

DEFAULT_DELAYED_COMMS_SECONDS = 60
DEFAULT_SIGNIFICANT_COMMS_SECONDS = 300
DEFAULT_WEBUI_PORT = 8080
DEFAULT_MINUTES_KEEP_DISCONNECTED = 30
DEFAULT_RETRY_AFTER_SECONDS = 30


@dataclass(frozen=True)
class ProviderConfig:
    server_capabilities: int
    delayed_comms_seconds: int
    significant_comms_seconds: int
    webui_port: int
    minutes_keep_disconnected: int
    retry_after_seconds: int


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


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    """Load JSON from a path, raising when missing."""
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    return json.loads(path.read_text(encoding=UTF8_ENCODING))


def load_config() -> ProviderConfig:
    """Load provider config from disk."""
    logger = logging.getLogger(__name__)
    raw = _load_json(_config_path())
    provider_raw = raw.get(CFG_PROVIDER, {})
    capability_names = provider_raw.get(CFG_SERVER_CAPABILITIES)
    if not capability_names:
        raise ValueError(f"{CFG_PROVIDER}.{CFG_SERVER_CAPABILITIES} must be a non-empty list")
    mask = parse_capabilities(capability_names, ServerCapabilities)
    logger.info("loaded provider capabilities: %s", capability_names)
    delayed = int(provider_raw.get(CFG_DELAYED_COMMS_SECONDS, DEFAULT_DELAYED_COMMS_SECONDS))
    significant = int(
        provider_raw.get(CFG_SIGNIFICANT_COMMS_SECONDS, DEFAULT_SIGNIFICANT_COMMS_SECONDS)
    )
    return ProviderConfig(
        server_capabilities=mask,
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=int(provider_raw.get(CFG_WEBUI_PORT, DEFAULT_WEBUI_PORT)),
        minutes_keep_disconnected=int(
            provider_raw.get(CFG_MINUTES_KEEP_DISCONNECTED, DEFAULT_MINUTES_KEEP_DISCONNECTED)
        ),
        retry_after_seconds=int(
            provider_raw.get(CFG_RETRY_AFTER_SECONDS, DEFAULT_RETRY_AFTER_SECONDS)
        ),
    )


def load_config_with_overrides(
    *,
    config_path: pathlib.Path | None,
    server_capabilities: list[str] | None,
) -> ProviderConfig:
    """Load provider config with CLI overrides applied."""
    logger = logging.getLogger(__name__)
    base_raw = _load_json(config_path or _config_path())
    provider_raw = base_raw.get(CFG_PROVIDER, {})
    if server_capabilities is not None:
        logger.info(
            "cli override %s.%s; ignoring config value",
            CFG_PROVIDER,
            CFG_SERVER_CAPABILITIES,
        )
        provider_raw[CFG_SERVER_CAPABILITIES] = server_capabilities

    temp_raw = {CFG_PROVIDER: provider_raw}
    capability_names = temp_raw.get(CFG_PROVIDER, {}).get(CFG_SERVER_CAPABILITIES)
    if not capability_names:
        raise ValueError(f"{CFG_PROVIDER}.{CFG_SERVER_CAPABILITIES} must be a non-empty list")
    mask = parse_capabilities(capability_names, ServerCapabilities)
    delayed = int(provider_raw.get(CFG_DELAYED_COMMS_SECONDS, DEFAULT_DELAYED_COMMS_SECONDS))
    significant = int(
        provider_raw.get(CFG_SIGNIFICANT_COMMS_SECONDS, DEFAULT_SIGNIFICANT_COMMS_SECONDS)
    )
    return ProviderConfig(
        server_capabilities=mask,
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=int(provider_raw.get(CFG_WEBUI_PORT, DEFAULT_WEBUI_PORT)),
        minutes_keep_disconnected=int(
            provider_raw.get(CFG_MINUTES_KEEP_DISCONNECTED, DEFAULT_MINUTES_KEEP_DISCONNECTED)
        ),
        retry_after_seconds=int(
            provider_raw.get(CFG_RETRY_AFTER_SECONDS, DEFAULT_RETRY_AFTER_SECONDS)
        ),
    )


def set_config(config: ProviderConfig) -> None:
    """Update the module-level config singleton."""
    global CONFIG
    CONFIG = config


def update_comms_thresholds(*, delayed: int, significant: int) -> ProviderConfig:
    """Return a new config with updated comm thresholds and set it."""
    config = ProviderConfig(
        server_capabilities=CONFIG.server_capabilities,
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=CONFIG.webui_port,
        minutes_keep_disconnected=CONFIG.minutes_keep_disconnected,
        retry_after_seconds=CONFIG.retry_after_seconds,
    )
    set_config(config)
    return config


CONFIG = load_config()
