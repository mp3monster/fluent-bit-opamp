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

"""Template AI connection scaffold for implementing new providers."""

from __future__ import annotations

from typing import Any


class TemplateAIConnection:
    """Non-runnable provider template for copy/paste implementation work."""

    def __init__(
        self,
        *,
        provider: str,
        api_key_env_var: str,
        base_url: str,
        timeout_seconds: int,
        temperature: float = 0.0,
        max_completion_tokens: int | None = 1024,
        verify_max_completion_tokens_attempts: tuple[int, ...] | None = None,
        verification_prompt: str = "",
    ) -> None:
        self.provider = provider
        self.api_key_env_var = api_key_env_var
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.verify_max_completion_tokens_attempts = (
            tuple(verify_max_completion_tokens_attempts)
            if verify_max_completion_tokens_attempts
            else ()
        )
        self.verification_prompt = verification_prompt

    def has_api_key(self) -> bool:
        """Always false so planner factory falls back safely in template mode."""
        return False

    async def request_json_schema_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> str:
        """Raise explicit guidance because this template is intentionally inert."""
        raise NotImplementedError(
            "template provider is a scaffold only. "
            "Implement request_json_schema_completion for your target AI API."
        )

    async def verify_connection(self, *, model: str) -> dict[str, Any]:
        """Return a clear non-ok status with guidance for implementers."""
        return {
            "ok": False,
            "error": (
                "template provider is not implemented. "
                "Copy template_ai_connection.py and implement provider-specific "
                "request/verification logic."
            ),
            "provider": self.provider,
            "model": model,
            "base_url": self.base_url,
        }
