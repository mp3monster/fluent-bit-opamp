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

import opamp_consumer.fluentbit_client as client
import pytest
from opamp_consumer.exceptions import AgentException
from opamp_consumer.proto import opamp_pb2


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


def test_handle_custom_message_missing_capability_raises_agent_exception() -> None:
    """Missing capability on CustomMessage should raise AgentException."""
    instance = client.OpAMPClient("http://localhost")
    custom_message = opamp_pb2.CustomMessage()
    custom_message.type = "test"
    custom_message.data = b'{"action":"run"}'

    with pytest.raises(AgentException):
        instance.handle_custom_message(custom_message)


def test_handle_custom_message_execute_error_raises_agent_exception(monkeypatch) -> None:
    """A handler execute error should be converted to AgentException."""
    instance = client.OpAMPClient("http://localhost")

    class _FakeHandler:
        def set_custom_message_handler(self, _custom_message):
            return None

        def execute(self, _opamp_client):
            from opamp_consumer.exceptions import CommandException

            return CommandException("bad execute")

    monkeypatch.setattr(
        client, "create_handler", lambda *_args, **_kwargs: _FakeHandler()
    )

    custom_message = opamp_pb2.CustomMessage()
    custom_message.capability = "org.mp3monster.opamp_provider.chatopcommand"
    custom_message.type = "test"
    custom_message.data = b'{"action":"run"}'

    with pytest.raises(AgentException):
        instance.handle_custom_message(custom_message)


def test_get_custom_capabilities_payload_from_registry() -> None:
    """Build custom capability payload from registered custom handlers."""
    instance = client.OpAMPClient("http://localhost")
    instance._custom_handler_lookup = {
        "org.mp3monster.opamp_provider.command_shutdown_agent": object,
        "org.mp3monster.opamp_provider.chatopcommand": object,
        "": object,
    }

    payload = instance.get_custom_capabilities_payload()

    assert payload.capabilities == [
        "request:org.mp3monster.opamp_provider.chatopcommand",
        "request:org.mp3monster.opamp_provider.command_shutdown_agent",
    ]


def test_populate_agent_to_server_includes_custom_capabilities() -> None:
    """Populate AgentToServer with custom capabilities from handler registry."""
    instance = client.OpAMPClient("http://localhost")
    instance._custom_handler_lookup = {
        "org.mp3monster.opamp_provider.command_shutdown_agent": object,
        "org.mp3monster.opamp_provider.chatopcommand": object,
    }
    message = opamp_pb2.AgentToServer()

    populated = instance._populate_agent_to_server(message)

    assert populated.HasField("custom_capabilities")
    assert populated.custom_capabilities.capabilities == [
        "request:org.mp3monster.opamp_provider.chatopcommand",
        "request:org.mp3monster.opamp_provider.command_shutdown_agent",
    ]
