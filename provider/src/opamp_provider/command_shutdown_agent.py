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

"""Shutdown-agent custom command object implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from opamp_provider.command_interface import (
    CommandObjectInterface,
    CommandParameterSchemaInterface,
)
from opamp_provider.proto import opamp_pb2

SHUTDOWN_AGENT_CAPABILITY = "org.mp3monster.opamp_provider.command_shutdown_agent"
SHUTDOWN_AGENT_TYPE = "Shutdown Agent"
SHUTDOWN_AGENT_CLASSIFIER = "custom"
SHUTDOWN_AGENT_ACTION = "shutdownagent"


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class CommandShutdownAgent(CommandObjectInterface, CommandParameterSchemaInterface):
    """Concrete custom command object for shutdown-agent operations."""

    def __init__(
        self,
        *,
        command_time: datetime | None = None,
        key_values: dict[str, str] | None = None,
    ) -> None:
        self._command_time = command_time or _utc_now()
        merged = self._default_key_values()
        if key_values:
            merged.update(key_values)
        self._key_values = merged

    def _default_key_values(self) -> dict[str, str]:
        return {
            "classifier": SHUTDOWN_AGENT_CLASSIFIER,
            "action": SHUTDOWN_AGENT_ACTION,
        }

    def get_command_classifier(self) -> str:
        return SHUTDOWN_AGENT_CLASSIFIER

    def get_command_time(self) -> datetime:
        return self._command_time

    def get_command_description(self) -> str:
        return "custom shutdownagent queued"

    def getdisplayname(self) -> str:
        return "Shutdown Agent"

    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        merged = self._default_key_values()
        merged.update(key_values)
        self._key_values = merged

    def get_key_value_dictionary(self) -> dict[str, str]:
        return dict(self._key_values)

    def get_capability_fqdn(self) -> str | None:
        return SHUTDOWN_AGENT_CAPABILITY

    def isOpAMPStandard(self) -> bool:
        return False

    def get_user_parameter_schema(self) -> list[dict[str, str | bool]]:
        return []

    def to_custom_message(self) -> opamp_pb2.CustomMessage:
        """Build a CustomMessage payload for shutdown-agent dispatch."""
        payload = opamp_pb2.CustomMessage()
        payload.capability = SHUTDOWN_AGENT_CAPABILITY
        payload.type = SHUTDOWN_AGENT_TYPE
        payload.data = json.dumps(self._key_values, sort_keys=True).encode("utf-8")
        return payload
