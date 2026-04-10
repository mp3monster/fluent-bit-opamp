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

"""Interface for custom OpAMP message handling."""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from opamp_consumer.exceptions import CommandException
from opamp_consumer.proto import opamp_pb2

if TYPE_CHECKING:
    from opamp_consumer.abstract_client import OpAMPClientData
    from opamp_consumer.opamp_client_interface import OpAMPClientInterface

UTF8_ENCODING = "utf-8"  # Text encoding used to decode custom-message payload bytes.
DECODE_ERRORS_REPLACE = "replace"  # Decode error strategy for malformed payload bytes.
PAYLOAD_ACTION_KEY = "action"  # JSON payload key used to select handler action.
CLIENT_SEND_METHOD_NAME = "send"  # Client method name used to send custom responses upstream.


class CommandHandlerInterface(ABC):
    """Defines the command handler contract for custom messages."""

    @abstractmethod
    def set_client_data(self, data: OpAMPClientData) -> None:
        """Provide the handler with OpAMP client data."""

    @abstractmethod
    def get_reverse_fqdn(self) -> str:
        """Return the reverse-FQDN for this command handler."""

    @abstractmethod
    def set_custom_message_handler(self, custom_message: opamp_pb2.CustomMessage) -> None:
        """Set the custom message payload to be processed by execute()."""

    @abstractmethod
    def execute(self, opamp_client: OpAMPClientInterface) -> CommandException | None:
        """Execute command logic and return a CommandException when execution fails."""


class CustomMessageHandlerInterface(CommandHandlerInterface):
    """Defines the contract for custom message handlers."""

    def __init__(self) -> None:
        """Initialize storage for the latest custom message payload."""
        self._custom_message: opamp_pb2.CustomMessage | None = None

    @abstractmethod
    def get_fqdn(self) -> str:
        """Return the fully-qualified domain name for this handler."""

    @abstractmethod
    def handle_message(self, message: str, message_type: str) -> None:
        """Handle an inbound message and type string."""

    @abstractmethod
    def execute_action(
        self, action: str, opamp_client: OpAMPClientInterface
    ) -> opamp_pb2.CustomMessage | None:
        """Execute a named action and optionally return a CustomMessage response."""

    def get_reverse_fqdn(self) -> str:
        """Return the reverse-FQDN used for capability lookup."""
        return self.get_fqdn()

    def set_custom_message_handler(self, custom_message: opamp_pb2.CustomMessage) -> None:
        """Store the inbound custom message for execute()."""
        self._custom_message = custom_message

    def execute(self, opamp_client: OpAMPClientInterface) -> CommandException | None:
        """Execute the custom message handler and return CommandException on failure."""
        logger = logging.getLogger(__name__)
        fqdn = self.get_reverse_fqdn()
        logger.info("custom handler execute start fqdn=%s", fqdn)
        try:
            if self._custom_message is None:
                return CommandException("No custom message set on command handler")

            message_type = str(self._custom_message.type or "")
            payload_text = bytes(self._custom_message.data or b"").decode(
                UTF8_ENCODING,
                errors=DECODE_ERRORS_REPLACE,
            )
            action = ""
            if payload_text:
                try:
                    payload_data = json.loads(payload_text)
                    if isinstance(payload_data, dict):
                        action = str(payload_data.get(PAYLOAD_ACTION_KEY, "") or "")
                except json.JSONDecodeError:
                    action = ""

            self.handle_message(payload_text, message_type)
            custom_response = self.execute_action(action, opamp_client)
            if custom_response is not None:
                sender = getattr(opamp_client, CLIENT_SEND_METHOD_NAME, None)
                if not callable(sender):
                    return CommandException(
                        "Custom response could not be sent: client send method unavailable"
                    )
                outbound = opamp_pb2.AgentToServer()
                outbound.custom_message.CopyFrom(custom_response)
                try:
                    asyncio.run(sender(msg=outbound, send_as_is=True))
                except TypeError:
                    return CommandException(
                        "Custom response could not be sent: client send signature mismatch"
                    )
        except Exception as err:  # pragma: no cover - depends on implementation details
            return CommandException(f"Command handler execute failed: {err}")
        finally:
            logger.info("custom handler execute end fqdn=%s", fqdn)
        return None
