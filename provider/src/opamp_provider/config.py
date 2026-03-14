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

DEFAULT_DELAYED_COMMS_SECONDS = 60
DEFAULT_SIGNIFICANT_COMMS_SECONDS = 300
DEFAULT_WEBUI_PORT = 8080


@dataclass(frozen=True)
class ProviderConfig:
    server_capabilities: int
    delayed_comms_seconds: int
    significant_comms_seconds: int
    webui_port: int


def _repo_root() -> pathlib.Path:
    return ROOT_PATH


def _ensure_shared_on_path() -> None:
    return None


def _config_path() -> pathlib.Path:
    path = os.environ.get(ENV_OPAMP_CONFIG_PATH)
    if path:
        return pathlib.Path(path)
    return _repo_root() / "config" / "opamp.json"


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    return json.loads(path.read_text(encoding=UTF8_ENCODING))


def load_config() -> ProviderConfig:
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
    )


def load_config_with_overrides(
    *,
    config_path: pathlib.Path | None,
    server_capabilities: list[str] | None,
) -> ProviderConfig:
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
    )


def set_config(config: ProviderConfig) -> None:
    global CONFIG
    CONFIG = config


def update_comms_thresholds(*, delayed: int, significant: int) -> ProviderConfig:
    config = ProviderConfig(
        server_capabilities=CONFIG.server_capabilities,
        delayed_comms_seconds=delayed,
        significant_comms_seconds=significant,
        webui_port=CONFIG.webui_port,
    )
    set_config(config)
    return config


CONFIG = load_config()
