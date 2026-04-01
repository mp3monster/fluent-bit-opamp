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
import pytest
from opamp_consumer.exceptions import AgentException
from opamp_consumer.proto import opamp_pb2


def test_send_as_is_skips_population(monkeypatch) -> None:
    """Send with send_as_is True should skip population."""
    instance = client.OpAMPClient("http://localhost")
    called = {"count": 0}

    def _populate(msg):
        called["count"] += 1
        return msg

    async def _fake_send_http(_msg):
        return None

    monkeypatch.setattr(instance, "_populate_agent_to_server", _populate)
    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    message = opamp_pb2.AgentToServer()
    asyncio.run(instance.send(message, send_as_is=True))
    assert called["count"] == 0


def test_send_websocket_error_falls_back_to_http(monkeypatch) -> None:
    """WebSocket transport errors should fall back to HTTP send."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.transport = "websocket"
    calls = {"ws": 0, "http": 0}

    async def _fake_send_websocket(_msg):
        calls["ws"] += 1
        raise RuntimeError("ws unavailable")

    async def _fake_send_http(_msg):
        calls["http"] += 1
        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = instance.data.uid_instance
        return reply

    monkeypatch.setattr(instance, "send_websocket", _fake_send_websocket)
    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    response = asyncio.run(instance.send(opamp_pb2.AgentToServer(), send_as_is=True))
    assert response is not None
    assert calls == {"ws": 1, "http": 1}


def test_send_returns_none_when_websocket_and_http_fail(monkeypatch, caplog) -> None:
    """Send should return None when both websocket and HTTP paths fail."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.transport = "websocket"
    caplog.set_level(logging.WARNING)

    async def _fake_send_websocket(_msg):
        raise RuntimeError("ws unavailable")

    async def _fake_send_http(_msg):
        raise RuntimeError("http unavailable")

    monkeypatch.setattr(instance, "send_websocket", _fake_send_websocket)
    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    response = asyncio.run(instance.send(opamp_pb2.AgentToServer(), send_as_is=True))
    assert response is None
    assert "Error sending websocket client-to-server message" in caplog.text
    assert "Error sending HTTP client-to-server message" in caplog.text


def test_get_config_value_missing_key_returns_empty_and_logs(caplog) -> None:
    """Missing config keys should return an empty string and log an error."""
    instance = client.OpAMPClient("http://localhost")
    caplog.set_level(logging.ERROR)

    value = instance._get_config_value("not_a_real_config_key")

    assert value == ""
    assert "Error handling request for not_a_real_config_key" in caplog.text


def test_handle_server_to_agent_invalid_reply_returns_false() -> None:
    """Invalid/malformed reply should be handled and return False."""
    instance = client.OpAMPClient("http://localhost")
    reply = opamp_pb2.ServerToAgent()

    assert instance._handle_server_to_agent(reply) is False


def test_populate_disconnect_sets_instance_uid() -> None:
    """Disconnect population should ensure instance UID and agent_disconnect."""
    instance = client.OpAMPClient("http://localhost")
    message = opamp_pb2.AgentToServer()
    instance._populate_disconnect(message)
    assert message.instance_uid == instance.data.uid_instance
    assert message.HasField("agent_disconnect")


def test_terminate_agent_process_terminates_only_launched_process(monkeypatch) -> None:
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

    monkeypatch.setattr(
        client.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess()
    )

    instance.launch_agent_process()
    assert instance.data.agent_process is not None

    instance.terminate_agent_process()
    assert called["terminate"] == 1
    assert called["wait"] == 1
    assert called["kill"] == 0
    assert instance.data.agent_process is None


def test_restart_agent_process_relaunches(monkeypatch) -> None:
    """Restart should terminate existing process and launch a new one."""
    instance = client.OpAMPClient("http://localhost")
    calls = {"terminate": 0, "launch": 0}

    def _terminate() -> None:
        calls["terminate"] += 1

    def _launch() -> bool:
        calls["launch"] += 1
        return True

    monkeypatch.setattr(instance, "terminate_agent_process", _terminate)
    monkeypatch.setattr(instance, "launch_agent_process", _launch)

    assert instance.restart_agent_process() is True
    assert calls["terminate"] == 1
    assert calls["launch"] == 1


def test_restart_agent_process_raises_on_failed_launch(monkeypatch) -> None:
    """Restart should raise AgentException when relaunch fails."""
    instance = client.OpAMPClient("http://localhost")

    monkeypatch.setattr(instance, "terminate_agent_process", lambda: None)
    monkeypatch.setattr(instance, "launch_agent_process", lambda: False)

    with pytest.raises(AgentException):
        instance.restart_agent_process()
