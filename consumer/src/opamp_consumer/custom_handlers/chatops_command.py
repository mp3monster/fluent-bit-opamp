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

"""Default custom handler implementation with logging stubs."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx

from opamp_consumer.custom_handlers.handler_interface import (
    CustomMessageHandlerInterface,
)
from opamp_consumer.proto import opamp_pb2

if TYPE_CHECKING:
    from opamp_consumer.client import OpAMPClientData
    from opamp_consumer.opamp_client_interface import OpAMPClientInterface

CHATOPCOMMAND_CAPABILITY = "org.mp3monster.opamp_provider.chatopcommand"
CONTENT_TYPE_HEADER = "Content-Type"
CONTENT_LENGTH_HEADER = "Content-Length"
CONTENT_TYPE_JSON = "application/json"
UTF8_ENCODING = "utf-8"


class ChatOpsCommand(CustomMessageHandlerInterface):
    """Stub ChatOps command handler."""

    def __init__(self) -> None:
        """Initialize runtime fields used to route and execute ChatOps requests."""
        super().__init__()
        self._data: OpAMPClientData | None = None
        self._payload_data: dict[str, object] = {}

    def set_client_data(self, data: OpAMPClientData) -> None:
        """Store client runtime/config data used while building local ChatOps calls.

        Args:
            data: Client runtime state and configuration.
        """
        logging.getLogger(__name__).info("ChatOpsCommand.set_client_data called")
        self._data = data

    def get_fqdn(self) -> str:
        """Return the capability FQDN this handler is responsible for processing."""
        logging.getLogger(__name__).info("ChatOpsCommand.get_fqdn called")
        return CHATOPCOMMAND_CAPABILITY

    def handle_message(self, message: str, message_type: str) -> None:
        """Parse and cache inbound payload data for later action execution.

        Args:
            message: Raw custom-message body string.
            message_type: Custom-message type value.
        """
        self._payload_data = {}
        if message:
            try:
                parsed = json.loads(message)
                if isinstance(parsed, dict):
                    self._payload_data = parsed
            except json.JSONDecodeError:
                self._payload_data = {}
        logging.getLogger(__name__).info(
            "ChatOpsCommand.handle_message called message_type=%s message=%s",
            message_type,
            message,
        )

    def _build_local_url(self) -> str:
        """Build the localhost ChatOps endpoint URL from config port and payload tag.

        Returns:
            Fully-qualified localhost URL for the ChatOps call.
        """
        port = 8888
        if self._data is not None and self._data.config is not None:
            configured_port = self._data.config.chat_ops_port or 8888
            port = int(configured_port)
        tag = str(self._payload_data.get("tag", "") or "").strip()
        if tag:
            return f"http://localhost:{port}/{tag.lstrip('/')}"
        return f"http://localhost:{port}"

    def _parse_attributes_payload(self) -> dict[str, object]:
        """Normalize attributes payload into a dict from object, JSON, or escaped JSON.

        Returns:
            Parsed attributes dictionary, or `{}` when parsing fails.
        """
        raw_attributes = self._payload_data.get("attributes")

        if raw_attributes is None:
            logging.getLogger(__name__).info(
                "ChatOpsCommand._parse_attributes_payload - no attributes set, returning default"
            )
            return {}
        if isinstance(raw_attributes, dict):
            logging.getLogger(__name__).debug(
                "ChatOpsCommand._parse_attributes_payload - identified object for %s",
                raw_attributes,
            )
            return raw_attributes
        if isinstance(raw_attributes, str):
            try:
                parsed = json.loads(raw_attributes)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                logging.getLogger(__name__).warning(
                    "ChatOpsCommand._parse_attributes_payload - failed to convert to JSON %s",
                    raw_attributes,
                )
                pass
            try:
                unescaped = bytes(raw_attributes, UTF8_ENCODING).decode("unicode_escape")
                parsed = json.loads(unescaped)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                logging.getLogger(__name__).warning(
                    "ChatOpsCommand._parse_attributes_payload - failed to convert as "
                    "unicode escaped to JSON %s",
                    raw_attributes,
                )
                return {}

        return {}

    def _build_failure_custom_message(
        self,
        *,
        http_code: int,
        response_text: str,
    ) -> opamp_pb2.CustomMessage:
        """Create a failure CustomMessage payload for non-success ChatOps responses.

        Args:
            http_code: HTTP status code from the ChatOps endpoint.
            response_text: Raw response body text from the ChatOps endpoint.

        Returns:
            CustomMessage with failure metadata encoded in `data`.
        """
        escaped_response = json.dumps(str(response_text))[1:-1]
        payload = opamp_pb2.CustomMessage()
        payload.capability = self.get_fqdn()
        payload.type = "failure"
        payload.data = json.dumps(
            {
                "http_code": str(http_code),
                "err_msg": escaped_response,
            },
            sort_keys=True,
        ).encode("utf-8")
        return payload

    def execute_action(
        self, action: str, opamp_client: OpAMPClientInterface
    ) -> opamp_pb2.CustomMessage | None:
        """Invoke local ChatOps endpoint and return failure payload for non-2xx status.

        Args:
            action: Action name associated with the custom command.
            opamp_client: Active OpAMP client instance invoking this handler.

        Returns:
            None for success, else a failure CustomMessage.
        """
        logger = logging.getLogger(__name__)
        logger.info(
            "ChatOpsCommand.execute_action called action=%s opamp_client=%s",
            action,
            opamp_client.__class__.__name__,
        )
        url = self._build_local_url()
        attributes = self._parse_attributes_payload()
        logger.debug(
            "ChatOpsCommand HTTP request url=%s attributes=%s",
            url,
            attributes,
        )
        payload_bytes = json.dumps(attributes, sort_keys=True).encode(UTF8_ENCODING)
        request_headers = {
            CONTENT_TYPE_HEADER: CONTENT_TYPE_JSON,
            CONTENT_LENGTH_HEADER: str(len(payload_bytes)),
        }
        response = httpx.post(
            url,
            content=payload_bytes,
            headers=request_headers,
            timeout=5.0,
        )
        logger.debug(
            "ChatOpsCommand HTTP response status=%s body_len=%s",
            response.status_code,
            len(str(response.text or "")),
        )

        if response.status_code < 200 or response.status_code > 299:
            return self._build_failure_custom_message(
                http_code=response.status_code,
                response_text=response.text,
            )
        return None
