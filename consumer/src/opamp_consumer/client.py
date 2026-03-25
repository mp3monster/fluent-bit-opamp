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

"""OpAMP client skeleton for HTTP and WebSocket transports."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
import sys
import logging
import os
import pathlib
import platform
import re
import socket
import subprocess
import threading
import time
import tracemalloc
import asyncio
import uuid
import traceback


import httpx
import websockets
from google.protobuf import text_format

from opamp_consumer import config as consumer_config
from opamp_consumer.config import CFG_AGENT_CONFIG_PATH, ConsumerConfig
from opamp_consumer.custom_handlers import build_factory_lookup, create_handler
from opamp_consumer.exceptions import AgentException
from opamp_consumer.opamp_client_interface import OpAMPClientInterface
from opamp_consumer.proto import anyvalue_pb2, opamp_pb2
from opamp_consumer.transport import decode_message, encode_message
from shared.opamp_config import (
    AGENT_CAPABILITIES_MAP,
    AgentCapabilities,
    OPAMP_HTTP_PATH,
    OPAMP_TRANSPORT_HEADER_NONE,
    PB_FIELD_AGENT_IDENTIFICATION,
    PB_FIELD_COMMAND,
    PB_FIELD_CONNECTION_SETTINGS,
    PB_FIELD_CUSTOM_CAPABILITIES,
    PB_FIELD_CUSTOM_MESSAGE,
    PB_FIELD_ERROR_RESPONSE,
    PB_FIELD_INSTANCE_UID,
    PB_FIELD_PACKAGES_AVAILABLE,
    PB_FLAG_REPORT_FULL_STATE,
    PB_FIELD_REMOTE_CONFIG,
    PB_FIELD_RETRY_INFO,
    UTF8_ENCODING,
    parse_capabilities,
)
from shared.uuid_utils import generate_uuid7_bytes

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - Python <3.11 fallback

    class StrEnum(str, Enum):
        """Compatibility fallback for Python versions without enum.StrEnum."""


HTTP_TIMEOUT_SECONDS = 5.0  # Timeout for local HTTP calls.
TRANSPORT_HTTP = "http"
TRANSPORT_WEBSOCKET = "websocket"
HEARTBEAT_SKEW_SECONDS = 1  # Sleep interval is heartbeat_frequency minus this value.
LOCALHOST_BASE = "http://localhost"  # Base URL for local Fluent Bit endpoints.
CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
HEADER_CONTENT_TYPE = "Content-Type"  # HTTP header key for protobuf content type.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.
ERR_PREFIX = "error: "  # Prefix for error values stored in results.
ERR_STATUS = "error"  # Status marker for failed local heartbeat HTTP calls.
FLUENTBIT_CMD = "fluent-bit"  # Fluent Bit executable name.
FLUENTBIT_CONFIG_FLAG = "-c"  # Fluent Bit config flag.
KEY_FLUENTBIT_VERSION = "fluentbit_version"  # Result key for version response.
KEY_AGENT_DESCRIPTION = "agent_description"  # Comment key for agent description.
KEY_SERVICE_INSTANCE_ID_COMMENT = (
    "service_instance_id"  # Comment key for service instance ID.
)
KEY_HTTP_PORT = "http_port"  # Fluent Bit HTTP port config key.
KEY_HTTP_LISTEN = "http_listen"  # Fluent Bit HTTP listen config key.
KEY_HTTP_SERVER = "http_server"  # Fluent Bit HTTP server config key.
KEY_HTTP_SERVER_ON = "on"  # Expected value token when HTTP server is enabled.
KEY_FLUENT_BIT_VERSION = "fluent-bit.version"  # Fluent Bit version JSON field key.
KEY_FLUENT_BIT_EDITION = "fluent-bit.edition"  # Fluent Bit edition JSON field key.
KEY_SERVICE_NAME = "service.name"  # Agent description service name key.
KEY_SERVICE_NAMESPACE = "service.namespace"  # Agent description service namespace key.
KEY_SERVICE_INSTANCE_ID = "service.instance.id"  # Agent description instance id key.
KEY_SERVICE_TYPE = "service.type"  # Agent description service type key.
TOKEN_IP = "__IP__"
TOKEN_HOSTNAME = "__hostname__"
TOKEN_MAC_ADDR = "__mac-ad__"
KEY_SERVICE_VERSION = "service.version"  # Agent description version key.
KEY_HEALTH = "health"  # Heartbeat dictionary key for health endpoint results.
VALUE_HEARTBEAT_STATUS = "heartbeat"  # Health status value used in heartbeats.
VALUE_SUPERVISOR_NO_STATE = (
    "Supervisor has not state"  # Error message when no heartbeat data.
)
VALUE_AGENT_TYPE_FLUENT_BIT = "Fluent Bit"  # Display name for Fluent Bit agent type.
JSON_KEY_FLUENT_BIT = "fluent-bit"  # JSON key for Fluent Bit map payload.
JSON_KEY_FLUENTBIT = "fluentbit"  # Alternate JSON key for Fluent Bit map payload.
JSON_KEY_VERSION = "version"  # Generic JSON version key.
JSON_KEY_EDITION = "edition"  # Generic JSON edition key.
CAPABILITY_PREFIX_REQUEST = (
    "request:"  # Prefix used for custom request capability fqdn.
)
HOST_META_KEY_OS_TYPE = "os_type"  # Host metadata key for OS type.
HOST_META_KEY_OS_VERSION = "os_version"  # Host metadata key for OS version.
HOST_META_KEY_HOSTNAME = "hostname"  # Host metadata key for hostname.
# Keep a local alias for backward compatibility with existing imports/tests.
CAPABILITIES_MAP = AGENT_CAPABILITIES_MAP
LOG_INVALID_HTTP_PORT = "invalid http_port value: %s"  # Log format for bad ports.
LOG_HTTP_SERVER_DISABLED = (
    "http_server is not enabled: %s"  # Log format for disabled HTTP.
)
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.
CONFIG_DOCS_URL = (
    "https://github.com/mp3monster/fluent-opamp"  # Reference docs for consumer config.
)

_HEARTBEAT_PATHS = (  # Local endpoints polled per heartbeat.
    "/api/v1/uptime",
    "/api/v1/health",
    "/api/v2/metrics/prometheus",
)


def _config_parameters_payload(config: ConsumerConfig) -> dict[str, object]:
    """Build config parameters payload with documentation URL.

    Args:
        config: Consumer configuration instance to serialize.

    Returns:
        Dictionary of config fields plus `documentation_url`.
    """
    config_params: dict[str, object] = asdict(config)
    config_params["documentation_url"] = CONFIG_DOCS_URL
    return config_params


@dataclass
class OpAMPClientData:
    """Container for OpAMP client instance data."""

    class ReportingFlag(StrEnum):
        """Enumeration of provider-directed reporting controls."""

        REPORT_FULL_STATE = "reportFullState"
        REPORT_HEALTH = "reportHealth"
        REPORT_CAPABILITIES = "reportCapabilities"
        REPORT_CUSTOM_CAPABILITIES = "reportCustomCapabilities"

        @classmethod
        def set_all_reporting_flags(
            cls,
            reporting_flags: dict["OpAMPClientData.ReportingFlag", bool],
            value: bool = True,
        ) -> None:
            """Set all reporting-flag dictionary values to the provided boolean.

            Args:
                reporting_flags: Mapping keyed by ReportingFlag values.
                value: Boolean value assigned to all reporting flags.
            """
            for flag in cls:
                reporting_flags[flag] = value

    config: ConsumerConfig
    base_url: str
    uid_instance: bytes | None = field(default_factory=generate_uuid7_bytes)
    allow_heartbeat: bool = True
    msg_sequence_number: int = 0
    last_heartbeat_http_codes: dict[str, int] | None = None
    last_heartbeat_call: int = 0
    last_heartbeat_results: dict[str, str] | None = field(default_factory=dict)
    launched_at: int = 0
    agent_process: subprocess.Popen[bytes] | None = None
    process_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    logFLB = False
    agent_type_name: str = "Fluent Bit"
    agent_version: str = ""
    reporting_flags: dict[ReportingFlag, bool] = field(
        default_factory=lambda: {flag: True for flag in OpAMPClientData.ReportingFlag}
    )

    def set_all_reporting_flags(self, value: bool = True) -> None:
        """Set every reporting flag value to the provided boolean.

        Args:
            value: Boolean value assigned to all reporting flags.
        """
        self.ReportingFlag.set_all_reporting_flags(self.reporting_flags, value)

    def set_all_flags(self, value: bool = True) -> None:
        """Backward-compatible alias to set all reporting flags.

        Args:
            value: Boolean value assigned to all reporting flags.
        """
        self.set_all_reporting_flags(value)


class OpAMPClient(OpAMPClientInterface):
    """Minimal OpAMP client supporting HTTP and WebSocket transports."""

    def __init__(self, base_url: str, config: ConsumerConfig | None = None) -> None:
        """Create a client bound to a base URL."""
        if config is None:
            config = globals().get("CONFIG") or consumer_config.CONFIG
        if config is None:
            logging.getLogger(__name__).warning("No config supplied to OpAMPClient")
            raise ValueError("OpAMP client requires a consumer config")

        self.data = OpAMPClientData(
            config=config,
            base_url=base_url.rstrip("/"),
        )
        self._custom_handler_folder = (
            pathlib.Path(__file__).resolve().parent / "custom_handlers"
        )
        self._custom_handler_lookup = build_factory_lookup(
            self._custom_handler_folder,
            client_data=self.data,
            allow_custom_capabilities=bool(self.config.allow_custom_capabilities),
        )

    @property
    def config(self) -> ConsumerConfig:
        """Return the active consumer configuration bound to this client instance."""
        return self.data.config

    @config.setter
    def config(self, value: ConsumerConfig) -> None:
        """Replace the active consumer configuration used by this client instance.

        Args:
            value: Consumer configuration object to bind to this client.
        """
        self.data.config = value

    def get_config_parameters(self) -> dict[str, object]:
        """Return active configuration parameters with a documentation reference.

        Returns:
            Config parameter dictionary plus a `documentation_url` entry.
        """
        return _config_parameters_payload(self.config)

    def _get_config_value(self, key: str) -> str:
        """Fetch a config value by key and normalize missing values to an empty string.

        Args:
            key: Configuration attribute name to retrieve from `self.data.config`.

        Returns:
            The string value for the key, or `""` when missing/unset.
        """
        value: str = ""
        try:
            value = self.data.config[key]
            if value is None:
                logging.getLogger(__name__).error("Error handling request for %s", key)
                value = ""
            return value
        except KeyValue as val:
            logging.getLogger(__name__).error(
                "Error handling request for %s, error is %s",
                key,
                val,
            )
            return ""

    async def send_http(self, msg: opamp_pb2.AgentToServer) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via HTTP and return the response.

        Args:
            msg: Populated AgentToServer payload to send.

        Returns:
            Parsed ServerToAgent reply from the provider.
        """
        url = f"{self.data.base_url}{OPAMP_HTTP_PATH}"
        logging.getLogger(__name__).debug("Calling REST endpoint at %s", url)
        payload = msg.SerializeToString()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                content=payload,
                headers={HEADER_CONTENT_TYPE: CONTENT_TYPE_PROTO},
            )
            resp.raise_for_status()
            reply = opamp_pb2.ServerToAgent()
            reply.ParseFromString(resp.content)
            self._handle_server_to_agent(reply)
            return reply

    def _populate_agent_to_server_health(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.AgentToServer:
        """Populate health fields on AgentToServer using latest heartbeat poll state.

        Args:
            msg: Outbound AgentToServer message being assembled.

        Returns:
            The same message instance with health fields updated.
        """
        healthy = True
        if self.data.last_heartbeat_results:
            healthy = (
                self.data.last_heartbeat_http_codes is not None
                and self.data.last_heartbeat_http_codes[KEY_HEALTH]
            )
            last_error = ""
            for value in self.data.last_heartbeat_results.values():
                text = str(value)
                # logging.getLogger(__name__).debug(f"Evaluating for health>>{text}")
                if text.startswith(ERR_PREFIX):
                    healthy = False
                    last_error = text

                msg = self._health_from_metrics(msg, text)

            msg.health.status = VALUE_HEARTBEAT_STATUS
            if not healthy and last_error:
                msg.health.last_error = last_error
        else:
            healthy = False
            msg.health.last_error = VALUE_SUPERVISOR_NO_STATE

        msg.health.start_time_unix_nano = time.time_ns() - self.data.launched_at
        msg.health.status_time_unix_nano = time.time_ns()
        msg.health.healthy = int(healthy)
        logging.getLogger(__name__).debug("Health info sending is >%s<", msg.health)
        return msg

    def _health_from_metrics(self, msg, text) -> opamp_pb2.AgentToServer:
        """Parse Fluent Bit metrics text and update component health entries in-place.

        Args:
            msg: AgentToServer message whose health map is updated.
            text: Metrics response text to parse.

        Returns:
            The same message instance with component health updates applied.
        """
        lines = text.splitlines()
        METRIC_STR: str = 'errors_total{name="'
        for line in lines:
            line_idx = line.find(METRIC_STR)
            if line_idx >= 0:
                # fluentbit_output_errors_total{name="file.0"} 0
                name_start: int = line_idx + len(METRIC_STR)
                name_end: int = line.index('"', name_start)
                component_name: str = line[name_start:name_end]
                last_num_text = re.findall(r"\d+(?:\.\d+)?", line[name_end:])[-1]
                last_num = int(last_num_text)
                msg.health.component_health_map[component_name].CopyFrom(
                    opamp_pb2.ComponentHealth(
                        healthy=(last_num == 0),
                        status=f"error count={last_num_text}",
                    )
                )
                logging.getLogger(__name__).debug(
                    "Component metric %s",
                    msg.health.component_health_map[component_name],
                )
        return msg

    def _populate_agent_to_server(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.AgentToServer:
        """Fill outbound AgentToServer payload with description, caps, IDs, and health.

        Args:
            msg: Base AgentToServer message to populate.

        Returns:
            Populated AgentToServer message ready to send.
        """
        msg.agent_description.CopyFrom(self.get_agent_description())
        msg.capabilities = self.get_agent_capabilities()
        custom_capabilities = self.get_custom_capabilities_payload()
        if custom_capabilities.capabilities:
            msg.custom_capabilities.CopyFrom(custom_capabilities)
        msg.sequence_num = self.data.msg_sequence_number
        self.data.msg_sequence_number = self.data.msg_sequence_number + 1
        msg.instance_uid = self.data.uid_instance

        msg = self._populate_agent_to_server_health(msg)
        return msg

    def _handle_server_to_agent(self, reply: opamp_pb2.ServerToAgent) -> bool:
        """Process ServerToAgent fields and dispatch each populated payload section.

        Args:
            reply: ServerToAgent payload received from the provider.

        Returns:
            True when message processing completed without critical handling errors.
        """
        logger = logging.getLogger(__name__)
        logger.debug("_handle_server_to_agent called")
        successful_message = True

        logger.debug("Handling Server to agent payload:%s", reply)
        if reply is None:
            logger.error("Been given None response")
            return False

        try:
            if not self._validate_reply_instance_uid(reply):
                successful_message = False
        except ValueError as val_err:
            logger.error("Error processing svr instance uid %s", val_err)
            successful_message = False

        try:
            if reply.HasField(PB_FIELD_ERROR_RESPONSE):
                self.data.set_all_flags()
                self.handle_error_response(error_response=reply.error_response)
            if reply.HasField(PB_FIELD_REMOTE_CONFIG):
                self.handle_remote_config(reply.remote_config)
            if reply.HasField(PB_FIELD_CONNECTION_SETTINGS):
                self.handle_connection_settings(reply.connection_settings)
            if reply.HasField(PB_FIELD_PACKAGES_AVAILABLE):
                self.handle_packages_available(reply.packages_available)
            if reply.flags:
                self.handle_flags(reply.flags)
            if reply.capabilities:
                self.handle_capabilities(reply.capabilities)
            if reply.HasField(PB_FIELD_AGENT_IDENTIFICATION):
                self.handle_agent_identification(reply.agent_identification)
            if reply.HasField(PB_FIELD_COMMAND):
                self.handle_command(reply.command)
            if reply.HasField(PB_FIELD_CUSTOM_CAPABILITIES):
                self.handle_custom_capabilities(reply.custom_capabilities)
            if reply.HasField(PB_FIELD_CUSTOM_MESSAGE):
                self.handle_custom_message(reply.custom_message)

        except AgentException as agent_err:
            logger.error("Agent Error received - %s", agent_err)
            successful_message = False
        return successful_message

    def _validate_reply_instance_uid(self, reply: opamp_pb2.ServerToAgent) -> bool:
        """Validate that a reply contains and matches the expected instance UID.

        Args:
            reply: Incoming ServerToAgent payload.

        Returns:
            True if the payload instance UID is present and matches this client.
        """
        logger = logging.getLogger(__name__)
        if reply.HasField(PB_FIELD_INSTANCE_UID):
            logger.debug("reply target is %s", reply.instance_uid)
            if reply.instance_uid == self.data.uid_instance:
                return True
            logger.error(
                "Message doesn't have an instance uid or doesn't match our "
                "service instance id %s",
                self.data.uid_instance,
            )
            return False
        logger.error(
            "Server didn't share instance_uid, my instance uid is %s",
            self.data.uid_instance,
        )
        return False

    async def send(
        self,
        msg: opamp_pb2.AgentToServer | None = None,
        *,
        send_as_is: bool = False,
    ) -> opamp_pb2.ServerToAgent | None:
        """Implements `OpAMPClientInterface.send`.

        Send an AgentToServer message using the configured transport.

        Args:
            msg: Optional outbound payload. A new payload is built when omitted.
            send_as_is: When True, skip automatic payload population.

        Returns:
            ServerToAgent reply when send succeeds; otherwise None.
        """
        if not send_as_is:
            if msg is None:
                msg = opamp_pb2.AgentToServer()
            msg = self._populate_agent_to_server(msg)
        transport = (self.config.transport or TRANSPORT_HTTP).strip().lower()
        if transport == TRANSPORT_WEBSOCKET:
            try:
                return await self.send_websocket(msg)
            except:
                logging.getLogger(__name__).warning(
                    "Error sending websocket client-to-server message"
                )

        try:
            return await self.send_http(msg)
        except Exception as err:
            logging.getLogger(__name__).warning(
                "Error sending HTTP client-to-server message\n %s",
                err,
            )
        return None

    def _populate_disconnect(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.AgentToServer:
        """Populate disconnect data and ensure instance UID is set.

        Args:
            msg: AgentToServer message to mark as a disconnect payload.

        Returns:
            Updated disconnect message.
        """
        if self.data.uid_instance is not None:
            msg.instance_uid = self.data.uid_instance
            logging.getLogger(__name__).warning(
                "Set disconnect message instance UID to %s", self.data.uid_instance
            )
        msg.agent_disconnect.SetInParent()
        return msg

    async def send_disconnect(self) -> None:
        """Implements `OpAMPClientInterface.send_disconnect`.

        Send a disconnect message without modifying the payload.
        """
        msg = self._populate_disconnect(opamp_pb2.AgentToServer())
        logging.getLogger(__name__).debug("Built disconnect message")

        try:
            await self.send(msg, send_as_is=True)
            self.allow_heartbeat = False
        except Exception:
            logging.getLogger(__name__).warning("Failed to send disconnect message")

    async def _send_disconnect_with_timeout(self, timeout_seconds: float = 1.0) -> None:
        """Best-effort disconnect send with a short timeout.

        Args:
            timeout_seconds: Maximum wait time for sending disconnect.
        """
        try:
            logging.getLogger(__name__).warning("_send_disconnect_with_timeout exiting")
            await asyncio.wait_for(self.send_disconnect(), timeout=timeout_seconds)
        except Exception:
            logging.getLogger(__name__).warning("Disconnect send timed out")
        logging.getLogger(__name__).warning("_send_disconnect_with_timeout exiting")

    def finalize(self) -> None:
        """Implements `OpAMPClientInterface.finalize`.

        Best-effort finalizer to send disconnect.
        """
        try:
            loop = asyncio.get_running_loop()
            logging.getLogger(__name__).debug("finalize - got loop")
        except RuntimeError:

            def _runner() -> None:
                """Run best-effort async disconnect send inside a dedicated thread."""
                try:
                    logging.getLogger(__name__).debug(
                        "About to send disconnect message"
                    )
                    asyncio.run(self._send_disconnect_with_timeout())
                except Exception as err:
                    logging.getLogger(__name__).error(
                        "Failed to send disconnect message, error is:\n %s", err
                    )
                    return

            thread = threading.Thread(target=_runner, daemon=True)
            thread.start()
        else:
            loop.create_task(self._send_disconnect_with_timeout())

    def __del__(self) -> None:
        """Attempt graceful disconnect/finalize during object destruction."""
        print("FINALIZER triggered")
        self.finalize()

    async def send_websocket(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via WebSocket and return the response.

        Args:
            msg: Populated AgentToServer payload to send.

        Returns:
            Parsed ServerToAgent reply from the provider.
        """
        url = f"{self.data.base_url}{OPAMP_HTTP_PATH}"
        logging.getLogger(__name__).debug("Calling web socket at %s", url)

        async with websockets.connect(url) as web_socket:
            await web_socket.send(encode_message(msg.SerializeToString()))
            data = await web_socket.recv()
            await web_socket.close(code=1000)
            await web_socket.wait_closed()
        if isinstance(data, str):
            data = data.encode(UTF8_ENCODING)
        header, payload = decode_message(data)
        if header != OPAMP_HEADER_NONE:
            raise ValueError(ERR_UNSUPPORTED_HEADER)
        reply = opamp_pb2.ServerToAgent()
        reply.ParseFromString(payload)

        self._handle_server_to_agent(reply)
        return reply

    def launch_agent_process(self) -> bool:
        """Implements `OpAMPClientInterface.launch_agent_process`.

        Launch the Fluent Bit process using configured params.
        """
        launched = True
        logger = logging.getLogger(__name__)
        cmd = [
            FLUENTBIT_CMD,
            *(self.config.agent_additional_params or []),
            FLUENTBIT_CONFIG_FLAG,
            self.config.agent_config_path,
        ]
        logger.debug(
            "About to start Fluent Bit with %s and cmd %s",
            self.config.agent_config_path,
            cmd,
        )

        with self.data.process_lock:
            process_response: subprocess.Popen[bytes] = subprocess.Popen(cmd)
            self.data.agent_process = process_response
            self.data.launched_at = time.time_ns()
        logger.info("Launch result = %s", process_response)
        return launched

    def terminate_agent_process(self) -> None:
        """Implements `OpAMPClientInterface.terminate_agent_process`.

        Terminate the launched Agent process if available.
        """
        logger = logging.getLogger(__name__)
        with self.data.process_lock:
            process = self.data.agent_process
            self.data.allow_heartbeat = False
            if process is None:
                return
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Agent did not terminate in time; killing process")
                print("Agent did not terminate in time; killing process")

                process.kill()
                process.wait(timeout=5)
            self.data.agent_process = None

    def restart_agent_process(self) -> bool:
        """Implements `OpAMPClientInterface.restart_agent_process`.

        Stop the current agent process and start a new instance.
        """
        logger = logging.getLogger(__name__)
        logger.info("Restarting agent process")
        lock_acquired = self.data.process_lock.acquire(timeout=30)
        if not lock_acquired:
            raise AgentException(
                "Timed out waiting for process lock while restarting agent process"
            )
        try:
            self.terminate_agent_process()
            relaunched = self.launch_agent_process()
        finally:
            self.data.process_lock.release()
        if not relaunched:
            raise AgentException("Failed to restart agent process")
        logger.info("Agent process restarted")
        return relaunched

    def _heartbeat_key(self, path: str) -> str:
        """Return the last URL path component as the dictionary key."""
        return path.rstrip("/").split("/")[-1]

    def poll_local_status_with_codes(
        self, port: int
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Implements `OpAMPClientInterface.poll_local_status_with_codes`.

        Poll local health endpoints and collect response bodies and status codes.

        Args:
            port: Local agent HTTP status port to query.

        Returns:
            Tuple of `(results, codes)` maps keyed by heartbeat endpoint name.
        """
        results: dict[str, str] = {}
        codes: dict[str, str] = {}
        for path in _HEARTBEAT_PATHS:
            url = f"{LOCALHOST_BASE}:{port}{path}"
            key = self._heartbeat_key(path)
            try:
                resp = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS)
                results[key] = resp.text
                codes[key] = str(resp.status_code)
                resp.raise_for_status()
            except Exception as exc:  # pragma: no cover - error path varies by env
                results[key] = f"{ERR_PREFIX}{exc}"
                codes[key] = ERR_STATUS
        return results, codes

    def add_agent_version(self, port: int) -> None:
        """Implements `OpAMPClientInterface.add_agent_version`.

        Fetch Fluent Bit version endpoint and store in client runtime metadata.

        Args:
            port: Local agent HTTP status port used for version endpoint calls.
        """
        url = f"{LOCALHOST_BASE}:{port}"
        try:
            resp = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            value = resp.text
            try:
                data = resp.json()
                version = None
                edition = None
                if isinstance(data, dict):
                    version = data.get(KEY_FLUENT_BIT_VERSION)
                    edition = data.get(KEY_FLUENT_BIT_EDITION)
                    fb = data.get(JSON_KEY_FLUENT_BIT) or data.get(JSON_KEY_FLUENTBIT)
                    if isinstance(fb, dict):
                        self.data.agent_type_name = VALUE_AGENT_TYPE_FLUENT_BIT
                        version = version or fb.get(JSON_KEY_VERSION)
                        edition = edition or fb.get(JSON_KEY_EDITION)
                if version or edition:
                    if version and edition:
                        value = f"{version} ({edition})"
                    else:
                        value = version or edition
                self.data.agent_version = value
            except ValueError as val_exc:
                logging.getLogger(__name__).warning(
                    "failed to parse Agent version response: %s", val_exc
                )
        except Exception as exc:  # pragma: no cover - error path varies by env
            logging.getLogger(__name__).warning(
                "failed to parse Agent version response: %s", exc
            )

    def get_agent_description(
        self, instance_uid: bytes | str | None = None
    ) -> opamp_pb2.AgentDescription:
        """Implements `OpAMPClientInterface.get_agent_description`.

        Build AgentDescription for outbound AgentToServer messages.

        Args:
            instance_uid: Optional explicit service instance id override.

        Returns:
            Populated AgentDescription protobuf message.
        """
        logger = logging.getLogger(__name__)
        desc = opamp_pb2.AgentDescription()
        service_name = self.config.service_name
        service_namespace = self.config.service_namespace
        fluentbit_version = self.data.agent_type_name + " - " + self.data.agent_version
        metadata = self.get_host_metadata()

        if service_name:
            desc.identifying_attributes.append(
                anyvalue_pb2.KeyValue(
                    key=KEY_SERVICE_NAME,
                    value=anyvalue_pb2.AnyValue(string_value=service_name),
                )
            )
        else:
            logger.warning("No Service name to provide")

        if service_namespace:
            desc.identifying_attributes.append(
                anyvalue_pb2.KeyValue(
                    key=KEY_SERVICE_NAMESPACE,
                    value=anyvalue_pb2.AnyValue(string_value=service_namespace),
                )
            )
        else:
            logger.warning("No Service Namespace to provide")

        for key, value in metadata.items():
            desc.non_identifying_attributes.append(
                anyvalue_pb2.KeyValue(
                    key=key,
                    value=anyvalue_pb2.AnyValue(string_value=value),
                )
            )

        desc.identifying_attributes.append(
            anyvalue_pb2.KeyValue(
                key=KEY_SERVICE_TYPE,
                value=anyvalue_pb2.AnyValue(string_value="Fluent Bit"),
            )
        )

        service_instance_id = (
            instance_uid
            if instance_uid is not None
            else self.config.service_instance_id
        )
        if isinstance(service_instance_id, str):
            service_instance_id = resolve_service_instance_id_template(
                service_instance_id
            )
        if service_instance_id:
            desc.identifying_attributes.append(
                anyvalue_pb2.KeyValue(
                    key=KEY_SERVICE_INSTANCE_ID,
                    value=anyvalue_pb2.AnyValue(
                        string_value=(
                            service_instance_id.hex()
                            if isinstance(service_instance_id, (bytes, bytearray))
                            else str(service_instance_id)
                        )
                    ),
                )
            )

        if fluentbit_version:
            desc.identifying_attributes.append(
                anyvalue_pb2.KeyValue(
                    key=KEY_SERVICE_VERSION,
                    value=anyvalue_pb2.AnyValue(string_value=fluentbit_version),
                )
            )
        else:
            logger.warning("No Client version to provide")

        logger.debug("Agent description is :%s", desc)

        return desc

    def get_agent_capabilities(self) -> int:
        """Implements `OpAMPClientInterface.get_agent_capabilities`.

        Return the required agent capability bitmask.

        Returns:
            Bitmask built from the hardwired required capability names.
        """
        required_agent_capabilities = (
            "ReportsStatus",
            "AcceptsRestartCommand",
            "ReportsHealth",
        )
        return parse_capabilities(
            required_agent_capabilities,
            AgentCapabilities,
        )

    def get_custom_capabilities_payload(self) -> opamp_pb2.CustomCapabilities:
        """Build CustomCapabilities from the custom handler registry."""
        if not self._custom_handler_lookup:
            self._custom_handler_lookup = build_factory_lookup(
                self._custom_handler_folder,
                client_data=self.data,
                allow_custom_capabilities=bool(self.config.allow_custom_capabilities),
            )
        logging.getLogger(__name__).debug(
            "custom capability lookup entries=%s",
            sorted(self._custom_handler_lookup.keys()),
        )

        capabilities = sorted(
            {
                f"{CAPABILITY_PREFIX_REQUEST}{str(fqdn).strip()}"
                for fqdn in self._custom_handler_lookup.keys()
                if str(fqdn).strip()
            }
        )
        payload = opamp_pb2.CustomCapabilities()
        payload.capabilities.extend(capabilities)
        logging.getLogger(__name__).debug(
            "custom capabilities payload generated=%s",
            capabilities,
        )
        return payload

    def get_host_metadata(self) -> dict[str, str]:
        """Collect basic host metadata as key/value pairs."""
        return {
            HOST_META_KEY_OS_TYPE: platform.system(),
            HOST_META_KEY_OS_VERSION: platform.version(),
            HOST_META_KEY_HOSTNAME: socket.gethostname(),
        }

    def handle_error_response(
        self, error_response: opamp_pb2.ServerErrorResponse
    ) -> None:
        """Log details from a ServerErrorResponse.

        Args:
            error_response: Server error payload to inspect and log.
        """
        logger = logging.getLogger(__name__)
        logger.warning("server error_response type=%s", error_response.type)
        if error_response.error_message:
            logger.warning(
                "*******/n server error_response message=%s/n*******",
                error_response.error_message,
            )
        if error_response.HasField(PB_FIELD_RETRY_INFO):
            logger.warning(
                "server error_response retry_after_nanoseconds=%s",
                error_response.retry_info.retry_after_nanoseconds,
            )

    def handle_remote_config(self, remote_config: opamp_pb2.AgentRemoteConfig) -> None:
        """Implements `OpAMPClientInterface.handle_remote_config`.

        Log the remote-config payload received from the provider.

        Args:
            remote_config: Remote configuration payload from ServerToAgent.
        """
        logging.getLogger(__name__).info(
            "server remote_config:\n%s", text_format.MessageToString(remote_config)
        )

    def handle_connection_settings(
        self, connection_settings: opamp_pb2.ConnectionSettingsOffers
    ) -> None:
        """Implements `OpAMPClientInterface.handle_connection_settings`.

        Log provider connection-settings offers for diagnostics and visibility.

        Args:
            connection_settings: Connection settings offered by the provider.
        """
        logging.getLogger(__name__).info(
            "server connection_settings:\n%s",
            text_format.MessageToString(connection_settings),
        )

    def handle_packages_available(
        self, packages_available: opamp_pb2.PackagesAvailable
    ) -> None:
        """Implements `OpAMPClientInterface.handle_packages_available`.

        Log package offers sent by the provider.

        Args:
            packages_available: Package availability payload from ServerToAgent.
        """
        logging.getLogger(__name__).info(
            "server packages_available:\n%s",
            text_format.MessageToString(packages_available),
        )

    def handle_flags(self, flags: int) -> None:
        """Log raw server flag bitmask values from ServerToAgent.

        Args:
            flags: Integer bitmask from `ServerToAgent.flags`.
        """
        logger = logging.getLogger(__name__)
        flag_names: list[str] = []
        for enum_value in opamp_pb2.ServerToAgentFlags.DESCRIPTOR.values:
            if enum_value.number == 0:
                continue
            if flags & enum_value.number:
                name = enum_value.name
                if name.startswith("ServerToAgentFlags_"):
                    name = name[len("ServerToAgentFlags_") :]
                flag_names.append(name)

        if PB_FLAG_REPORT_FULL_STATE in flag_names:
            self.data.set_all_flags(True)
            logger.info(
                "server flags include ReportFullState; set all reporting flags true"
            )

        if flag_names:
            logger.info("server flags: %s (%s)", flags, ", ".join(flag_names))
        else:
            logger.info("server flags: %s", flags)

    def handle_capabilities(self, capabilities: int) -> None:
        """Log raw server capability bitmask values from ServerToAgent.

        Args:
            capabilities: Integer bitmask from `ServerToAgent.capabilities`.
        """
        logging.getLogger(__name__).info("server capabilities: %s", capabilities)

    def handle_command(self, command: opamp_pb2.ServerToAgentCommand) -> None:
        """Handle ServerToAgent command payloads.

        Args:
            command: Command payload from the provider.
        """
        logger = logging.getLogger(__name__)
        if command is None:
            return
        logger.info("server command:\n%s", text_format.MessageToString(command))
        match command.type:
            case opamp_pb2.CommandType.CommandType_Restart:
                logger.info("server command to restart recognized")
                self.restart_agent_process()
            case _:
                raise AgentException(f"Unknown command type: {command.type}")

    def handle_agent_identification(
        self, agent_identification: opamp_pb2.AgentIdentification
    ) -> None:
        """Update local instance UID when the server sends AgentIdentification.

        Args:
            agent_identification: AgentIdentification payload with replacement UID.
        """
        logging.getLogger(__name__).info(
            "server agent_identification:\n%s",
            text_format.MessageToString(agent_identification),
        )
        self.data.uid_instance = agent_identification.new_instance_uid

    def handle_custom_capabilities(
        self, custom_capabilities: opamp_pb2.CustomCapabilities
    ) -> None:
        """Log custom capability declarations received from the provider.

        Args:
            custom_capabilities: Custom capability list reported by the provider.
        """
        logging.getLogger(__name__).info(
            "server custom_capabilities:\n%s",
            text_format.MessageToString(custom_capabilities),
        )

    def handle_custom_message(self, custom_message: opamp_pb2.CustomMessage) -> None:
        """Implements `OpAMPClientInterface.handle_custom_message`.

        Route a custom message to its handler and execute it against this client.

        Args:
            custom_message: Custom message payload containing capability and data.
        """
        logger = logging.getLogger(__name__)
        logger.info(
            "server custom_message:\n%s", text_format.MessageToString(custom_message)
        )
        if custom_message is None:
            return

        capability = str(custom_message.capability or "").strip()
        if not capability:
            raise AgentException("CustomMessage capability is missing")
        logger.debug(
            "handling custom message capability=%s type=%s data_len=%s",
            capability,
            str(custom_message.type or ""),
            len(bytes(custom_message.data or b"")),
        )

        handler = create_handler(
            capability,
            self._custom_handler_folder,
            client_data=self.data,
            factory_lookup=self._custom_handler_lookup,
            allow_custom_capabilities=bool(self.config.allow_custom_capabilities),
        )
        logger.debug(
            "custom handler lookup initial capability=%s found=%s",
            capability,
            handler.__class__.__name__ if handler is not None else None,
        )
        if handler is None:
            self._custom_handler_lookup = build_factory_lookup(
                self._custom_handler_folder,
                client_data=self.data,
            )
            handler = create_handler(
                capability,
                self._custom_handler_folder,
                client_data=self.data,
                factory_lookup=self._custom_handler_lookup,
                allow_custom_capabilities=bool(self.config.allow_custom_capabilities),
            )
            logger.debug(
                "custom handler lookup after refresh capability=%s found=%s",
                capability,
                handler.__class__.__name__ if handler is not None else None,
            )
        if handler is None:
            raise AgentException(
                f"No command handler registered for capability: {capability}"
            )

        handler.set_custom_message_handler(custom_message)
        logger.debug(
            "executing custom handler capability=%s handler=%s",
            capability,
            handler.__class__.__name__,
        )
        command_error = handler.execute(self)
        if command_error is not None:
            raise AgentException(str(command_error))

    async def _heartbeat_loop(self, port: int) -> None:
        """Run a periodic polling loop that updates last heartbeat results.

        Args:
            port: Local agent HTTP status port used for heartbeat polling.
        """
        logger = logging.getLogger(__name__)
        interval = max(0, int(self.config.heartbeat_frequency) - HEARTBEAT_SKEW_SECONDS)
        logger.debug("Heartbeat cycle start - checking every %s", interval)
        try:
            while self.data.allow_heartbeat:
                await asyncio.sleep(interval)
                if check_semaphore():
                    await self._send_disconnect_with_timeout()
                    self.data.allow_heartbeat = False
                try:
                    with self.data.process_lock:
                        results, codes = self.poll_local_status_with_codes(port)
                        self.data.last_heartbeat_results.clear()
                        self.data.last_heartbeat_results.update(results)
                        self.add_agent_version(port)
                        self.data.last_heartbeat_http_codes = codes
                    if self.config.log_agent_api_responses and self.data.logFLB:
                        logger.debug("Heartbeat outcome --> %s", results)

                    logger.info("Heartbeat response codes: %s", codes)

                except KeyboardInterrupt as kb:
                    logger.error("Error - a disturbance in the force\n %s", kb)
                    self.data.allow_heartbeat = False
                    await self._send_disconnect_with_timeout()
                    break
                except Exception as err:
                    logger.error("Something stumbled - we catch and carry on\n %s", err)
                    self.data.last_heartbeat_results = None
                    self.data.last_heartbeat_http_codes = None

                self._handle_server_to_agent(await self.send())
        except BaseException as err:
            await self._send_disconnect_with_timeout()
            logger.error(
                "heartbeat outer error trap triggered by:\n%s\n %s",
                err,
                traceback.format_exc(),
            )
            print("...ouch, bye")


def check_semaphore() -> bool:
    """Return True when the supervisor semaphore file exists on local disk."""
    if os.path.isfile("OpAMPSupervisor.signal"):
        logging.getLogger(__name__).warning("Spotted Semaphore file")
        return True
    return False


def load_agent_config(config: consumer_config.ConsumerConfig) -> ConsumerConfig:
    """Load Fluent Bit config values and agent metadata into the config object.

    Args:
        config: Consumer configuration to enrich from Fluent Bit config file content.

    Returns:
        The same config object with parsed HTTP and metadata values applied.
    """
    logger = logging.getLogger(__name__)
    logger.warning("All config is %s", config)
    path = config.agent_config_path
    if not path:
        raise ValueError(f"{CFG_AGENT_CONFIG_PATH} is not set")

    comment_pattern = (
        rf"^\s*#\s*(?P<key>agent_description|{KEY_SERVICE_INSTANCE_ID_COMMENT})\s*"
        r"[:=]\s*(?P<value>.+?)\s*$"
    )
    comment_kv = re.compile(comment_pattern, re.IGNORECASE)
    config_kv = re.compile(
        r"^\s*(?P<key>http_port|http_listen|http_server)\s*(?:[:=]|\s+)\s*(?P<value>\S.*)$",
        re.IGNORECASE,
    )
    with open(path, encoding=UTF8_ENCODING) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            comment_match = comment_kv.match(raw_line)
            if comment_match:
                key = comment_match.group("key").lower()
                value = comment_match.group("value")
                try:
                    if key == KEY_SERVICE_INSTANCE_ID_COMMENT:
                        value = resolve_service_instance_id_template(value)
                    config[key] = value
                    logger.info("located >%s< with value >%s<", key, value)
                    continue
                except KeyError:
                    logger.error("barfed with comment match %s --> %s", key, value)
                    continue

            config_match = config_kv.match(raw_line)
            if config_match:
                key = config_match.group("key").lower()
                value = config_match.group("value").strip()
                try:
                    if key == KEY_HTTP_PORT:
                        port_value = int(value)
                        config.client_status_port = port_value
                        config.agent_http_port = port_value
                        logger.info("located >%s< with value >%s<", key, value)
                    elif key == KEY_HTTP_LISTEN:
                        config.agent_http_listen = value
                        logger.info("located >%s< with value >%s<", key, value)
                    elif key == KEY_HTTP_SERVER:
                        config.agent_http_server = value
                        logger.info("located >%s< with value >%s<", key, value)
                    else:
                        config[key] = value
                        logger.info("located >%s< with value >%s<", key, value)
                    continue
                except KeyError:
                    logger.error("barfed with config match %s --> %s", key, value)
                    continue

    return config


def build_minimal_agent(
    instance_uid: bytes | None = None,
    capabilities: int | None = None,
) -> opamp_pb2.AgentToServer:
    """Create a minimal AgentToServer message with configured capabilities.

    Args:
        instance_uid: Optional instance UID bytes to assign.
        capabilities: Optional capabilities bitmask.

    Returns:
        Minimal AgentToServer protobuf message for tests or bootstrap flows.
    """
    msg = opamp_pb2.AgentToServer()
    if instance_uid is not None:
        msg.instance_uid = instance_uid
    msg.capabilities = capabilities or 0
    return msg


async def run_client(client) -> None:
    """Trigger a single send cycle for the provided client instance.

    Args:
        client: OpAMP client object exposing an async `send()` method.
    """
    await client.send()


def _force_exit_on_lingering_threads() -> None:
    """Force process exit when non-daemon threads keep the interpreter alive."""
    alive_threads = [
        thread
        for thread in threading.enumerate()
        if thread is not threading.main_thread()
        and thread.is_alive()
        and not thread.daemon
    ]
    if not alive_threads:
        return
    print(
        "forcing process exit; non-daemon threads still alive: %s",
        [thread.name for thread in alive_threads],
    )
    os._exit(0)


def _get_local_ip() -> str:
    """Return a best-effort local host IP address."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def _get_local_mac() -> str:
    """Return local MAC address in colon-delimited lower-case format."""
    node = int(uuid.getnode())
    return ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))


def resolve_service_instance_id_template(value: str | None) -> str | None:
    """Resolve service_instance_id template tokens into runtime host values."""
    if value is None:
        return None
    resolved = str(value)
    if TOKEN_IP in resolved:
        resolved = resolved.replace(TOKEN_IP, _get_local_ip())
    if TOKEN_HOSTNAME in resolved:
        resolved = resolved.replace(TOKEN_HOSTNAME, socket.gethostname())
    if TOKEN_MAC_ADDR in resolved:
        resolved = resolved.replace(TOKEN_MAC_ADDR, _get_local_mac())
    return resolved


def main() -> None:
    """Load config, read Fluent Bit settings, launch Fluent Bit, start heartbeat."""
    try:
        tracemalloc.start()
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("-h", "--help", action="store_true")
        parser.add_argument("--config-path", type=str)
        parser.add_argument("--server-url", type=str)
        parser.add_argument("--server-port", type=int)
        parser.add_argument(
            "--agent-config-path",
            "--fluentbit-config-path",
            dest="agent_config_path",
            type=str,
        )
        parser.add_argument(
            "--agent-additional-params",
            "--additional-agent-params",
            "--additional-fluent-bit-params",
            dest="agent_additional_params",
            nargs="*",
        )
        parser.add_argument("--heartbeat-frequency", type=int)
        parser.add_argument(
            "--log-level",
            type=str,
            help="logging level name override (for example DEBUG, INFO, WARNING)",
        )
        args = parser.parse_args()

        config = consumer_config.load_config_with_overrides(
            config_path=pathlib.Path(args.config_path) if args.config_path else None,
            server_url=args.server_url,
            server_port=args.server_port,
            agent_config_path=args.agent_config_path,
            agent_additional_params=args.agent_additional_params,
            heartbeat_frequency=args.heartbeat_frequency,
            log_level=args.log_level,
        )
        resolved_log_level = consumer_config.resolve_log_level(config.log_level)
        root_logger = logging.getLogger()
        # Do not force-reconfigure handlers here. In tests/tools, handlers may be
        # preinstalled (for capture), and replacing them can break stream lifecycle.
        if not root_logger.handlers:
            logging.basicConfig(level=resolved_log_level)
        else:
            root_logger.setLevel(resolved_log_level)
        logger = logging.getLogger(__name__)

        if args.help:
            print(
                json.dumps(
                    _config_parameters_payload(config),
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        logger.warning("about to process FLB config")
        config = load_agent_config(config)

        if config.client_status_port is None:
            raise ValueError("client_status_port not found in Fluent Bit config")

        if config.server_url is None and config.server_port is not None:
            config.server_url = f"{LOCALHOST_BASE}:{config.server_port}"
        if config.server_url is None:
            raise ValueError("server_url is not configured")

        logger.debug(msg="setting up OpAMP")
        client = OpAMPClient(config.server_url, config)

        client.launch_agent_process()
        client.add_agent_version(config.client_status_port)

        logger.info("introducing self to server")
        asyncio.run(run_client(client))

        asyncio.run(client._heartbeat_loop(config.client_status_port))
        client.terminate_agent_process()

    except KeyboardInterrupt as kb:
        print(f"... bzzzz keyboard\n %s", kb)
    except SystemExit as sys_exit:
        print(f"... bzzzz brutal exit\n %s", sys_exit)

    except:
        print(f"... bzzzzzzzzzzz")


if __name__ == "__main__":
    main()
    print("... Bye")
    # _force_exit_on_lingering_threads()
    sys.exit(1)
