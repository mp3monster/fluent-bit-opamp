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

"""Provider-agnostic AI connection protocol used by planner components."""

from __future__ import annotations

from typing import Any, Protocol


class AIConnection(Protocol):
    """Protocol for AI provider transport/auth operations."""

    provider: str
    api_key_env_var: str
    base_url: str
    timeout_seconds: int

    def has_api_key(self) -> bool:
        """Return whether required API key material is currently available."""

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
        """Return model output text constrained by the supplied JSON schema."""

    async def verify_connection(self, *, model: str) -> dict[str, Any]:
        """Return provider connectivity/auth status for startup verification."""
