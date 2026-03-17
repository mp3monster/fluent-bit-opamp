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
from ast import List
from ctypes import string_at
from dataclasses import dataclass, field
import logging
from os import strerror
import pathlib
import platform
import re
import socket
import subprocess
import threading
import time
import tracemalloc
import asyncio

import httpx
import websockets
from google.protobuf import text_format

try:
    from uuid_v7.base import uuid7
except ImportError:  # pragma: no cover - environment-dependent
    uuid7 = None

import uuid

from opamp_consumer import config as consumer_config
from opamp_consumer.config import CFG_FLUENTBIT_CONFIG_PATH, ConsumerConfig
from opamp_consumer.proto import anyvalue_pb2, opamp_pb2
from opamp_consumer.transport import decode_message, encode_message
from shared.opamp_config import (
    OPAMP_HTTP_PATH,
    OPAMP_TRANSPORT_HEADER_NONE,
    UTF8_ENCODING,
)

HTTP_TIMEOUT_SECONDS = 5.0  # Timeout for local HTTP calls.
TRANSPORT_HTTP = "http"
TRANSPORT_WEBSOCKET = "websocket"
HEARTBEAT_SKEW_SECONDS = 1  # Sleep interval is heartbeat_frequency minus this value.
LOCALHOST_BASE = "http://localhost"  # Base URL for local Fluent Bit endpoints.
CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.
ERR_PREFIX = "error: "  # Prefix for error values stored in results.
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
KEY_SERVICE_NAME = "service.name"  # Agent description service name key.
KEY_SERVICE_NAMESPACE = "service.namespace"  # Agent description service namespace key.
KEY_SERVICE_INSTANCE_ID = "service.instance.id"  # Agent description instance id key.
KEY_SERVICE_VERSION = "service.version"  # Agent description version key.
CAPABILITIES_MAP = {
    "UnspecifiedAgentCapability": 0x00000000,
    "ReportsStatus": 0x00000001,
    "AcceptsRemoteConfig": 0x00000002,
    "ReportsEffectiveConfig": 0x00000004,
    "AcceptsPackages": 0x00000008,
    "ReportsPackageStatuses": 0x00000010,
    "ReportsOwnTraces": 0x00000020,
    "ReportsOwnMetrics": 0x00000040,
    "ReportsOwnLogs": 0x00000080,
    "AcceptsOpAMPConnectionSettings": 0x00000100,
    "AcceptsOtherConnectionSettings": 0x00000200,
    "AcceptsRestartCommand": 0x00000400,
    "ReportsHealth": 0x00000800,
    "ReportsRemoteConfig": 0x00001000,
    "ReportsHeartbeat": 0x00002000,
    "ReportsAvailableComponents": 0x00004000,
    "ReportsConnectionSettingsStatus": 0x00008000,
}
LOG_INVALID_HTTP_PORT = "invalid http_port value: %s"  # Log format for bad ports.
LOG_HTTP_SERVER_DISABLED = (
    "http_server is not enabled: %s"  # Log format for disabled HTTP.
)
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.

_HEARTBEAT_PATHS = (  # Local endpoints polled per heartbeat.
    "/api/v1/uptime",
    "/api/v1/health",
    "/api/v2/metrics/prometheus",
)


@dataclass
class OpAMPClientData:
    """Container for OpAMP client instance data."""

    config: ConsumerConfig
    base_url: str
    uid_instance: bytes | None
    allow_heartbeat: bool = True
    msg_sequence_number: int = 0
    last_heartbeat_http_codes: dict[str, int] | None = None
    last_heartbeat_call: int = 0
    last_heartbeat_results: dict[str, str] | None = field(default_factory=dict)
    launched_at: int = 0


class OpAMPClient:
    """Minimal OpAMP client supporting HTTP and WebSocket transports."""

    def __init__(self, base_url: str, config: ConsumerConfig | None = None) -> None:
        """Create a client bound to a base URL."""
        if config is None:
            config = globals().get("CONFIG") or consumer_config.CONFIG
        if config is None:
            logging.getLogger(__name__).warning("No config supplied to OpAMPClient")
            raise ValueError("OpAMP client requires a consumer config")
        if uuid7 is None:
            logging.getLogger(__name__).warning(
                "uuid_v7 not available; falling back to uuid4"
            )
            uid_instance = uuid.uuid4().bytes
        else:
            uid_instance = uuid7().bytes

        self.data = OpAMPClientData(
            config=config,
            base_url=base_url.rstrip("/"),
            uid_instance=uid_instance,
        )
        self._ensure_reports_status_capability()

    @property
    def config(self) -> ConsumerConfig:
        return self.data.config

    @config.setter
    def config(self, value: ConsumerConfig) -> None:
        self.data.config = value

    def _ensure_reports_status_capability(self) -> None:
        """Ensure ReportsStatus is set on the client configuration."""
        required_bit = CAPABILITIES_MAP.get("ReportsStatus", 0)
        configured = self.config.agent_capabilities
        logger = logging.getLogger(__name__)
        if isinstance(configured, int):
            if required_bit and (configured & required_bit) == 0:
                self.config.agent_capabilities = configured | required_bit
                logger.info("Added ReportsStatus to agent capabilities bitmask")
            return
        if not configured:
            self.config.agent_capabilities = required_bit
            logger.info("Defaulted agent capabilities to ReportsStatus")
            return
        if isinstance(configured, (list, tuple, set)):
            if "ReportsStatus" not in {str(name) for name in configured}:
                updated = list(configured)
                updated.append("ReportsStatus")
                self.config.agent_capabilities = updated
                logger.info("Added ReportsStatus to agent capabilities list")

    async def send_http(self, msg: opamp_pb2.AgentToServer) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via HTTP and return the response."""
        url = f"{self.data.base_url}{OPAMP_HTTP_PATH}"
        logging.getLogger(__name__).debug(f"Calling REST endpoint at {url}")
        payload = msg.SerializeToString()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                content=payload,
                headers={"Content-Type": CONTENT_TYPE_PROTO},
            )
            resp.raise_for_status()
            reply = opamp_pb2.ServerToAgent()
            reply.ParseFromString(resp.content)
            self._handle_server_to_agent(reply)
            return reply

    def _populate_agent_to_server_health(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.AgentToServer:
        healthy = True
        if self.data.last_heartbeat_results:
            healthy = (
                self.data.last_heartbeat_http_codes is not None
                and self.data.last_heartbeat_http_codes["health"]
            )
            last_error = ""
            for value in self.data.last_heartbeat_results.values():
                text = str(value)
                logging.getLogger(__name__).debug(f"Evaluating for health>>{text}")
                if text.startswith(ERR_PREFIX):
                    healthy = False
                    last_error = text

                msg = self._health_from_metrics(msg, text)

            msg.health.status = "heartbeat"
            if not healthy and last_error:
                msg.health.last_error = last_error
        else:
            healthy = False
            msg.health.last_error = "Supervisor has not state"

        msg.health.start_time_unix_nano = time.time_ns() - self.data.launched_at
        msg.health.status_time_unix_nano = time.time_ns()
        msg.health.healthy = int(healthy)
        logging.getLogger(__name__).debug(f"Health info sending is >{msg.health}<")
        return msg

    def _health_from_metrics(self, msg, text) -> opamp_pb2.AgentToServer:
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
        msg.agent_description.CopyFrom(self.get_agent_description())
        msg.capabilities = self.get_agent_capabilities()
        msg.sequence_num = self.data.msg_sequence_number
        if self.data.uid_instance is not None:
            msg.instance_uid = self.data.uid_instance
        else:
            logging.getLogger(__name__).error("No UID set")

        msg = self._populate_agent_to_server_health(msg)
        return msg

    def _handle_server_to_agent(self, reply: opamp_pb2.ServerToAgent) -> bool:
        logger = logging.getLogger(__name__)
        successful_message = True

        if reply is None:
            logger.error("Been given None response")
            return False

        try:
            if reply.HasField("instance_uid"):
                if reply.instance_uid != self.config.service_instance_id:
                    logger.error(
                        "Message doesn't have an instance uid or doesn't match our service instance id %s",
                        self.config.service_instance_id,
                    )
                    successful_message = False
            else:
                logging.getLogger(__name__).error(
                    "Server didnt share instance_uid, my service instance id is %s",
                    self.config.service_instance_id,
                )
                successful_message = False
        except ValueError:
            logger.error("Couldn't locate instance_uid in reply")
            successful_message = False

        if reply.HasField("error_response"):
            self.handle_error_response(reply.error_response)
        if reply.HasField("remote_config"):
            self.handle_remote_config(reply.remote_config)
        if reply.HasField("connection_settings"):
            self.handle_connection_settings(reply.connection_settings)
        if reply.HasField("packages_available"):
            self.handle_packages_available(reply.packages_available)
        if reply.flags:
            self.handle_flags(reply.flags)
        if reply.capabilities:
            self.handle_capabilities(reply.capabilities)
        if reply.HasField("agent_identification"):
            self.handle_agent_identification(reply.agent_identification)
        if reply.HasField("command"):
            self.handle_command(reply.command)
        if reply.HasField("custom_capabilities"):
            self.handle_custom_capabilities(reply.custom_capabilities)
        if reply.HasField("custom_message"):
            self.handle_custom_message(reply.custom_message)
        return successful_message

    async def send(
        self, msg: opamp_pb2.AgentToServer | None = None
    ) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message using the configured transport."""
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
                f"Error sending HTTP client-to-server message\n {err}"
            )
        return None

    async def send_websocket(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via WebSocket and return the response."""
        url = f"{self.data.base_url}{OPAMP_HTTP_PATH}"
        logging.getLogger(__name__).debug(f"Calling web socket at {url}")

        async with websockets.connect(url) as web_socket:
            await web_socket.send(encode_message(msg.SerializeToString()))
            data = await web_socket.recv()
        if isinstance(data, str):
            data = data.encode(UTF8_ENCODING)
        header, payload = decode_message(data)
        if header != OPAMP_HEADER_NONE:
            raise ValueError(ERR_UNSUPPORTED_HEADER)
        reply = opamp_pb2.ServerToAgent()
        reply.ParseFromString(payload)

        self._handle_server_to_agent(reply)
        return reply

    def launch_fluent_bit(self) -> bool:
        """Launch the Fluent Bit process using configured params."""
        launched = True
        logger = logging.getLogger(__name__)
        cmd = [
            FLUENTBIT_CMD,
            *(self.config.additional_fluent_bit_params or []),
            FLUENTBIT_CONFIG_FLAG,
            self.config.fluentbit_config_path,
        ]
        logger.debug(
            f"About to start Fluent Bit with {self.config.fluentbit_config_path} and cmd {cmd}"
        )

        processResponse: subprocess.Popen[bytes] = subprocess.Popen(cmd)
        self.data.launched_at = time.time_ns()
        logger.info(f"Launch result = {processResponse}")
        return launched

    def _heartbeat_key(self, path: str) -> str:
        """Return the last URL path component as the dictionary key."""
        return path.rstrip("/").split("/")[-1]

    def poll_local_status_with_codes(
        self, port: int
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Poll local health endpoints and return maps of response text and status code."""
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
                codes[key] = "error"
        return results, codes

    def add_fluentbit_version(self, port: int) -> None:
        """Fetch Fluent Bit version endpoint and store in last heartbeat results."""
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
                    version = data.get("fluent-bit.version")
                    edition = data.get("fluent-bit.edition")
                    fb = data.get("fluent-bit") or data.get("fluentbit")
                    if isinstance(fb, dict):
                        version = version or fb.get("version")
                        edition = edition or fb.get("edition")
                if version or edition:
                    if version and edition:
                        value = f"{version} ({edition})"
                    else:
                        value = version or edition
            except ValueError as exc:
                logging.getLogger(__name__).warning(
                    "failed to parse Fluent Bit version response: %s", exc
                )
        except Exception as exc:  # pragma: no cover - error path varies by env
            value = f"{ERR_PREFIX}{exc}"
        self.data.last_heartbeat_results[KEY_FLUENTBIT_VERSION] = value

    def get_agent_description(
        self, instance_uid: bytes | str | None = None
    ) -> opamp_pb2.AgentDescription:
        """Build AgentDescription for outbound AgentToServer messages."""
        logger = logging.getLogger(__name__)
        desc = opamp_pb2.AgentDescription()
        service_name = self.config.service_name
        service_namespace = self.config.service_namespace
        fluentbit_version = self.data.last_heartbeat_results.get(KEY_FLUENTBIT_VERSION)
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
                key="service.type",
                value=anyvalue_pb2.AnyValue(string_value="Fluent Bit"),
            )
        )

        service_instance_id = (
            instance_uid
            if instance_uid is not None
            else self.config.service_instance_id
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

        logger.debug(f"Agent description is :{desc}")

        return desc

    def get_agent_capabilities(self) -> int:
        """Return the configured agent capability bitmask."""
        configured = self.config.agent_capabilities
        if isinstance(configured, int):
            logging.getLogger(__name__).debug(f"Capabilities named - {configured}")
            return configured
        if not configured:
            logging.getLogger(__name__).warning(
                "No capabilities configuration available applying required"
            )
            return 0
        mask = 0
        for name in configured:
            value = CAPABILITIES_MAP.get(str(name))
            if value is None:
                logging.getLogger(__name__).warning(
                    "unknown agent capability: %s", name
                )
                continue
            mask |= value
            logging.getLogger(__name__).debug(f"Added to mask {name} - code now {mask}")
        return mask

    def get_host_metadata(self) -> dict[str, str]:
        """Collect basic host metadata as key/value pairs."""
        return {
            "os_type": platform.system(),
            "os_version": platform.version(),
            "hostname": socket.gethostname(),
        }

    def handle_error_response(
        self, error_response: opamp_pb2.ServerErrorResponse
    ) -> None:
        """Log details from a ServerErrorResponse."""
        logger = logging.getLogger(__name__)
        logger.warning("server error_response type=%s", error_response.type)
        if error_response.error_message:
            logger.warning(
                "server error_response message=%s", error_response.error_message
            )
        if error_response.HasField("retry_info"):
            logger.warning(
                "server error_response retry_after_nanoseconds=%s",
                error_response.retry_info.retry_after_nanoseconds,
            )

    def handle_remote_config(self, remote_config: opamp_pb2.AgentRemoteConfig) -> None:
        logging.getLogger(__name__).info(
            "server remote_config:\n%s", text_format.MessageToString(remote_config)
        )

    def handle_connection_settings(
        self, connection_settings: opamp_pb2.ConnectionSettingsOffers
    ) -> None:
        logging.getLogger(__name__).info(
            "server connection_settings:\n%s",
            text_format.MessageToString(connection_settings),
        )

    def handle_packages_available(
        self, packages_available: opamp_pb2.PackagesAvailable
    ) -> None:
        logging.getLogger(__name__).info(
            "server packages_available:\n%s",
            text_format.MessageToString(packages_available),
        )

    def handle_flags(self, flags: int) -> None:
        logging.getLogger(__name__).info("server flags: %s", flags)

    def handle_capabilities(self, capabilities: int) -> None:
        logging.getLogger(__name__).info("server capabilities: %s", capabilities)

    def handle_command(self, command: opamp_pb2.ServerToAgentCommand) -> None:
        logging.getLogger(__name__).info(
            "server command:\n%s", text_format.MessageToString(command)
        )

    def handle_agent_identification(
        self, agent_identification: opamp_pb2.AgentIdentification
    ) -> None:
        logging.getLogger(__name__).info(
            "server agent_identification:\n%s",
            text_format.MessageToString(agent_identification),
        )

    def handle_custom_capabilities(
        self, custom_capabilities: opamp_pb2.CustomCapabilities
    ) -> None:
        logging.getLogger(__name__).info(
            "server custom_capabilities:\n%s",
            text_format.MessageToString(custom_capabilities),
        )

    def handle_custom_message(self, custom_message: opamp_pb2.CustomMessage) -> None:
        logging.getLogger(__name__).info(
            "server custom_message:\n%s", text_format.MessageToString(custom_message)
        )

    async def _heartbeat_loop(self, port: int) -> None:
        """Run a periodic polling loop that updates last heartbeat results."""
        logger = logging.getLogger(__name__)
        interval = max(0, int(self.config.heartbeat_frequency) - HEARTBEAT_SKEW_SECONDS)
        logger.debug(f"Heartbeat cycle start - checking every {interval}")
        while self.data.allow_heartbeat:
            time.sleep(interval)
            try:
                results, codes = self.poll_local_status_with_codes(port)
                self.data.last_heartbeat_results.clear()
                self.data.last_heartbeat_results.update(results)
                self.add_fluentbit_version(port)
                self.data.last_heartbeat_http_codes = codes
                if self.config.log_fluentbit_api_responses:
                    logger.info(f"Heartbeat outcome --> {results}")
                else:
                    logger.info("Heartbeat response codes: %s", codes)
            except:
                self.data.last_heartbeat_results = None
                self.data.last_heartbeat_http_codes = None

            self._handle_server_to_agent(await self.send())


def load_fluentbit_config(config: consumer_config.ConsumerConfig) -> ConsumerConfig:
    """Load Fluent Bit config values and agent metadata into the config object."""
    logger = logging.getLogger(__name__)
    logger.warning(f"All config is {config}")
    path = config.fluentbit_config_path
    if not path:
        raise ValueError(f"{CFG_FLUENTBIT_CONFIG_PATH} is not set")

    comment_kv = re.compile(
        rf"^\s*#\s*(?P<key>agent_description|{KEY_SERVICE_INSTANCE_ID_COMMENT})\s*[:=]\s*(?P<value>.+?)\s*$",
        re.IGNORECASE,
    )
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
                    config[key] = value
                    logger.info(f"located >{key}< with value >{value}<")
                    continue
                except KeyError:
                    logger.error(f"barfed with comment match {key} --> {value}")
                    continue

            config_match = config_kv.match(raw_line)
            if config_match:
                key = config_match.group("key").lower()
                value = config_match.group("value").strip()
                try:
                    if key == KEY_HTTP_PORT:
                        port_value = int(value)
                        config.http_port = port_value
                        config.fluentbit_http_port = port_value
                        logger.info(f"located >{key}< with value >{value}<")
                    elif key == KEY_HTTP_LISTEN:
                        config.http_listen = value
                        config.fluentbit_http_listen = value
                        logger.info(f"located >{key}< with value >{value}<")
                    elif key == KEY_HTTP_SERVER:
                        config.http_server = value
                        config.fluentbit_http_server = value
                        logger.info(f"located >{key}< with value >{value}<")
                    else:
                        config[key] = value
                        logger.info(f"located >{key}< with value >{value}<")
                    continue
                except KeyError:
                    logger.error(f"barfed with config match {key} --> {value}")
                    continue

    return config


def build_minimal_agent(
    instance_uid: bytes | None = None,
    capabilities: int | None = None,
) -> opamp_pb2.AgentToServer:
    """Create a minimal AgentToServer message with configured capabilities."""
    msg = opamp_pb2.AgentToServer()
    if instance_uid is not None:
        msg.instance_uid = instance_uid
    msg.capabilities = capabilities or 0
    return msg


async def run_client(client) -> None:
    await client.send()


def main() -> None:
    """Load config, read Fluent Bit settings, launch Fluent Bit, start heartbeat."""
    tracemalloc.start()
    logger = logging.getLogger(__name__)

    logger.debug("prepping CLI parser")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", type=str)
    parser.add_argument("--server-url", type=str)
    parser.add_argument("--server-port", type=int)
    parser.add_argument("--fluentbit-config-path", type=str)
    parser.add_argument("--additional-fluent-bit-params", nargs="*")
    parser.add_argument("--heartbeat-frequency", type=int)
    args = parser.parse_args()

    logger.debug("about to load with CLI overrides")
    config = consumer_config.load_config_with_overrides(
        config_path=pathlib.Path(args.config_path) if args.config_path else None,
        server_url=args.server_url,
        server_port=args.server_port,
        fluentbit_config_path=args.fluentbit_config_path,
        additional_fluent_bit_params=args.additional_fluent_bit_params,
        heartbeat_frequency=args.heartbeat_frequency,
    )

    logger.warning("about to process FLB config")
    config = load_fluentbit_config(config)

    if config.http_port is None:
        raise ValueError("http_port not found in Fluent Bit config")

    if config.server_url is None and config.server_port is not None:
        config.server_url = f"{LOCALHOST_BASE}:{config.server_port}"
    if config.server_url is None:
        raise ValueError("server_url is not configured")

    logger.debug(msg="setting up OpAMP")
    client = OpAMPClient(config.server_url, config)

    client.launch_fluent_bit()
    client.add_fluentbit_version(config.http_port)

    logger.info("introducing self to server")
    asyncio.run(run_client(client))

    asyncio.run(client._heartbeat_loop(config.http_port))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
