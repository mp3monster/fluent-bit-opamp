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

NULLCOMMAND_CAPABILITY = "org.mp3monster.opamp_provider.nullcommand"  # Capability FQDN routed to the null-command handler.
NULLCOMMAND_TYPE = "Null Command"  # CustomMessage.type value for null-command payloads.
NULLCOMMAND_CLASSIFIER = "custom"  # Command classifier for provider routing.
NULLCOMMAND_ACTION = "nullcommand"  # Action name used for queueing and dispatch.


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class CommandNullCommand(CommandObjectInterface, CommandParameterSchemaInterface):
    """Concrete custom command object for nullcommand operations.

    Purpose: provide a no-op style custom command used for integration testing
    of custom command plumbing.

    Attributes:
        _command_time: UTC timestamp captured when the command object is created.
        _key_values: Mutable command payload dictionary used for CustomMessage output.
    """

    def __init__(
        self,
        *,
        command_time: datetime | None = None,
        key_values: dict[str, str] | None = None,
    ) -> None:
        """Initialize null-command metadata and payload values.

        Args:
            command_time: Optional explicit timestamp used in tests.
            key_values: Optional payload values merged over required defaults.
        """
        self._command_time = command_time or _utc_now()
        merged = self._default_key_values()
        if key_values:
            merged.update(key_values)
        self._key_values = merged

    def _default_key_values(self) -> dict[str, str]:
        """Return default classifier/action values for null-command routing."""
        return {
            "classifier": NULLCOMMAND_CLASSIFIER,
            "action": NULLCOMMAND_ACTION,
        }

    def get_command_classifier(self) -> str:
        """Return command classifier used for routing.

        Implements:
            CommandObjectInterface.get_command_classifier.
        """
        return NULLCOMMAND_CLASSIFIER

    def get_command_time(self) -> datetime:
        """Return command creation timestamp.

        Implements:
            CommandObjectInterface.get_command_time.
        """
        return self._command_time

    def get_command_description(self) -> str:
        """Return event/queue description text.

        Implements:
            CommandObjectInterface.get_command_description.
        """
        return "custom nullcommand queued"

    def getdisplayname(self) -> str:
        """Return display label used in UI/API metadata.

        Implements:
            CommandObjectInterface.getdisplayname.
        """
        return "Null Command"

    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        """Replace payload values while preserving command defaults.

        Implements:
            CommandObjectInterface.set_key_value_dictionary.

        Args:
            key_values: User/operator-provided payload values.
        """
        merged = self._default_key_values()
        merged.update(key_values)
        self._key_values = merged

    def get_key_value_dictionary(self) -> dict[str, str]:
        """Return a copy of current payload values.

        Implements:
            CommandObjectInterface.get_key_value_dictionary.
        """
        return dict(self._key_values)

    def get_capability_fqdn(self) -> str | None:
        """Return reverse-FQDN used by outbound custom messages.

        Implements:
            CommandObjectInterface.get_capability_fqdn.
        """
        return NULLCOMMAND_CAPABILITY

    def isOpAMPStandard(self) -> bool:
        """Return whether this command is OpAMP-standard (it is not).

        Implements:
            CommandObjectInterface.isOpAMPStandard.
        """
        return False

    def get_user_parameter_schema(self) -> list[dict[str, str | bool]]:
        """Return user-editable parameter schema rows.

        Implements:
            CommandParameterSchemaInterface.get_user_parameter_schema.
        """
        return []

    def to_custom_message(self) -> opamp_pb2.CustomMessage:
        """Build a CustomMessage payload for nullcommand dispatch."""
        payload = opamp_pb2.CustomMessage()
        payload.capability = NULLCOMMAND_CAPABILITY
        payload.type = NULLCOMMAND_TYPE
        payload.data = json.dumps(self._key_values, sort_keys=True).encode("utf-8")
        return payload
