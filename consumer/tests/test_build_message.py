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

import opamp_consumer.fluentbit_client as client
import pytest
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.fluentbit_client import (
    build_minimal_agent,
    load_agent_config,
    resolve_service_instance_id_template,
)

from shared.opamp_config import UTF8_ENCODING


def test_build_minimal_agent() -> None:
    msg = build_minimal_agent(b"1234567890abcdef")
    assert msg.instance_uid == b"1234567890abcdef"


def test_load_agent_identity_from_fluentbit_config(tmp_path) -> None:
    sample_path = tmp_path / "fluent-bit.conf"
    sample_path.write_text(
        """
# agent_description = test-agent
# service_instance_id: abcdef1234567890
[SERVICE]
HTTP_Server On
HTTP_Listen 0.0.0.0
HTTP_Port 2020
[SERVICE]
Flush 1
""",
        encoding=UTF8_ENCODING,
    )
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path=str(sample_path),
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=0,
        log_level="debug",
    )
    client.CONFIG = config
    load_agent_config(config)

    assert config.agent_description == "test-agent"
    assert config.service_instance_id == "abcdef1234567890"
    assert config.client_status_port == 2020
    assert config.agent_http_port == 2020
    assert config.agent_http_listen == "0.0.0.0"
    assert config.agent_http_server == "On"


def test_resolve_service_instance_id_template_tokens(monkeypatch) -> None:
    monkeypatch.setattr(client.socket, "gethostname", lambda: "agent-host")
    monkeypatch.setattr(client.socket, "gethostbyname", lambda _name: "10.2.3.4")
    monkeypatch.setattr(client.uuid, "getnode", lambda: 0xAABBCCDDEEFF)

    resolved = resolve_service_instance_id_template(
        "node-__hostname__-__IP__-__mac-ad__"
    )

    assert resolved == "node-agent-host-10.2.3.4-aa:bb:cc:dd:ee:ff"


def test_load_agent_identity_resolves_template_tokens(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(client.socket, "gethostname", lambda: "edge-01")
    monkeypatch.setattr(client.socket, "gethostbyname", lambda _name: "192.168.10.5")
    monkeypatch.setattr(client.uuid, "getnode", lambda: 0x001122334455)
    sample_path = tmp_path / "fluent-bit.conf"
    sample_path.write_text(
        """
# service_instance_id: __hostname__-__IP__-__mac-ad__
[SERVICE]
HTTP_Server On
HTTP_Listen 0.0.0.0
HTTP_Port 2020
""",
        encoding=UTF8_ENCODING,
    )
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path=str(sample_path),
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=0,
        log_level="debug",
    )

    load_agent_config(config)

    assert config.service_instance_id == "edge-01-192.168.10.5-00:11:22:33:44:55"


def test_load_agent_config_raises_when_path_missing() -> None:
    """Missing agent_config_path should raise ValueError."""
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path=None,
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=0,
        log_level="debug",
    )

    with pytest.raises(ValueError):
        load_agent_config(config)


def test_load_agent_config_raises_on_invalid_http_port(tmp_path) -> None:
    """Invalid HTTP_Port values should raise ValueError during parsing."""
    sample_path = tmp_path / "fluent-bit-invalid.conf"
    sample_path.write_text(
        """
[SERVICE]
HTTP_Server On
HTTP_Listen 0.0.0.0
HTTP_Port not_a_number
""",
        encoding=UTF8_ENCODING,
    )
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path=str(sample_path),
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=0,
        log_level="debug",
    )

    with pytest.raises(ValueError):
        load_agent_config(config)
