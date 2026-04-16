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

"""Shared planner constants and output schema."""

from __future__ import annotations

from typing import Any

TOOL_NAME_KEY = "tool_name"
TOOL_ARGS_KEY = "tool_args"
RESPONSE_TEXT_KEY = "response_text"
REQUIRES_CONFIRMATION_KEY = "requires_confirmation"

DEFAULT_AI_SVC_BASE_URL = "https://api.openai.com/v1"
DEFAULT_AI_SVC_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_AI_SVC_PROVIDER = "openai"

BROKER_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        RESPONSE_TEXT_KEY: {"type": "string"},
        TOOL_NAME_KEY: {"type": ["string", "null"]},
        TOOL_ARGS_KEY: {
            # OpenAI strict json_schema validation rejects dynamic object maps in this
            # position (400 invalid_request_error against response_format). We encode
            # tool args as JSON text, then parse back to dict in sanitize_plan.
            "type": "string",
            "description": (
                "JSON object encoded as a string representing tool arguments. "
                "Use '{}' when no args are required."
            ),
        },
        REQUIRES_CONFIRMATION_KEY: {"type": "boolean"},
    },
    "required": [
        RESPONSE_TEXT_KEY,
        TOOL_NAME_KEY,
        TOOL_ARGS_KEY,
        REQUIRES_CONFIRMATION_KEY,
    ],
}
