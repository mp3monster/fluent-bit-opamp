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

from dataclasses import asdict, dataclass, field
from abc import ABC, abstractmethod
import sys
import logging
import pathlib
import platform
import socket
import subprocess
import threading
import asyncio
import uuid


from opamp_consumer import config as consumer_config
from opamp_consumer.client_bootstrap import (
    build_minimal_agent as _bootstrap_build_minimal_agent,
    load_agent_config as _bootstrap_load_agent_config,
    resolve_service_instance_id_template_with_values,
    run_client as _bootstrap_run_client,
    run_default_client_main,
)
from opamp_consumer.client_mixins import ClientRuntimeMixin, ServerMessageHandlingMixin
from opamp_consumer.client_message_builder import (
    parse_fluentbit_metrics_health,
    populate_agent_to_server,
    populate_agent_to_server_health,
)
from opamp_consumer.client_transport import (
    send_http_message,
    send_websocket_message,
)
from opamp_consumer.config import CFG_AGENT_CONFIG_PATH, ConsumerConfig
from opamp_consumer.custom_handlers import build_factory_lookup, create_handler
from opamp_consumer.full_update_controller import (
    AlwaysSend,
    FullUpdateControllerInterface,
    SentCount,
    TimeSend,
)
from opamp_consumer.opamp_client_interface import OpAMPClientInterface
from opamp_consumer.proto import anyvalue_pb2, opamp_pb2
from opamp_consumer.reporting_flag import ReportingFlag
from shared.opamp_config import (
    AGENT_CAPABILITIES_MAP,
    AgentCapabilities,
    OPAMP_HTTP_PATH,
    parse_capabilities,
)
from shared.uuid_utils import generate_uuid7_bytes


TRANSPORT_HTTP = "http"
TRANSPORT_WEBSOCKET = "websocket"
LOCALHOST_BASE = "http://localhost"  # Base URL for local Fluent Bit endpoints.
ERR_PREFIX = "error: "  # Prefix for error values stored in results.
KEY_FLUENTBIT_VERSION = "fluentbit_version"  # Result key for version response.
KEY_SERVICE_INSTANCE_ID_COMMENT = (
    "service_instance_id"  # Comment key for service instance ID.
)
KEY_SERVICE_NAME = "service.name"  # Agent description service name key.
KEY_SERVICE_NAMESPACE = "service.namespace"  # Agent description service namespace key.
KEY_SERVICE_INSTANCE_ID = "service.instance.id"  # Agent description instance id key.
KEY_SERVICE_TYPE = "service.type"  # Agent description service type key.
KEY_SERVICE_VERSION = "service.version"  # Agent description version key.
KEY_HEALTH = "health"  # Heartbeat dictionary key for health endpoint results.
VALUE_HEARTBEAT_STATUS = "heartbeat"  # Health status value used in heartbeats.
VALUE_SUPERVISOR_NO_STATE = (
    "Supervisor has not state"  # Error message when no heartbeat data.
)
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
CONFIG_DOCS_URL = (
    "https://github.com/mp3monster/fluent-opamp"  # Reference docs for consumer config.
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
        default_factory=lambda: {flag: True for flag in ReportingFlag}
    )
    full_update_controller: FullUpdateControllerInterface | None = None

    def set_all_reporting_flags(self, value: bool = True) -> None:
        """Set every reporting flag value to the provided boolean.

        Args:
            value: Boolean value assigned to all reporting flags.
        """
        ReportingFlag.set_all_reporting_flags(self.reporting_flags, value)

    def set_all_flags(self, value: bool = True) -> None:
        """Backward-compatible alias to set all reporting flags."""
        self.set_all_reporting_flags(value)

    @property
    def FullUpdateController(self) -> FullUpdateControllerInterface | None:
        """Backward-compatible alias for full update controller object."""
        return self.full_update_controller

    @FullUpdateController.setter
    def FullUpdateController(self, value: FullUpdateControllerInterface | None) -> None:
        """Backward-compatible alias setter for full update controller object."""
        self.full_update_controller = value


class AbstractOpAMPClient(
    ClientRuntimeMixin, ServerMessageHandlingMixin, OpAMPClientInterface, ABC
):
    """Abstract OpAMP client base for HTTP/WebSocket-capable implementations.

    This class provides the full `OpAMPClientInterface` behavior and leaves
    environment-specific custom-handler discovery to concrete subclasses.
    """

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
        self.data.FullUpdateController = self._create_full_update_controller()
        self._custom_handler_folder = self.get_custom_handler_folder()
        self._custom_handler_lookup = build_factory_lookup(
            self._custom_handler_folder,
            client_data=self.data,
            allow_custom_capabilities=bool(self.config.allow_custom_capabilities),
        )

    @abstractmethod
    def get_custom_handler_folder(self) -> pathlib.Path:
        """Return the folder path containing custom handler implementations."""

    def _create_full_update_controller(self) -> FullUpdateControllerInterface:
        """Build a configured full update controller instance for this client."""
        controller_type = str(
            self.config.full_update_controller_type or "SentCount"
        ).strip()
        normalized_type = controller_type.lower()
        if normalized_type == "alwayssend":
            controller = AlwaysSend(
                set_all_reporting_flags=self.data.set_all_reporting_flags,
            )
        elif normalized_type == "timesend":
            controller = TimeSend(
                set_all_reporting_flags=self.data.set_all_reporting_flags,
            )
        else:
            if normalized_type != "sentcount":
                logging.getLogger(__name__).warning(
                    "Unknown full_update_controller_type=%s; defaulting to SentCount",
                    controller_type,
                )
            controller = SentCount(
                set_all_reporting_flags=self.data.set_all_reporting_flags,
            )
        controller.configure(self.config.full_update_controller)
        return controller

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
        value = getattr(self.data.config, key, None)
        if value is None:
            logging.getLogger(__name__).error(
                "Error handling request for %s",
                key,
            )
            return ""
        return str(value)

    async def send_http(self, msg: opamp_pb2.AgentToServer) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via HTTP and return the response.

        Args:
            msg: Populated AgentToServer payload to send.

        Returns:
            Parsed ServerToAgent reply from the provider.
        """
        return await send_http_message(
            msg=msg,
            base_url=self.data.base_url,
            opamp_http_path=OPAMP_HTTP_PATH,
            handle_reply=self._handle_server_to_agent,
        )

    def _populate_agent_to_server_health(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.AgentToServer:
        """Populate health fields on AgentToServer using latest heartbeat poll state.

        Args:
            msg: Outbound AgentToServer message being assembled.

        Returns:
            The same message instance with health fields updated.
        """
        return populate_agent_to_server_health(
            data=self.data,
            msg=msg,
            health_from_metrics=self._health_from_metrics,
            health_key=KEY_HEALTH,
            err_prefix=ERR_PREFIX,
            value_heartbeat_status=VALUE_HEARTBEAT_STATUS,
            value_supervisor_no_state=VALUE_SUPERVISOR_NO_STATE,
        )

    def _health_from_metrics(self, msg, text) -> opamp_pb2.AgentToServer:
        """Parse Fluent Bit metrics text and update component health entries in-place.

        Args:
            msg: AgentToServer message whose health map is updated.
            text: Metrics response text to parse.

        Returns:
            The same message instance with component health updates applied.
        """
        return parse_fluentbit_metrics_health(msg, text)

    def _populate_agent_to_server(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.AgentToServer:
        """Fill outbound AgentToServer payload with description, caps, IDs, and health.

        Args:
            msg: Base AgentToServer message to populate.

        Returns:
            Populated AgentToServer message ready to send.
        """
        return populate_agent_to_server(
            data=self.data,
            msg=msg,
            get_agent_description=self.get_agent_description,
            get_agent_capabilities=self.get_agent_capabilities,
            get_custom_capabilities_payload=self.get_custom_capabilities_payload,
            populate_agent_to_server_health=self._populate_agent_to_server_health,
        )

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
        response: opamp_pb2.ServerToAgent | None = None
        transport = (self.config.transport or TRANSPORT_HTTP).strip().lower()
        if transport == TRANSPORT_WEBSOCKET:
            try:
                response = await self.send_websocket(msg)
            except Exception as err:
                logging.getLogger(__name__).warning(
                    "Error sending websocket client-to-server message -- %s", err
                )
        if response is not None:
            if not send_as_is and self.data.full_update_controller is not None:
                self.data.full_update_controller.update_sent()
            return response

        try:
            response = await self.send_http(msg)
            if not send_as_is and self.data.full_update_controller is not None:
                self.data.full_update_controller.update_sent()
            return response
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
        except Exception as err:
            logging.getLogger(__name__).warning(
                "Failed to send disconnect message - %s", err
            )

    async def _send_disconnect_with_timeout(self, timeout_seconds: float = 1.0) -> None:
        """Best-effort disconnect send with a short timeout.

        Args:
            timeout_seconds: Maximum wait time for sending disconnect.
        """
        try:
            logging.getLogger(__name__).warning("_send_disconnect_with_timeout exiting")
            await asyncio.wait_for(self.send_disconnect(), timeout=timeout_seconds)
        except Exception as err:
            logging.getLogger(__name__).error("Disconnect send timed out-- %s", err)

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
        return await send_websocket_message(
            msg=msg,
            base_url=self.data.base_url,
            opamp_http_path=OPAMP_HTTP_PATH,
            handle_reply=self._handle_server_to_agent,
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


class OpAMPClient(AbstractOpAMPClient):
    """Default concrete OpAMP client implementation."""

    def get_custom_handler_folder(self) -> pathlib.Path:
        """Return the default custom-handler folder bundled with the consumer."""
        return pathlib.Path(__file__).resolve().parent / "custom_handlers"


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
    return resolve_service_instance_id_template_with_values(
        value=value,
        hostname=socket.gethostname(),
        ip_address=_get_local_ip(),
        mac_address=_get_local_mac(),
    )


def load_agent_config(config: consumer_config.ConsumerConfig) -> ConsumerConfig:
    """Load Fluent Bit config values and agent metadata into the config object."""
    return _bootstrap_load_agent_config(
        config,
        resolve_service_instance_id_template_fn=resolve_service_instance_id_template,
    )


def build_minimal_agent(
    instance_uid: bytes | None = None,
    capabilities: int | None = None,
) -> opamp_pb2.AgentToServer:
    """Create a minimal AgentToServer message with configured capabilities."""
    return _bootstrap_build_minimal_agent(
        instance_uid=instance_uid,
        capabilities=capabilities,
    )


async def run_client(client) -> None:
    """Trigger a single send cycle for the provided client instance."""
    await _bootstrap_run_client(client)


def main() -> None:
    """Load config, start Fluent Bit client runtime, and run heartbeat loop."""
    run_default_client_main(
        client_class=OpAMPClient,
        config_parameters_payload_builder=_config_parameters_payload,
        load_agent_config_fn=load_agent_config,
        localhost_base=LOCALHOST_BASE,
    )


if __name__ == "__main__":
    main()
    print("... Bye")
    # _force_exit_on_lingering_threads()
    sys.exit(1)
