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

"""Runtime configuration loader for broker defaults and environment overrides.

The loader merges layered sources (code defaults, broker JSON, OpAMP config)
because deployment environments vary and we need deterministic fallback behavior.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "broker": {
        "name": "opamp-conversation-broker",
        "log_level": "INFO",
        "idle_timeout_seconds": 1200,
        "sweeper_interval_seconds": 30,
        "send_idle_goodbye": True,
        "send_shutdown_goodbye": True,
    },
    "slack": {
        "command_name": "/opamp",
        "app_mention_enabled": True,
        "dm_enabled": True,
    },
    "social_collaboration": {
        "implementation": "slack",
    },
    "messages": {
        "idle_goodbye": "I've been idle for a while, so I've cleared my working context for this thread. Reply here to start again.",
        "shutdown_goodbye": "I'm going to bed now, so I'm clearing my working context for this thread. When I wake up, please remind me what you want to do.",
        "restart_notice": "I'm awake again, but I don't have my earlier working context for this thread. Tell me what you want to check.",
        "server_offline": "The OpAMP server is currently offline. Please try again shortly.",
        "slack_error_reply": "soory a bit dizzy at the moment",
        "help": "Try `/opamp status collector-a`, `/opamp health collector-a`, or mention me with a question like `@OpAMP why is collector-a unhealthy?`",
    },
    "paths": {
        "opamp_project_root": "../fluent-opamp",
        "opamp_config_path": "../fluent-opamp/config/opamp.json",
    },
    "mcp": {
        "request_timeout_seconds": 30,
        "connection_mode": "auto",
        "protocol_version_attempts": ["2025-06-18", "2025-03-26"],
        "startup_discovery_max_attempts": 5,
        "startup_discovery_initial_backoff_seconds": 0.5,
        "startup_discovery_max_backoff_seconds": 5.0,
        "startup_discovery_backoff_multiplier": 2.0,
        "startup_discovery_jitter_seconds": 0.25,
    },
    "planner": {
        "mode": "rule-first",
        "llm_enabled": True,
        "provider": "openai",
        "model": "gpt-5.2",
        "request_timeout_seconds": 30,
        "temperature": 0.0,
        "api_key_env_var": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "max_completion_tokens": 1024,
        "verify_max_completion_tokens_attempts": [64, 512],
        "prompts_config_path": "planner_prompts.json",
    },
}


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge a partial config overlay into a base dictionary.

    Why this approach:
    nested config sections should inherit defaults unless explicitly overridden,
    so a deep merge prevents callers from rewriting entire sections.

    Args:
        base: Original dictionary containing default values.
        overlay: Dictionary with runtime override values.

    Returns:
        Dict[str, Any]: A merged copy with overlay values applied.
    """
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_json_if_exists(path: Path) -> Dict[str, Any]:
    """Load JSON from disk when present, otherwise return an empty mapping.

    Why this approach:
    optional config files should not break startup; missing paths are treated as
    "use defaults" to keep local development friction low.

    Args:
        path: Filesystem path to a JSON document.

    Returns:
        Dict[str, Any]: Parsed JSON object or an empty dictionary.
    """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_runtime_config(config_path: str | None = None) -> Dict[str, Any]:
    """Build the effective broker configuration used at runtime.

    Why this approach:
    the broker must combine local broker settings and provider-discovered routes
    so downstream code can consume one normalized config object.

    Args:
        config_path: Optional explicit broker config path. When omitted, the
            loader checks ``BROKER_CONFIG_PATH`` and then bundled defaults.

    Returns:
        Dict[str, Any]: Fully merged configuration with derived provider routes.
    """
    runtime_path = Path(
        config_path
        or os.getenv("BROKER_CONFIG_PATH")
        or Path(__file__).with_name("broker.example.json")
    ).resolve()

    config = deepcopy(DEFAULTS)
    config = _deep_merge(config, _load_json_if_exists(runtime_path))

    planner_cfg = config.get("planner", {})
    if isinstance(planner_cfg, dict):
        prompts_config_path_value = str(
            planner_cfg.get("prompts_config_path", "planner_prompts.json")
        ).strip() or "planner_prompts.json"
        prompts_config_path = Path(prompts_config_path_value).expanduser()
        if not prompts_config_path.is_absolute():
            prompts_config_path = (runtime_path.parent / prompts_config_path).resolve()
        if not prompts_config_path.exists():
            raise FileNotFoundError(
                "planner prompts config file not found: "
                f"{prompts_config_path}"
            )
        prompts_config = _load_json_if_exists(prompts_config_path)
        if not isinstance(prompts_config, dict):
            raise ValueError(
                "planner prompts config must be a JSON object: "
                f"{prompts_config_path}"
            )
        system_prompt = str(prompts_config.get("system_prompt", "")).strip()
        verification_prompt = str(prompts_config.get("verification_prompt", "")).strip()
        if not system_prompt:
            raise ValueError(
                "planner prompts config missing required non-empty "
                f"'system_prompt': {prompts_config_path}"
            )
        if not verification_prompt:
            raise ValueError(
                "planner prompts config missing required non-empty "
                f"'verification_prompt': {prompts_config_path}"
            )
        planner_cfg["prompts"] = {
            "system_prompt": system_prompt,
            "verification_prompt": verification_prompt,
        }
        planner_cfg["prompts_config_path"] = str(prompts_config_path)
        config["planner"] = planner_cfg

    opamp_config_path = Path(config["paths"]["opamp_config_path"]).expanduser().resolve()
    opamp_config = _load_json_if_exists(opamp_config_path)
    provider = opamp_config.get("provider", {})
    consumer = opamp_config.get("consumer", {})

    webui_port = provider.get("webui_port", 8080)
    base_url = consumer.get("server_url", f"http://localhost:{webui_port}")
    auth_mode = provider.get("ui-use-authorization", "none")
    opamp_auth_mode = provider.get("opamp-use-authorization", "none")

    provider_routes = {
        "base_url": base_url.rstrip("/"),
        "sse_url": f"{base_url.rstrip('/')}/sse",
        "messages_url": f"{base_url.rstrip('/')}/messages",
        "mcp_url": f"{base_url.rstrip('/')}/mcp",
        "ui_use_authorization": auth_mode,
        "opamp_use_authorization": opamp_auth_mode,
    }

    config["derived"] = {
        "provider_routes": provider_routes,
        "provider_port": webui_port,
        "opamp_config_loaded": bool(opamp_config),
    }
    return config
