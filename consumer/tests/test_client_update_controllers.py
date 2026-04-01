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

import asyncio
import logging

import opamp_consumer.fluentbit_client as client
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.full_update_controller import AlwaysSend, TimeSend
from opamp_consumer.proto import opamp_pb2


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


def test_sent_count_full_update_controller_sets_all_reporting_flags(monkeypatch) -> None:
    """SentCount should set all reporting flags after reaching fullResendAfter."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.config.full_update_controller = {"fullResendAfter": 1}
    instance.data.full_update_controller = client.SentCount(
        set_all_reporting_flags=instance.data.set_all_reporting_flags,
    )
    instance.data.full_update_controller.configure(instance.config.full_update_controller)
    instance.data.set_all_reporting_flags(False)

    async def _fake_send_http(_msg):
        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = instance.data.uid_instance
        return reply

    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    asyncio.run(instance.send(opamp_pb2.AgentToServer(), send_as_is=False))
    assert all(instance.data.reporting_flags.values())


def test_always_send_full_update_controller_sets_all_reporting_flags() -> None:
    """AlwaysSend should set all reporting flags on every update_sent call."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.full_update_controller = AlwaysSend(
        set_all_reporting_flags=instance.data.set_all_reporting_flags,
    )
    instance.data.set_all_reporting_flags(False)

    instance.data.full_update_controller.update_sent()

    assert all(instance.data.reporting_flags.values())


def test_time_send_full_update_controller_respects_time_window() -> None:
    """TimeSend should set all flags only after configured seconds have elapsed."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.full_update_controller = TimeSend(
        set_all_reporting_flags=instance.data.set_all_reporting_flags,
    )
    instance.data.full_update_controller.configure({"fullUpdateAfterSeconds": 2})
    instance.data.set_all_reporting_flags(False)

    instance.data.full_update_controller.update_sent(1000)
    assert not any(instance.data.reporting_flags.values())
    assert instance.data.full_update_controller.last_full_update_ms == 0

    instance.data.full_update_controller.update_sent(3001)
    assert all(instance.data.reporting_flags.values())
    assert instance.data.full_update_controller.last_full_update_ms == 3001


def test_client_uses_always_send_when_type_configured() -> None:
    """Instantiate AlwaysSend when full_update_controller_type is AlwaysSend."""
    _set_config(["ReportsStatus"])
    config = client.CONFIG
    config.full_update_controller_type = "AlwaysSend"
    instance = client.OpAMPClient("http://localhost", config)
    assert isinstance(instance.data.full_update_controller, AlwaysSend)


def test_client_uses_time_send_when_type_configured() -> None:
    """Instantiate TimeSend when full_update_controller_type is TimeSend."""
    _set_config(["ReportsStatus"])
    config = client.CONFIG
    config.full_update_controller_type = "TimeSend"
    config.full_update_controller = {"fullUpdateAfterSeconds": 2}
    instance = client.OpAMPClient("http://localhost", config)
    assert isinstance(instance.data.full_update_controller, TimeSend)


def test_client_defaults_to_sent_count_for_unknown_type(caplog) -> None:
    """Fallback to SentCount and warn for unknown controller types."""
    _set_config(["ReportsStatus"])
    config = client.CONFIG
    config.full_update_controller_type = "UnknownController"
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost", config)
    assert isinstance(instance.data.full_update_controller, client.SentCount)
    assert "Unknown full_update_controller_type" in caplog.text
