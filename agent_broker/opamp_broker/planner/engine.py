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

"""Compatibility facade for planner modules.

Classes are split into dedicated files:
- ``RuleFirstPlanner`` -> ``rule_first_planner.py``
- ``AISvcPlanner`` -> ``ai_svc_planner.py``
"""

from __future__ import annotations

from opamp_broker.planner.ai_svc_planner import AISvcPlanner, sanitize_plan
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
from opamp_broker.planner.factory import create_planner
from opamp_broker.planner.rule_first_planner import RuleFirstPlanner
from opamp_broker.planner.types import Planner

# Backward-compat alias for existing tests/importers.
_sanitize_plan = sanitize_plan

__all__ = [
    "AISvcPlanner",
    "BROKER_PLAN_JSON_SCHEMA",
    "DEFAULT_AI_SVC_API_KEY_ENV",
    "DEFAULT_AI_SVC_BASE_URL",
    "DEFAULT_AI_SVC_PROVIDER",
    "Planner",
    "REQUIRES_CONFIRMATION_KEY",
    "RESPONSE_TEXT_KEY",
    "RuleFirstPlanner",
    "TOOL_ARGS_KEY",
    "TOOL_NAME_KEY",
    "_sanitize_plan",
    "create_planner",
]
