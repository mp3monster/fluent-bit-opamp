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
import pytest

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
from opamp_consumer.exceptions import AgentException
from opamp_consumer.proto import opamp_pb2, anyvalue_pb2


def _set_config(agent_capabilities) -> None:
    """Install a test config with the requested agent capabilities."""
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
    """Build a bitmask from named capabilities and ignore unknowns."""
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
    """Log a warning when unknown capability names are provided."""
    _set_config(["ReportsStatus", "UnknownCapability"])
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost")

    mask = instance.get_agent_capabilities()

    assert mask == CAPABILITIES_MAP["ReportsStatus"]
    assert "unknown agent capability" in caplog.text


def test_get_agent_description_includes_config_and_version(monkeypatch) -> None:
    """Include configured service info and Fluent Bit version in AgentDescription."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.last_heartbeat_results[KEY_FLUENTBIT_VERSION] = "3.0.0 (classic)"

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
    """Log server error response details including message and retry info."""
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


def test_send_as_is_skips_population(monkeypatch) -> None:
    """Send with send_as_is True should skip population."""
    instance = client.OpAMPClient("http://localhost")
    called = {"count": 0}

    def _populate(msg):
        called["count"] += 1
        return msg

    async def _fake_send_http(msg):
        return None

    monkeypatch.setattr(instance, "_populate_agent_to_server", _populate)
    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    msg = opamp_pb2.AgentToServer()
    import asyncio

    asyncio.run(instance.send(msg, send_as_is=True))
    assert called["count"] == 0


def test_populate_disconnect_sets_instance_uid() -> None:
    """Disconnect population should ensure instance UID and agent_disconnect."""
    instance = client.OpAMPClient("http://localhost")
    msg = opamp_pb2.AgentToServer()
    instance._populate_disconnect(msg)
    assert msg.instance_uid == instance.data.uid_instance
    assert msg.HasField("agent_disconnect")


def test_terminate_fluent_bit_terminates_only_launched_process(monkeypatch) -> None:
    """Terminate only the Fluent Bit process launched by the client."""
    instance = client.OpAMPClient("http://localhost")
    called = {"terminate": 0, "wait": 0, "kill": 0}

    class FakeProcess:
        def terminate(self) -> None:
            called["terminate"] += 1

        def wait(self, timeout: float | None = None) -> int:
            called["wait"] += 1
            return 0

        def kill(self) -> None:
            called["kill"] += 1

    monkeypatch.setattr(client.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())

    instance.launch_fluent_bit()
    assert instance.data.fluentbit_process is not None

    instance.terminate_fluent_bit()
    assert called["terminate"] == 1
    assert called["wait"] == 1
    assert called["kill"] == 0
    assert instance.data.fluentbit_process is None


def test_restart_agent_process_relaunches(monkeypatch) -> None:
    """Restart should terminate existing process and launch a new one."""
    instance = client.OpAMPClient("http://localhost")
    calls = {"terminate": 0, "launch": 0}

    def _terminate() -> None:
        calls["terminate"] += 1

    def _launch() -> bool:
        calls["launch"] += 1
        return True

    monkeypatch.setattr(instance, "terminate_fluent_bit", _terminate)
    monkeypatch.setattr(instance, "launch_fluent_bit", _launch)

    assert instance.restart_agent_process() is True
    assert calls["terminate"] == 1
    assert calls["launch"] == 1


def test_restart_agent_process_raises_on_failed_launch(monkeypatch) -> None:
    """Restart should raise AgentException when relaunch fails."""
    instance = client.OpAMPClient("http://localhost")

    monkeypatch.setattr(instance, "terminate_fluent_bit", lambda: None)
    monkeypatch.setattr(instance, "launch_fluent_bit", lambda: False)

    with pytest.raises(AgentException):
        instance.restart_agent_process()


def test_handle_command_restart_invokes_restart(monkeypatch) -> None:
    """Restart command should invoke restart_agent_process."""
    instance = client.OpAMPClient("http://localhost")
    calls = {"restart": 0}

    def _restart() -> bool:
        calls["restart"] += 1
        return True

    monkeypatch.setattr(instance, "restart_agent_process", _restart)
    command = opamp_pb2.ServerToAgentCommand(
        type=opamp_pb2.CommandType.CommandType_Restart
    )

    instance.handle_command(command)
    assert calls["restart"] == 1


def test_handle_command_unknown_raises_agent_exception() -> None:
    """Unknown command type should raise AgentException."""
    instance = client.OpAMPClient("http://localhost")
    command = opamp_pb2.ServerToAgentCommand()
    command.type = 999

    with pytest.raises(AgentException):
        instance.handle_command(command)
