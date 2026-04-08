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

import opamp_consumer.abstract_client as abstract_client
import opamp_consumer.fluentbit_client as client
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.fluentbit_client import (
    HOST_META_KEY_HOSTNAME,
    HOST_META_KEY_MAC_ADDRESS,
    HOST_META_KEY_OS_TYPE,
    HOST_META_KEY_OS_VERSION,
    KEY_FLUENTBIT_VERSION,
    KEY_SERVICE_INSTANCE_ID,
    KEY_SERVICE_NAME,
    KEY_SERVICE_NAMESPACE,
    KEY_SERVICE_VERSION,
)


def _set_config(agent_capabilities) -> None:
    """Install a test config with the requested agent capabilities."""
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path="unused",
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=agent_capabilities,
        log_level="debug",
        service_name="Fluentbit",
        service_namespace="FluentBitNS",
    )
    client.CONFIG = config


def test_get_agent_description_includes_config_and_version(monkeypatch) -> None:
    """Include configured service info and assert version name includes Fluent Bit."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.last_heartbeat_results[KEY_FLUENTBIT_VERSION] = "3.0.0 (classic)"

    monkeypatch.setattr(
        instance,
        "get_host_metadata",
        lambda: {"os_type": "Linux", "os_version": "1", "hostname": "box"},
    )

    description = instance.get_agent_description(b"\x01\x02")
    identifying = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in description.identifying_attributes
    }
    non_identifying = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in description.non_identifying_attributes
    }

    assert identifying[KEY_SERVICE_NAME] == "Fluentbit"
    assert identifying[KEY_SERVICE_NAMESPACE] == "FluentBitNS"
    assert identifying[KEY_SERVICE_INSTANCE_ID] == "0102"
    assert "Fluent Bit" in identifying[KEY_SERVICE_VERSION]
    assert non_identifying == {
        "os_type": "Linux",
        "os_version": "1",
        "hostname": "box",
    }


def test_get_agent_description_resolves_service_instance_template(monkeypatch) -> None:
    """Resolve service instance template placeholders in agent description."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.config.service_instance_id = "__hostname__-__IP__-__mac-ad__"
    instance.data.agent_version = "3.0.0"

    monkeypatch.setattr(client.socket, "gethostname", lambda: "agent-01")
    monkeypatch.setattr(client.socket, "gethostbyname", lambda _name: "10.0.1.2")
    monkeypatch.setattr(client.uuid, "getnode", lambda: 0xA1B2C3D4E5F6)

    description = instance.get_agent_description()
    identifying = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in description.identifying_attributes
    }

    assert (
        identifying[KEY_SERVICE_INSTANCE_ID]
        == "agent-01-10.0.1.2-a1:b2:c3:d4:e5:f6"
    )


def test_get_host_metadata_includes_mac_address(monkeypatch) -> None:
    """Host metadata should include OS, hostname, and normalized MAC address."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")

    monkeypatch.setattr(abstract_client.platform, "system", lambda: "Linux")
    monkeypatch.setattr(abstract_client.platform, "version", lambda: "1.2.3")
    monkeypatch.setattr(abstract_client.socket, "gethostname", lambda: "edge-02")
    monkeypatch.setattr(abstract_client.uuid, "getnode", lambda: 0xAABBCCDDEEFF)

    metadata = instance.get_host_metadata()

    assert metadata == {
        HOST_META_KEY_OS_TYPE: "Linux",
        HOST_META_KEY_OS_VERSION: "1.2.3",
        HOST_META_KEY_HOSTNAME: "edge-02",
        HOST_META_KEY_MAC_ADDRESS: "aa:bb:cc:dd:ee:ff",
    }
