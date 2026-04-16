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

"""AI service-backed planner implementation."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from opamp_broker.planner.ai_connection import AIConnection
from opamp_broker.planner.ai_connection_factory import create_ai_connection
from opamp_broker.planner.constants import (
    BROKER_PLAN_JSON_SCHEMA,
    DEFAULT_AI_SVC_API_KEY_ENV,
    DEFAULT_AI_SVC_BASE_URL,
    DEFAULT_AI_SVC_PROVIDER,
    REQUIRES_CONFIRMATION_KEY,
    RESPONSE_TEXT_KEY,
    TOOL_ARGS_KEY,
    TOOL_NAME_KEY,
)

logger = logging.getLogger(__name__)


class AISvcPlanner:
    """LLM planner that returns a strict JSON plan constrained to discovered tools."""

    def __init__(
        self,
        *,
        model: str,
        connection: AIConnection,
        system_prompt: str,
        temperature: float,
    ) -> None:
        self.model = model
        self.connection = connection
        self.system_prompt = system_prompt
        self.temperature = temperature

    async def plan(self, *, text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Create a tool-constrained plan using an AI service JSON schema response."""
        allowed_tools = [
            {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "inputSchema": tool.get("inputSchema", {}),
            }
            for tool in tools
            if tool.get("name")
        ]

        system_prompt = str(self.system_prompt).strip()
        if not system_prompt:
            raise RuntimeError(
                "missing required non-empty system_prompt in planner prompts config"
            )

        user_prompt = {
            "request_text": text,
            "available_tools": allowed_tools,
            "output_requirements": {
                "must_use_only_listed_tool_names": True,
                "tool_args_must_match_selected_tool_schema": True,
            },
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
            "temperature": self.temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "broker_plan",
                    "schema": BROKER_PLAN_JSON_SCHEMA,
                    "strict": True,
                },
            },
        }

        logger.debug(
            "Sending planner request to AI service provider=%s model=%s base_url=%s tool_count=%d",
            self.connection.provider,
            self.model,
            self.connection.base_url,
            len(allowed_tools),
        )
        logger.debug("Planner request payload: %s", json.dumps(payload, ensure_ascii=False))

        raw_content = await self.connection.request_json_schema_completion(
            model=self.model,
            messages=payload["messages"],
            schema_name="broker_plan",
            schema=BROKER_PLAN_JSON_SCHEMA,
            temperature=self.temperature,
        )
        parsed = json.loads(raw_content)
        return sanitize_plan(parsed=parsed, tools=tools)


async def verify_ai_svc_connection(
    *,
    model: str,
    provider: str = DEFAULT_AI_SVC_PROVIDER,
    timeout_seconds: int = 30,
    temperature: float = 0.0,
    api_key_env_var: str = DEFAULT_AI_SVC_API_KEY_ENV,
    base_url: str = DEFAULT_AI_SVC_BASE_URL,
    max_completion_tokens: int | None = 1024,
    verify_max_completion_tokens_attempts: tuple[int, ...] | None = (64, 512),
    verification_prompt: str = "",
) -> dict[str, Any]:
    """Verify AI service reachability/authentication using a minimal API call."""
    try:
        connection = create_ai_connection(
            provider=provider,
            api_key_env_var=api_key_env_var,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            verify_max_completion_tokens_attempts=(
                verify_max_completion_tokens_attempts
            ),
            verification_prompt=verification_prompt,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"failed to create AI provider connection: {exc}",
        }
    return await connection.verify_connection(model=model)


def sanitize_plan(
    *,
    parsed: dict[str, Any],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Normalize and constrain planner output to discovered tool metadata."""
    allowed_names = {str(tool.get("name")) for tool in tools if tool.get("name")}

    raw_tool_name = parsed.get(TOOL_NAME_KEY)
    tool_name = str(raw_tool_name).strip() if raw_tool_name else None
    if tool_name not in allowed_names:
        tool_name = None

    # See planner/constants.py note: tool_args is emitted as a JSON string to stay
    # compatible with OpenAI strict response_format schema requirements.
    raw_tool_args = parsed.get(TOOL_ARGS_KEY, "{}")
    tool_args: dict[str, Any] = {}
    if isinstance(raw_tool_args, dict):
        tool_args = raw_tool_args
    elif isinstance(raw_tool_args, str):
        candidate = raw_tool_args.strip() or "{}"
        try:
            decoded = json.loads(candidate)
        except ValueError:
            # Keep planning resilient if the model emits non-JSON tool_args text.
            decoded = {}
        if isinstance(decoded, dict):
            tool_args = decoded
    if not tool_name:
        tool_args = {}

    response_text = parsed.get(RESPONSE_TEXT_KEY, "")
    if not isinstance(response_text, str):
        response_text = str(response_text)

    requires_confirmation = bool(parsed.get(REQUIRES_CONFIRMATION_KEY, False))

    if tool_name and re.search(r"restart|delete", response_text, re.IGNORECASE):
        requires_confirmation = True

    return {
        RESPONSE_TEXT_KEY: response_text.strip(),
        TOOL_NAME_KEY: tool_name,
        TOOL_ARGS_KEY: tool_args,
        REQUIRES_CONFIRMATION_KEY: requires_confirmation,
    }
