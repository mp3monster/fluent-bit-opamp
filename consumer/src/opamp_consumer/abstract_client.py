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

"""Shared abstract OpAMP client implementation and runtime data model."""

from __future__ import annotations

import logging
import os
import pathlib
import platform
import socket
import subprocess
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

import httpx

from opamp_consumer import config as consumer_config
from opamp_consumer.client_bootstrap import resolve_service_instance_id_template_with_values
from opamp_consumer.client_message_builder import (
    parse_fluentbit_metrics_health,
    populate_agent_to_server,
    populate_agent_to_server_health,
)
from opamp_consumer.client_mixins import ClientRuntimeMixin, ServerMessageHandlingMixin
from opamp_consumer.client_transport import (
    send_http_message,
    send_websocket_message,
)
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.custom_handlers import build_factory_lookup, create_handler  # noqa: F401
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
    OPAMP_HTTP_PATH,
    AgentCapabilities,
    parse_capabilities,
)
from shared.uuid_utils import generate_uuid7_bytes

TRANSPORT_HTTP = "http"  # Transport selector for HTTP polling mode.
TRANSPORT_WEBSOCKET = "websocket"  # Transport selector for WebSocket mode.
LOCALHOST_BASE = "http://localhost"  # Base URL for local agent endpoints.
ERR_PREFIX = "error: "  # Prefix for error values stored in results.
KEY_FLUENTBIT_VERSION = "fluentbit_version"  # Result key for version response.
KEY_SERVICE_INSTANCE_ID_COMMENT = "service_instance_id"  # Comment key for service instance ID.
KEY_SERVICE_NAME = "service.name"  # Agent description service name key.
KEY_SERVICE_NAMESPACE = "service.namespace"  # Agent description service namespace key.
KEY_SERVICE_INSTANCE_ID = "service.instance.id"  # Agent description instance id key.
KEY_SERVICE_TYPE = "service.type"  # Agent description service type key.
KEY_SERVICE_VERSION = "service.version"  # Agent description version key.
KEY_HEALTH = "health"  # Heartbeat dictionary key for health endpoint results.
VALUE_HEARTBEAT_STATUS = "heartbeat"  # Health status value used in heartbeats.
VALUE_SUPERVISOR_NO_STATE = "Supervisor has not state"  # Error message when no heartbeat data.
CAPABILITY_PREFIX_REQUEST = "request:"  # Prefix used for custom request capability FQDN.
HOST_META_KEY_OS_TYPE = "os_type"  # Host metadata key for OS type.
HOST_META_KEY_OS_VERSION = "os_version"  # Host metadata key for OS version.
HOST_META_KEY_HOSTNAME = "hostname"  # Host metadata key for hostname.
CONFIG_DOCS_URL = (
    "https://github.com/mp3monster/fluent-opamp"  # Reference docs for consumer config.
)
ENV_OPAMP_TOKEN = "OpAMP-token"  # Requested env var name for outbound OpAMP token.
HEADER_AUTHORIZATION = "Authorization"  # HTTP/WebSocket header key for provider auth token.
AUTH_RETRY_STATUS_CODES = {401, 403}  # Status codes that trigger IDP credential renegotiation.


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
            config = globals().get("CONFIG")
        if config is None:
            try:
                from opamp_consumer import fluentbit_client as client_module

                config = getattr(client_module, "CONFIG", None)
            except Exception:  # pragma: no cover - defensive import fallback
                config = None
        if config is None:
            config = consumer_config.CONFIG
        if config is None:
            logging.getLogger(__name__).warning("No config supplied to OpAMPClient")
            raise ValueError("OpAMP client requires a consumer config")

        self.data = OpAMPClientData(
            config=config,
            base_url=base_url.rstrip("/"),
        )
        self.data.full_update_controller = self._create_full_update_controller()
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
        authorization_header = await self._resolve_authorization_header_value()
        try:
            return await send_http_message(
                msg=msg,
                base_url=self.data.base_url,
                opamp_http_path=OPAMP_HTTP_PATH,
                handle_reply=self._handle_server_to_agent,
                authorization_header=authorization_header,
            )
        except Exception as err:
            if not self._should_retry_idp_authorization(err):
                raise
            logging.getLogger(__name__).info(
                "HTTP auth failure detected; renegotiating IDP token and retrying request"
            )
            authorization_header = await self._resolve_authorization_header_value(
                force_refresh=True
            )
            return await send_http_message(
                msg=msg,
                base_url=self.data.base_url,
                opamp_http_path=OPAMP_HTTP_PATH,
                handle_reply=self._handle_server_to_agent,
                authorization_header=authorization_header,
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

    async def send_websocket(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via WebSocket and return the response.

        Args:
            msg: Populated AgentToServer payload to send.

        Returns:
            Parsed ServerToAgent reply from the provider.
        """
        authorization_header = await self._resolve_authorization_header_value()
        try:
            return await send_websocket_message(
                msg=msg,
                base_url=self.data.base_url,
                opamp_http_path=OPAMP_HTTP_PATH,
                handle_reply=self._handle_server_to_agent,
                authorization_header=authorization_header,
            )
        except Exception as err:
            if not self._should_retry_idp_authorization(err):
                raise
            logging.getLogger(__name__).info(
                "WebSocket auth failure detected; renegotiating IDP token and retrying request"
            )
            authorization_header = await self._resolve_authorization_header_value(
                force_refresh=True
            )
            return await send_websocket_message(
                msg=msg,
                base_url=self.data.base_url,
                opamp_http_path=OPAMP_HTTP_PATH,
                handle_reply=self._handle_server_to_agent,
                authorization_header=authorization_header,
            )

    def _server_authorization_mode(self) -> str:
        """Return normalized configured server authorization mode."""
        raw_mode = str(
            self.config.server_authorization or consumer_config.DEFAULT_SERVER_AUTHORIZATION
        ).strip().lower()
        if raw_mode in (
            consumer_config.SERVER_AUTHORIZATION_NONE,
            consumer_config.SERVER_AUTHORIZATION_ENV_VAR,
            consumer_config.SERVER_AUTHORIZATION_CONFIG_VAR,
            consumer_config.SERVER_AUTHORIZATION_IDP,
        ):
            return raw_mode
        return consumer_config.DEFAULT_SERVER_AUTHORIZATION

    def _record_authorization_header(
        self,
        *,
        header_name: str,
        header_value: str | None,
    ) -> None:
        """Persist active outbound authorization header details onto client config."""
        self.config.server_authorization_header_name = str(header_name or HEADER_AUTHORIZATION)
        self.config.server_authorization_header_value = (
            str(header_value).strip() if header_value else None
        )

    def _status_code_from_exception(self, err: Exception) -> int | None:
        """Extract HTTP status code from transport-layer exceptions when available."""
        direct_status = getattr(err, "status_code", None)
        if isinstance(direct_status, int):
            return direct_status
        response = getattr(err, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    def _should_retry_idp_authorization(self, err: Exception) -> bool:
        """Return True when IDP mode should renegotiate credentials and retry once."""
        if self._server_authorization_mode() != consumer_config.SERVER_AUTHORIZATION_IDP:
            return False
        status_code = self._status_code_from_exception(err)
        return status_code in AUTH_RETRY_STATUS_CODES

    def _normalize_header_value(self, raw_value: str) -> str:
        """Normalize raw token/header value into a bearer Authorization header value."""
        value = str(raw_value or "").strip()
        if not value:
            raise ValueError("authorization token value is empty")
        if value.lower().startswith("bearer "):
            return value
        return f"Bearer {value}"

    def _token_from_env(self) -> str:
        """Resolve outbound OpAMP token from environment."""
        token = os.environ.get(ENV_OPAMP_TOKEN) or ""
        token = str(token).strip()
        if not token:
            raise ValueError(
                "consumer.server-authorization=env-var but no token is set in OpAMP-token"
            )
        return token

    async def _refresh_idp_authorization_header(self) -> str:
        """Obtain fresh bearer credentials from the configured IdP token endpoint."""
        token_url = str(self.config.idp_token_url or "").strip()
        if not token_url:
            raise ValueError(
                "consumer.server-authorization=idp requires consumer.idp-token-url"
            )
        client_id = str(self.config.idp_client_id or "").strip()
        client_secret = str(self.config.idp_client_secret or "").strip()
        if not client_id or not client_secret:
            raise ValueError(
                "consumer.server-authorization=idp requires consumer.idp-client-id and "
                "consumer.idp-client-secret"
            )
        grant_type = str(
            self.config.idp_grant_type or consumer_config.DEFAULT_IDP_GRANT_TYPE
        ).strip()
        scope = str(self.config.idp_scope or "").strip()
        form_payload = {
            "grant_type": grant_type or consumer_config.DEFAULT_IDP_GRANT_TYPE,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scope:
            form_payload["scope"] = scope
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(token_url, data=form_payload)
            response.raise_for_status()
            payload = response.json()
        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            raise ValueError("idp token response missing access_token")
        token_type = str(payload.get("token_type", "Bearer")).strip() or "Bearer"
        header_value = (
            f"{token_type} {access_token}"
            if not access_token.lower().startswith("bearer ")
            else access_token
        )
        self._record_authorization_header(
            header_name=HEADER_AUTHORIZATION,
            header_value=header_value,
        )
        return header_value

    async def _resolve_authorization_header_value(
        self,
        *,
        force_refresh: bool = False,
    ) -> str | None:
        """Return outbound Authorization header value for configured mode."""
        mode = self._server_authorization_mode()
        if mode == consumer_config.SERVER_AUTHORIZATION_NONE:
            self._record_authorization_header(
                header_name=HEADER_AUTHORIZATION,
                header_value=None,
            )
            return None

        if mode == consumer_config.SERVER_AUTHORIZATION_ENV_VAR:
            header_value = self._normalize_header_value(self._token_from_env())
            self._record_authorization_header(
                header_name=HEADER_AUTHORIZATION,
                header_value=header_value,
            )
            return header_value

        if mode == consumer_config.SERVER_AUTHORIZATION_CONFIG_VAR:
            token = str(self.config.opamp_token or "").strip()
            if not token:
                raise ValueError(
                    "consumer.server-authorization=config-var requires consumer.OpAMP-token"
                )
            header_value = self._normalize_header_value(token)
            self._record_authorization_header(
                header_name=HEADER_AUTHORIZATION,
                header_value=header_value,
            )
            return header_value

        if mode == consumer_config.SERVER_AUTHORIZATION_IDP:
            cached_value = str(self.config.server_authorization_header_value or "").strip()
            if cached_value and not force_refresh:
                self._record_authorization_header(
                    header_name=HEADER_AUTHORIZATION,
                    header_value=cached_value,
                )
                return cached_value
            return await self._refresh_idp_authorization_header()

        self._record_authorization_header(
            header_name=HEADER_AUTHORIZATION,
            header_value=None,
        )
        return None

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
