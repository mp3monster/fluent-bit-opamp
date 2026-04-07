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

"""Restart command object implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from opamp_provider.command_interface import (
    CommandObjectInterface,
    CommandParameterSchemaInterface,
)


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class RestartAgent(CommandObjectInterface, CommandParameterSchemaInterface):
    """Concrete command object for a restart operation.

    Attributes:
        _command_time: UTC timestamp captured when the command object is created.
        _key_values: Mutable command payload dictionary used by queueing/dispatch.
    """

    def __init__(
        self,
        *,
        command_time: datetime | None = None,
        key_values: dict[str, str] | None = None,
    ) -> None:
        """Initialize the restart command metadata and payload dictionary.

        Args:
            command_time: Optional explicit timestamp used in deterministic tests.
            key_values: Optional payload values merged over command defaults.
        """
        self._command_time = command_time or _utc_now()
        merged = self._default_key_values()
        if key_values:
            merged.update(key_values)
        self._key_values = merged

    def _default_key_values(self) -> dict[str, str]:
        """Return default classifier/action routing values for restart."""
        return {
            "classifier": "command",
            "action": "restart",
        }

    def get_command_classifier(self) -> str:
        """Return provider classifier used for restart routing.

        Implements:
            CommandObjectInterface.get_command_classifier.
        """
        return "command"

    def get_command_time(self) -> datetime:
        """Return command creation timestamp.

        Implements:
            CommandObjectInterface.get_command_time.
        """
        return self._command_time

    def get_command_description(self) -> str:
        """Return human-readable command description.

        Implements:
            CommandObjectInterface.get_command_description.
        """
        return "Restarts Agent"

    def getdisplayname(self) -> str:
        """Return display label used in UI/API metadata.

        Implements:
            CommandObjectInterface.getdisplayname.
        """
        return "Restart Agent"

    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        """Replace payload values while preserving default routing keys.

        Implements:
            CommandObjectInterface.set_key_value_dictionary.

        Args:
            key_values: User/operator-provided command values.
        """
        merged = self._default_key_values()
        merged.update(key_values)
        self._key_values = merged

    def get_key_value_dictionary(self) -> dict[str, str]:
        """Return a copy of command payload values.

        Implements:
            CommandObjectInterface.get_key_value_dictionary.
        """
        return dict(self._key_values)

    def get_capability_fqdn(self) -> str | None:
        """Return capability mapping for custom messages (none for restart).

        Implements:
            CommandObjectInterface.get_capability_fqdn.
        """
        # This uses the shared command framework for a default OpAMP feature (restart),
        # so it should not appear in the list of available custom commands.
        return None

    def isOpAMPStandard(self) -> bool:
        """Return whether this command is OpAMP-standard (it is).

        Implements:
            CommandObjectInterface.isOpAMPStandard.
        """
        return True

    def get_user_parameter_schema(self) -> list[dict[str, str | bool]]:
        """Return user-editable parameter schema rows.

        Implements:
            CommandParameterSchemaInterface.get_user_parameter_schema.
        """
        return [
            {
                "parametername": "action",
                "type": "string",
                "description": "Command action to execute.",
                "isrequired": True,
            },
        ]
