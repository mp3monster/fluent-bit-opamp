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

import json
import logging

from opamp_consumer.config import ConsumerConfig
from opamp_consumer.custom_handlers import build_factory_lookup
from opamp_consumer.custom_handlers.nullcommand import NullCommand
from opamp_consumer.fluentbit_client import OpAMPClientData
from opamp_consumer.proto import opamp_pb2


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


def test_nullcommand_factory_discovery_includes_fqdn() -> None:
    """Factory lookup should discover the built-in nullcommand handler."""
    lookup = build_factory_lookup(
        "consumer/src/opamp_consumer/custom_handlers",
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    assert "org.mp3monster.opamp_provider.nullcommand" in lookup


def test_nullcommand_execute_logs_dummy_value(caplog) -> None:
    """Nullcommand execution should log the provided `dummyValue` string."""
    caplog.set_level(logging.INFO)
    handler = NullCommand()
    handler.set_client_data(_make_client_data())

    payload = opamp_pb2.CustomMessage()
    payload.capability = handler.get_reverse_fqdn()
    payload.type = "Null Command"
    payload.data = json.dumps(
        {"action": "nullcommand", "dummyValue": "log-me"}
    ).encode("utf-8")
    handler.set_custom_message_handler(payload)

    result = handler.execute(object())

    assert result is None
    assert "dummyValue=log-me" in caplog.text
