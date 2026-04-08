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

"""Default Fluent Bit OpAMP client implementation and program entrypoint."""

from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import uuid

from opamp_consumer import config as consumer_config
from opamp_consumer.abstract_client import (
    CAPABILITY_PREFIX_REQUEST,
    CONFIG_DOCS_URL,
    ERR_PREFIX,
    HOST_META_KEY_MAC_ADDRESS,
    HOST_META_KEY_HOSTNAME,
    HOST_META_KEY_OS_TYPE,
    HOST_META_KEY_OS_VERSION,
    KEY_FLUENTBIT_VERSION,
    KEY_HEALTH,
    KEY_SERVICE_INSTANCE_ID,
    KEY_SERVICE_INSTANCE_ID_COMMENT,
    KEY_SERVICE_NAME,
    KEY_SERVICE_NAMESPACE,
    KEY_SERVICE_TYPE,
    KEY_SERVICE_VERSION,
    LOCALHOST_BASE,
    TRANSPORT_HTTP,
    TRANSPORT_WEBSOCKET,
    VALUE_HEARTBEAT_STATUS,
    VALUE_SUPERVISOR_NO_STATE,
    AbstractOpAMPClient,
    OpAMPClientData,
    _config_parameters_payload,
)
from opamp_consumer.client_bootstrap import (
    build_minimal_agent as _bootstrap_build_minimal_agent,
)
from opamp_consumer.client_bootstrap import (
    load_agent_config as _bootstrap_load_agent_config,
)
from opamp_consumer.client_bootstrap import (
    resolve_service_instance_id_template_with_values,
    run_default_client_main,
)
from opamp_consumer.client_bootstrap import (
    run_client as _bootstrap_run_client,
)
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.custom_handlers import build_factory_lookup, create_handler  # noqa: F401
from opamp_consumer.full_update_controller import AlwaysSend, SentCount, TimeSend
from opamp_consumer.proto import opamp_pb2
from opamp_consumer.reporting_flag import ReportingFlag

CONFIG = consumer_config.CONFIG

__all__ = [
    "AbstractOpAMPClient",
    "CAPABILITY_PREFIX_REQUEST",
    "CONFIG_DOCS_URL",
    "ERR_PREFIX",
    "HOST_META_KEY_MAC_ADDRESS",
    "HOST_META_KEY_HOSTNAME",
    "HOST_META_KEY_OS_TYPE",
    "HOST_META_KEY_OS_VERSION",
    "KEY_FLUENTBIT_VERSION",
    "KEY_HEALTH",
    "KEY_SERVICE_INSTANCE_ID",
    "KEY_SERVICE_INSTANCE_ID_COMMENT",
    "KEY_SERVICE_NAME",
    "KEY_SERVICE_NAMESPACE",
    "KEY_SERVICE_TYPE",
    "KEY_SERVICE_VERSION",
    "LOCALHOST_BASE",
    "OpAMPClient",
    "OpAMPClientData",
    "AlwaysSend",
    "SentCount",
    "TimeSend",
    "ReportingFlag",
    "TRANSPORT_HTTP",
    "TRANSPORT_WEBSOCKET",
    "VALUE_HEARTBEAT_STATUS",
    "VALUE_SUPERVISOR_NO_STATE",
    "build_minimal_agent",
    "build_factory_lookup",
    "create_handler",
    "load_agent_config",
    "main",
    "resolve_service_instance_id_template",
    "run_client",
    "socket",
    "subprocess",
    "uuid",
]


class OpAMPClient(AbstractOpAMPClient):
    """Fluent Bit concrete client using shared runtime behavior.

    Why implementation-specific: this class sets Fluent Bit command/config/
    endpoint constants while reusing the shared abstract runtime behavior.
    """

    _runtime_agent_command = "fluent-bit"
    _runtime_config_flag = "-c"
    _heartbeat_paths = (
        "/api/v1/uptime",
        "/api/v1/health",
        "/api/v2/metrics/prometheus",
    )
    _key_agent_version = "fluent-bit.version"
    _key_agent_edition = "fluent-bit.edition"
    _json_key_agent = "fluent-bit"
    _json_key_agent_fallback = "fluentbit"
    _value_agent_type = "Fluent Bit"

    def get_custom_handler_folder(self) -> pathlib.Path:
        """Return the default handler folder used by the Fluent Bit client."""
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
    """Resolve service_instance_id tokens for Fluent Bit-style config comments.

    Why implementation-specific: Fluent Bit bootstrap comment parsing resolves
    service-instance templates from local host identity fields.
    """
    return resolve_service_instance_id_template_with_values(
        value=value,
        hostname=socket.gethostname(),
        ip_address=_get_local_ip(),
        mac_address=_get_local_mac(),
    )


def load_agent_config(config: ConsumerConfig) -> ConsumerConfig:
    """Load Fluent Bit agent config keys and metadata into the config object.

    Why implementation-specific: this uses the Fluent Bit HTTP/comment config
    conventions handled by the default bootstrap parser.
    """
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
    """Run the default Fluent Bit bootstrap flow.

    Why implementation-specific: Fluent Bit can use the shared bootstrap
    end-to-end because its config and heartbeat model match default behavior.
    """
    run_default_client_main(
        client_class=OpAMPClient,
        config_parameters_payload_builder=_config_parameters_payload,
        load_agent_config_fn=load_agent_config,
        localhost_base=LOCALHOST_BASE,
    )


if __name__ == "__main__":
    main()
    print("... Bye")
    sys.exit(1)
