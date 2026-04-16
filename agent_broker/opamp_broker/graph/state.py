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

"""Shared typed state keys and schema for the broker conversation graph.

State is intentionally dictionary-based for LangGraph compatibility, with string
constants to prevent typos and improve cross-node refactor safety.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

STATE_KEY_TEAM_ID: Final[str] = "team_id"
STATE_KEY_CHANNEL_ID: Final[str] = "channel_id"
STATE_KEY_THREAD_TS: Final[str] = "thread_ts"
STATE_KEY_USER_ID: Final[str] = "user_id"
STATE_KEY_TEXT: Final[str] = "text"
STATE_KEY_NORMALIZED_TEXT: Final[str] = "normalized_text"
STATE_KEY_COMMAND: Final[str] = "command"
STATE_KEY_TARGET: Final[str] = "target"
STATE_KEY_ENVIRONMENT: Final[str] = "environment"
STATE_KEY_INTENT: Final[str] = "intent"
STATE_KEY_RESPONSE_TEXT: Final[str] = "response_text"
STATE_KEY_REQUIRES_CONFIRMATION: Final[str] = "requires_confirmation"
STATE_KEY_TOOL_NAME: Final[str] = "tool_name"
STATE_KEY_TOOL_ARGS: Final[str] = "tool_args"
STATE_KEY_TOOL_RESULT: Final[str] = "tool_result"
STATE_KEY_TOOLS_AVAILABLE: Final[str] = "tools_available"


class BrokerState(TypedDict, total=False):
    """Typed dictionary describing the graph state contract.

    Why this structure:
    ``total=False`` allows incremental enrichment as each node appends fields
    without requiring every stage to populate the full schema.
    """
    team_id: str
    channel_id: str
    thread_ts: str
    user_id: str
    text: str
    normalized_text: str
    command: str
    target: str | None
    environment: str | None
    intent: str
    response_text: str
    requires_confirmation: bool
    tool_name: str | None
    tool_args: dict[str, Any]
    tool_result: dict[str, Any]
    tools_available: list[str]
