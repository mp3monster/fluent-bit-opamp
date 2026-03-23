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

import opamp_consumer.client as client
from opamp_consumer.client import build_minimal_agent, load_fluentbit_config
from opamp_consumer.config import ConsumerConfig
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
        fluentbit_config_path=str(sample_path),
        additional_fluent_bit_params=[],
        heartbeat_frequency=30,
        agent_capabilities=0,
        log_level="debug",
    )
    client.CONFIG = config
    load_fluentbit_config(config)

    assert config.agent_description == "test-agent"
    assert config.service_instance_id == "abcdef1234567890"
    assert config.client_status_port == 2020
    assert config.fluentbit_http_port == 2020
    assert config.fluentbit_http_listen == "0.0.0.0"
    assert config.fluentbit_http_server == "On"
