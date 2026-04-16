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

"""Factory for AI connection providers and normalized planner runtime settings."""

from __future__ import annotations

import os
from typing import Any

from opamp_broker.planner.ai_connection import AIConnection
from opamp_broker.planner.constants import (
    DEFAULT_AI_SVC_API_KEY_ENV,
    DEFAULT_AI_SVC_BASE_URL,
    DEFAULT_AI_SVC_PROVIDER,
)
from opamp_broker.planner.openai_compatible_connection import OpenAICompatibleConnection
from opamp_broker.planner.template_ai_connection import TemplateAIConnection

_PROVIDER_ALIASES: dict[str, str] = {
    "openai": "openai",
    "openai-compatible": "openai",
    "openai_compatible": "openai",
    "template": "template",
}

_DEFAULT_MAX_COMPLETION_TOKENS = 1024
_DEFAULT_VERIFY_MAX_COMPLETION_TOKEN_ATTEMPTS: tuple[int, ...] = (64, 512)
_DEFAULT_TEMPERATURE = 0.0


def _normalize_optional_positive_int(value: Any, default: int | None) -> int | None:
    try:
        if value is None:
            return default
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    if normalized <= 0:
        return default
    return normalized


def _normalize_verify_attempt_tokens(value: Any) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return _DEFAULT_VERIFY_MAX_COMPLETION_TOKEN_ATTEMPTS
    normalized: list[int] = []
    for token_limit in value:
        try:
            token_limit_value = int(token_limit)
        except (TypeError, ValueError):
            continue
        if token_limit_value > 0:
            normalized.append(token_limit_value)
    if not normalized:
        return _DEFAULT_VERIFY_MAX_COMPLETION_TOKEN_ATTEMPTS
    return tuple(normalized)


def _normalize_temperature(value: Any, default: float = _DEFAULT_TEMPERATURE) -> float:
    try:
        if value is None:
            return default
        normalized = float(value)
    except (TypeError, ValueError):
        return default
    if normalized < 0:
        return 0.0
    if normalized > 2:
        return 2.0
    return normalized


def _normalize_provider_name(provider: str | None) -> str:
    raw_provider = str(provider or DEFAULT_AI_SVC_PROVIDER).strip().lower()
    if not raw_provider:
        raw_provider = DEFAULT_AI_SVC_PROVIDER
    return _PROVIDER_ALIASES.get(raw_provider, raw_provider)


def resolve_ai_runtime_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize planner runtime settings used by planner and startup checks."""
    planner_cfg = config.get("planner", {}) if isinstance(config, dict) else {}
    model = str(planner_cfg.get("model", "gpt-5.2")).strip() or "gpt-5.2"
    provider = _normalize_provider_name(planner_cfg.get("provider"))
    timeout_seconds = int(planner_cfg.get("request_timeout_seconds", 30))
    api_key_env_var = str(
        planner_cfg.get("api_key_env_var", DEFAULT_AI_SVC_API_KEY_ENV)
    ).strip() or DEFAULT_AI_SVC_API_KEY_ENV
    base_url = (
        str(planner_cfg.get("base_url", DEFAULT_AI_SVC_BASE_URL)).strip()
        or DEFAULT_AI_SVC_BASE_URL
    )
    max_completion_tokens = _normalize_optional_positive_int(
        planner_cfg.get("max_completion_tokens"),
        _DEFAULT_MAX_COMPLETION_TOKENS,
    )
    verify_max_completion_tokens_attempts = _normalize_verify_attempt_tokens(
        planner_cfg.get("verify_max_completion_tokens_attempts")
    )
    temperature = _normalize_temperature(planner_cfg.get("temperature"))
    prompts_cfg = planner_cfg.get("prompts", {}) if isinstance(planner_cfg, dict) else {}
    system_prompt = str(prompts_cfg.get("system_prompt", "")).strip()
    verification_prompt = str(prompts_cfg.get("verification_prompt", "")).strip()
    return {
        "llm_enabled": bool(planner_cfg.get("llm_enabled", True)),
        "provider": provider,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "temperature": temperature,
        "api_key_env_var": api_key_env_var,
        "base_url": base_url,
        "max_completion_tokens": max_completion_tokens,
        "verify_max_completion_tokens_attempts": verify_max_completion_tokens_attempts,
        "system_prompt": system_prompt,
        "verification_prompt": verification_prompt,
        "prompts_config_path": str(planner_cfg.get("prompts_config_path", "")).strip(),
        "api_key_present": bool(os.getenv(api_key_env_var)),
    }


def create_ai_connection(
    *,
    provider: str,
    api_key_env_var: str,
    base_url: str,
    timeout_seconds: int,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_completion_tokens: int | None = _DEFAULT_MAX_COMPLETION_TOKENS,
    verify_max_completion_tokens_attempts: tuple[int, ...] | None = (
        _DEFAULT_VERIFY_MAX_COMPLETION_TOKEN_ATTEMPTS
    ),
    verification_prompt: str = "",
) -> AIConnection:
    """Create the configured AI connection provider instance."""
    normalized_provider = _normalize_provider_name(provider)
    if normalized_provider == "openai":
        return OpenAICompatibleConnection(
            provider=normalized_provider,
            api_key_env_var=api_key_env_var,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            verify_max_completion_tokens_attempts=verify_max_completion_tokens_attempts,
            verification_prompt=verification_prompt,
        )
    if normalized_provider == "template":
        return TemplateAIConnection(
            provider=normalized_provider,
            api_key_env_var=api_key_env_var,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            verify_max_completion_tokens_attempts=verify_max_completion_tokens_attempts,
            verification_prompt=verification_prompt,
        )
    supported_values = sorted(_PROVIDER_ALIASES.keys())
    raise ValueError(
        f"unsupported AI provider '{provider}'. "
        f"Supported values: {', '.join(supported_values)}"
    )
