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

"""ChatOp command object implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from opamp_provider.command_interface import CommandObjectInterface
from opamp_provider.proto import opamp_pb2

CHATOPCOMMAND_CAPABILITY = "org.mp3monster.opamp_provider.chatopcommand"
CHATOPCOMMAND_TYPE = "by REST Call"


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class ChatOpCommand(CommandObjectInterface):
    """Concrete custom command object for chatopcommand operations."""

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
        return "chatopcommand"

    def get_command_time(self) -> datetime:
        return self._command_time

    def get_command_description(self) -> str:
        return "custom chatopcommand queued"

    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        self._key_values = dict(key_values)

    def get_key_value_dictionary(self) -> dict[str, str]:
        return dict(self._key_values)

    def get_capability_fqdn(self) -> str:
        return CHATOPCOMMAND_CAPABILITY

    def to_custom_message(self) -> opamp_pb2.CustomMessage:
        """Build a CustomMessage payload for ChatOp command dispatch."""
        payload = opamp_pb2.CustomMessage()
        payload.capability = CHATOPCOMMAND_CAPABILITY
        payload.type = CHATOPCOMMAND_TYPE
        payload.data = json.dumps(self._key_values, sort_keys=True).encode("utf-8")
        return payload
