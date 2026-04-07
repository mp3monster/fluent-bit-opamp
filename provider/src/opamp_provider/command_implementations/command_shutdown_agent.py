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

SHUTDOWN_AGENT_CAPABILITY = "org.mp3monster.opamp_provider.command_shutdown_agent"  # Capability FQDN routed to shutdown handler.
SHUTDOWN_AGENT_TYPE = "Shutdown Agent"  # CustomMessage.type value for shutdown requests.
SHUTDOWN_AGENT_CLASSIFIER = "custom"  # Command classifier for provider routing.
SHUTDOWN_AGENT_ACTION = "shutdownagent"  # Action name used for queueing and dispatch.


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class CommandShutdownAgent(CommandObjectInterface, CommandParameterSchemaInterface):
    """Concrete custom command object for shutdown-agent operations.

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
        """Initialize shutdown command metadata and payload values.

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
        """Return default classifier/action values for shutdown routing."""
        return {
            "classifier": SHUTDOWN_AGENT_CLASSIFIER,
            "action": SHUTDOWN_AGENT_ACTION,
        }

    def get_command_classifier(self) -> str:
        """Return command classifier used for routing.

        Implements:
            CommandObjectInterface.get_command_classifier.
        """
        return SHUTDOWN_AGENT_CLASSIFIER

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
        return "Instruction for telling an agent to shutdown"

    def getdisplayname(self) -> str:
        """Return display label used in UI/API metadata.

        Implements:
            CommandObjectInterface.getdisplayname.
        """
        return "Shutdown Agent"

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
        return SHUTDOWN_AGENT_CAPABILITY

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
        """Build a CustomMessage payload for shutdown-agent dispatch."""
        payload = opamp_pb2.CustomMessage()
        payload.capability = SHUTDOWN_AGENT_CAPABILITY
        payload.type = SHUTDOWN_AGENT_TYPE
        payload.data = json.dumps(self._key_values, sort_keys=True).encode("utf-8")
        return payload
