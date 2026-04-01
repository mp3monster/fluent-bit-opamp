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

from opamp_consumer.config import ConsumerConfig
from opamp_consumer.custom_handlers import build_factory_lookup, create_handler
from opamp_consumer.fluentbit_client import OpAMPClientData


def _make_client_data() -> OpAMPClientData:
    """Create a minimal OpAMPClientData instance for handler tests."""
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path="unused",
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=["ReportsStatus"],
        allow_custom_capabilities=True,
        log_level="debug",
    )
    return OpAMPClientData(
        config=config, base_url="http://localhost", uid_instance=b"id"
    )


def test_shutdowncommand_factory_creates_handler_by_fqdn() -> None:
    """Factory lookup should resolve the provider shutdown-agent custom command."""
    lookup = build_factory_lookup(
        "consumer/src/opamp_consumer/custom_handlers",
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    fqdn = "org.mp3monster.opamp_provider.command_shutdown_agent"
    assert fqdn in lookup

    instance = create_handler(
        fqdn,
        "consumer/src/opamp_consumer/custom_handlers",
        client_data=_make_client_data(),
        factory_lookup=lookup,
        allow_custom_capabilities=True,
    )
    assert instance is not None
    assert instance.get_reverse_fqdn() == fqdn
    assert instance.__class__.__name__ == "ShutdownCommand"
