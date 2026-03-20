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

"""Null-command custom command object implementation.

This command is intentionally minimal and exists to test custom command
discovery, UI rendering, queueing, and payload handling end-to-end.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from opamp_provider.command_interface import (
    CommandObjectInterface,
    CommandParameterSchemaInterface,
)
from opamp_provider.proto import opamp_pb2

NULLCOMMAND_CAPABILITY = "org.mp3monster.opamp_provider.nullcommand"
NULLCOMMAND_TYPE = "Null Command"


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class CommandNullCommand(CommandObjectInterface, CommandParameterSchemaInterface):
    """Concrete custom command object for nullcommand operations.

    Purpose: provide a no-op style custom command used for integration testing
    of custom command plumbing.
    """

    def __init__(
        self,
        *,
        command_time: datetime | None = None,
        key_values: dict[str, str] | None = None,
    ) -> None:
        self._command_time = command_time or _utc_now()
        self._key_values = key_values or {}

    def get_command_classifier(self) -> str:
        return "custom"

    def get_command_type(self) -> str:
        return "nullcommand"

    def get_command_time(self) -> datetime:
        return self._command_time

    def get_command_description(self) -> str:
        return "custom nullcommand queued"

    def getdisplayname(self) -> str:
        return "Null Command"

    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        self._key_values = dict(key_values)

    def get_key_value_dictionary(self) -> dict[str, str]:
        return dict(self._key_values)

    def get_capability_fqdn(self) -> str | None:
        return NULLCOMMAND_CAPABILITY

    def isOpAMPStandard(self) -> bool:
        return False

    def get_user_parameter_schema(self) -> list[dict[str, str | bool]]:
        return []

    def to_custom_message(self) -> opamp_pb2.CustomMessage:
        """Build a CustomMessage payload for nullcommand dispatch."""
        payload = opamp_pb2.CustomMessage()
        payload.capability = NULLCOMMAND_CAPABILITY
        payload.type = NULLCOMMAND_TYPE
        payload.data = json.dumps(self._key_values, sort_keys=True).encode("utf-8")
        return payload
