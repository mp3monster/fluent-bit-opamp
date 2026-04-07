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

from opamp_provider.command_interface import (
    CommandObjectInterface,
    CommandParameterSchemaInterface,
)
from opamp_provider.proto import opamp_pb2

CHATOPCOMMAND_CAPABILITY = "org.mp3monster.opamp_provider.chatopcommand"  # Capability FQDN routed to ChatOps handlers on the client.
CHATOPCOMMAND_TYPE = "request"  # CustomMessage.type value for chatops requests.
COMMAND_CLASSIFIER = "custom"  # Command classifier for provider routing.
COMMAND_DESCRIPTION = "Uses the chat ops strategy to provide a dynamic means to get the agent to perform a task based on its existing configuration."  # Event/queue description text.
COMMAND_DISPLAY_NAME = "ChatOps Command"  # Display name presented in UI metadata.
COMMAND_ACTION = "chatopcommand"  # Action name used for command dispatch and filtering.
PARAMETER_ACTION_NAME = "tag"  # User parameter name that selects ChatOps operation.
PARAMETER_ACTION_TYPE = "string"  # User parameter datatype metadata.
PARAMETER_ACTION_DESCRIPTION = "Custom command operation name."  # User parameter help text.
ENCODING_UTF8 = "utf-8"  # Text encoding used for serialized custom payload bytes.


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class ChatOpCommand(CommandObjectInterface, CommandParameterSchemaInterface):
    """Concrete custom command object for chatopcommand operations.

    Attributes:
        _command_time: UTC timestamp captured when the command object is created.
        _key_values: Mutable command payload dictionary used to build wire messages.
    """

    def __init__(
        self,
        *,
        command_time: datetime | None = None,
        key_values: dict[str, str] | None = None,
    ) -> None:
        """Initialize the command object and normalized key/value payload.

        Args:
            command_time: Optional explicit timestamp used for deterministic tests.
            key_values: Optional payload values merged on top of command defaults.
        """
        self._command_time = command_time or _utc_now()
        merged = self._default_key_values()
        if key_values:
            merged.update(key_values)
        self._key_values = merged

    def _default_key_values(self) -> dict[str, str]:
        """Return default routing keys required by provider command dispatch."""
        return {
            "classifier": COMMAND_CLASSIFIER,
            "action": COMMAND_ACTION,
        }

    def get_command_classifier(self) -> str:
        """Return classifier string for routing.

        Implements:
            CommandObjectInterface.get_command_classifier.
        """
        return COMMAND_CLASSIFIER

    def get_command_time(self) -> datetime:
        """Return command creation timestamp.

        Implements:
            CommandObjectInterface.get_command_time.
        """
        return self._command_time

    def get_command_description(self) -> str:
        """Return a human-readable queue/event description.

        Implements:
            CommandObjectInterface.get_command_description.
        """
        return COMMAND_DESCRIPTION

    def getdisplayname(self) -> str:
        """Return UI-friendly display name.

        Implements:
            CommandObjectInterface.getdisplayname.
        """
        return COMMAND_DISPLAY_NAME

    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        """Replace payload values while preserving required defaults.

        Implements:
            CommandObjectInterface.set_key_value_dictionary.

        Args:
            key_values: User/operator-provided values to merge into payload.
        """
        merged = self._default_key_values()
        merged.update(key_values)
        self._key_values = merged

    def get_key_value_dictionary(self) -> dict[str, str]:
        """Return a copy of current payload key/value pairs.

        Implements:
            CommandObjectInterface.get_key_value_dictionary.
        """
        return dict(self._key_values)

    def get_capability_fqdn(self) -> str | None:
        """Return reverse-FQDN used in `CustomMessage.capability`.

        Implements:
            CommandObjectInterface.get_capability_fqdn.
        """
        return CHATOPCOMMAND_CAPABILITY

    def isOpAMPStandard(self) -> bool:
        """Return whether this command is OpAMP-standard (it is not).

        Implements:
            CommandObjectInterface.isOpAMPStandard.
        """
        return False

    def get_user_parameter_schema(self) -> list[dict[str, str | bool]]:
        """Return user-editable parameter schema rows for UI/API consumers.

        Implements:
            CommandParameterSchemaInterface.get_user_parameter_schema.
        """
        return [
            {
                "parametername": PARAMETER_ACTION_NAME,
                "type": PARAMETER_ACTION_TYPE,
                "description": PARAMETER_ACTION_DESCRIPTION,
                "isrequired": True,
            },
        ]

    def to_custom_message(self) -> opamp_pb2.CustomMessage:
        """Build a CustomMessage payload for ChatOp command dispatch."""
        payload = opamp_pb2.CustomMessage()
        payload.capability = CHATOPCOMMAND_CAPABILITY
        payload.type = CHATOPCOMMAND_TYPE
        payload.data = json.dumps(self._key_values, sort_keys=True).encode(
            ENCODING_UTF8
        )
        return payload
