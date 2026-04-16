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

"""Named graph topology constants used by the LangGraph conversation pipeline.

Keeping node and edge names in constants avoids drift between registration,
entrypoint wiring, and edge declarations when the workflow evolves.
"""

from __future__ import annotations

from typing import Final

NODE_NORMALIZE_INPUT: Final[str] = "normalize_input"
NODE_CLASSIFY_INTENT: Final[str] = "classify_intent"
NODE_PLAN_ACTION: Final[str] = "plan_action"
NODE_EXECUTE_OR_SUMMARIZE: Final[str] = "execute_or_summarize"

EDGE_NORMALIZE_TO_CLASSIFY: Final[tuple[str, str]] = (
    NODE_NORMALIZE_INPUT,
    NODE_CLASSIFY_INTENT,
)
EDGE_CLASSIFY_TO_PLAN: Final[tuple[str, str]] = (
    NODE_CLASSIFY_INTENT,
    NODE_PLAN_ACTION,
)
EDGE_PLAN_TO_EXECUTE: Final[tuple[str, str]] = (
    NODE_PLAN_ACTION,
    NODE_EXECUTE_OR_SUMMARIZE,
)
