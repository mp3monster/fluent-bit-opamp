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

import logging

import opamp_consumer.client as client
from opamp_consumer.client import (
    CAPABILITIES_MAP,
    KEY_SERVICE_INSTANCE_ID,
    KEY_SERVICE_NAME,
    KEY_SERVICE_NAMESPACE,
    KEY_SERVICE_VERSION,
    KEY_FLUENTBIT_VERSION,
)
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.proto import opamp_pb2, anyvalue_pb2


def _set_config(agent_capabilities) -> None:
    config = ConsumerConfig(
        server_url="http://localhost",
        fluentbit_config_path="unused",
        additional_fluent_bit_params=[],
        heartbeat_frequency=30,
        agent_capabilities=agent_capabilities,
        log_level="debug",
        service_name="Fluentbit",
        service_namespace="FluentBitNS",
    )
    client.CONFIG = config


def test_get_agent_capabilities_from_names(caplog) -> None:
    _set_config(["ReportsStatus", "ReportsHealth", "ReportsHeartbeat"])
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost")

    mask = instance.get_agent_capabilities()

    expected = (
        CAPABILITIES_MAP["ReportsStatus"]
        | CAPABILITIES_MAP["ReportsHealth"]
        | CAPABILITIES_MAP["ReportsHeartbeat"]
    )
    assert mask == expected
    assert "unknown agent capability" not in caplog.text


def test_get_agent_capabilities_warns_unknown(caplog) -> None:
    _set_config(["ReportsStatus", "UnknownCapability"])
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost")

    mask = instance.get_agent_capabilities()

    assert mask == CAPABILITIES_MAP["ReportsStatus"]
    assert "unknown agent capability" in caplog.text


def test_get_agent_description_includes_config_and_version(monkeypatch) -> None:
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.last_heartbeat_results[KEY_FLUENTBIT_VERSION] = "3.0.0 (classic)"

    monkeypatch.setattr(
        instance,
        "get_host_metadata",
        lambda: {"os_type": "Linux", "os_version": "1", "hostname": "box"},
    )

    desc = instance.get_agent_description(b"\x01\x02")
    identifying = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in desc.identifying_attributes
    }
    non_identifying = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in desc.non_identifying_attributes
    }

    assert identifying[KEY_SERVICE_NAME] == "Fluentbit"
    assert identifying[KEY_SERVICE_NAMESPACE] == "FluentBitNS"
    assert identifying[KEY_SERVICE_INSTANCE_ID] == "0102"
    assert identifying[KEY_SERVICE_VERSION] == "3.0.0 (classic)"
    assert non_identifying == {
        "os_type": "Linux",
        "os_version": "1",
        "hostname": "box",
    }


def test_handle_error_response_logs(caplog) -> None:
    instance = client.OpAMPClient("http://localhost")
    caplog.set_level(logging.WARNING)

    error = opamp_pb2.ServerErrorResponse(
        type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
        error_message="boom",
        retry_info=opamp_pb2.RetryInfo(retry_after_nanoseconds=123),
    )
    instance.handle_error_response(error)

    assert "error_response" in caplog.text
    assert "boom" in caplog.text
