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

"""Custom handler for provider shutdown-agent command messages."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import TYPE_CHECKING

from opamp_consumer.custom_handlers.handler_interface import (
    CustomMessageHandlerInterface,
)
from opamp_consumer.proto import opamp_pb2

if TYPE_CHECKING:
    from opamp_consumer.abstract_client import OpAMPClientData
    from opamp_consumer.opamp_client_interface import OpAMPClientInterface

SHUTDOWNCOMMAND_CAPABILITY = (
    "org.mp3monster.opamp_provider.command_shutdown_agent"
)  # Capability routed to shutdown handler.


class ShutdownCommand(CustomMessageHandlerInterface):
    """Handle shutdown-agent custom command messages from the provider."""

    def __init__(self) -> None:
        """Initialize runtime state used to execute shutdown custom commands."""
        super().__init__()
        self._data: OpAMPClientData | None = None
        self._last_message: str = ""
        self._last_message_type: str = ""

    def set_client_data(self, data: OpAMPClientData) -> None:
        """Attach client runtime data so command execution can update heartbeat flags.

        Args:
            data: Client runtime state and configuration.
        """
        self._data = data
        logging.getLogger(__name__).info("ShutdownCommand.set_client_data called")

    def get_fqdn(self) -> str:
        """Return the capability FQDN that routes messages to this handler."""
        return SHUTDOWNCOMMAND_CAPABILITY

    def handle_message(self, message: str, message_type: str) -> None:
        """Store incoming custom message payload details for diagnostics.

        Args:
            message: Raw custom-message body string.
            message_type: Custom-message type value.
        """
        self._last_message = message
        self._last_message_type = message_type
        logging.getLogger(__name__).info(
            "ShutdownCommand.handle_message called message_type=%s message=%s",
            message_type,
            message,
        )

    def execute_action(
        self, action: str, opamp_client: OpAMPClientInterface
    ) -> opamp_pb2.CustomMessage | None:
        """Send disconnect, stop the agent, and terminate process for shutdown action.

        Args:
            action: Requested action name from the incoming custom command.
            opamp_client: Active OpAMP client instance used to send disconnect.

        Returns:
            Always None. Raises when disconnect fails.
        """
        logger = logging.getLogger(__name__)
        logger.info(
            "ShutdownCommand.execute_action called action=%s opamp_client=%s",
            action or "shutdown",
            opamp_client.__class__.__name__,
        )
        if self._data is not None:
            self._data.allow_heartbeat = False
        else:
            logger.warning(
                "ShutdownCommand has no client data; proceeding with disconnect"
            )

        disconnect_error: list[Exception] = []

        def _send_disconnect() -> None:
            """Run async disconnect send in a helper thread and capture raised errors."""
            try:
                asyncio.run(opamp_client.send_disconnect())
            except Exception as err:  # pragma: no cover - depends on runtime transport
                disconnect_error.append(err)

        disconnect_thread = threading.Thread(target=_send_disconnect, daemon=True)
        disconnect_thread.start()
        disconnect_thread.join()

        if disconnect_error:
            raise disconnect_error[0]

        logger.info("ShutdownCommand sent disconnect; sleeping for 10 seconds")
        time.sleep(10)
        opamp_client.terminate_agent_process()
        logger.info("ShutdownCommand exiting process")
        os._exit(0)
