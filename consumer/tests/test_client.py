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
import json
import pytest

import opamp_consumer.client as client
from opamp_consumer.client import (
    CAPABILITIES_MAP,
    CONFIG_DOCS_URL,
    KEY_SERVICE_INSTANCE_ID,
    KEY_SERVICE_NAME,
    KEY_SERVICE_NAMESPACE,
    KEY_SERVICE_VERSION,
    KEY_FLUENTBIT_VERSION,
)
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.exceptions import AgentException
from opamp_consumer.full_update_controller import AlwaysSend, TimeSend
from opamp_consumer.proto import opamp_pb2, anyvalue_pb2


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


def test_get_agent_capabilities_from_names(caplog) -> None:
    """Return a bitmask built from the hardwired required capabilities."""
    _set_config(["ReportsStatus", "ReportsHealth", "ReportsHeartbeat"])
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost")

    mask = instance.get_agent_capabilities()

    expected = (
        CAPABILITIES_MAP["ReportsStatus"]
        | CAPABILITIES_MAP["AcceptsRestartCommand"]
        | CAPABILITIES_MAP["ReportsHealth"]
    )
    assert mask == expected
    assert "unknown agent capability" not in caplog.text


def test_get_agent_capabilities_warns_unknown(caplog) -> None:
    """Ignore config capability values and always return the required capability mask."""
    _set_config(["ReportsStatus", "UnknownCapability"])
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost")

    mask = instance.get_agent_capabilities()

    assert mask == (
        CAPABILITIES_MAP["ReportsStatus"]
        | CAPABILITIES_MAP["AcceptsRestartCommand"]
        | CAPABILITIES_MAP["ReportsHealth"]
    )
    assert "unknown agent capability" not in caplog.text


def test_get_config_parameters_includes_docs_url() -> None:
    """Return config parameters plus documentation URL reference."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")

    config_params = instance.get_config_parameters()

    assert config_params["server_url"] == "http://localhost"
    assert config_params["documentation_url"] == CONFIG_DOCS_URL


def test_reporting_flags_default_to_true() -> None:
    """OpAMPClientData should default all ReportingFlag values to True."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")

    assert instance.data.reporting_flags
    assert set(instance.data.reporting_flags.keys()) == set(
        client.ReportingFlag
    )
    assert all(instance.data.reporting_flags.values())


def test_reporting_flags_setall_updates_all_values() -> None:
    """set_all_reporting_flags should apply the given value to all reporting flags."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")

    instance.data.set_all_reporting_flags(False)
    assert all(value is False for value in instance.data.reporting_flags.values())

    instance.data.set_all_reporting_flags()
    assert all(value is True for value in instance.data.reporting_flags.values())


def test_reportingflag_setall_updates_all_values() -> None:
    """ReportingFlag.set_all_reporting_flags should update every flag entry in-place."""
    flags = {
        flag: True
        for flag in client.ReportingFlag
    }

    client.ReportingFlag.set_all_reporting_flags(flags, False)
    assert all(value is False for value in flags.values())


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

    import asyncio

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

    # First call at 1000ms should not trigger (0 + 2000 < 1000 is false).
    instance.data.full_update_controller.update_sent(1000)
    assert not any(instance.data.reporting_flags.values())
    assert instance.data.full_update_controller.last_full_update_ms == 0

    # Second call at 3001ms should trigger (0 + 2000 < 3001 is true).
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


def test_handle_flags_logs_names_and_sets_all_for_report_full_state(caplog) -> None:
    """handle_flags should decode names and set all flags when ReportFullState is present."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.set_all_flags(False)
    caplog.set_level(logging.INFO)

    instance.handle_flags(
        opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportFullState
        | opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportAvailableComponents
    )

    assert all(instance.data.reporting_flags.values())
    assert "ReportFullState" in caplog.text
    assert "ReportAvailableComponents" in caplog.text


def test_handle_flags_without_report_full_state_does_not_set_all() -> None:
    """handle_flags should not force-enable reporting flags without ReportFullState."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.set_all_flags(False)

    instance.handle_flags(
        opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportAvailableComponents
    )

    assert not any(instance.data.reporting_flags.values())


def test_main_help_prints_config_parameters_and_skips_client(monkeypatch, capsys) -> None:
    """`--help` should print config parameters and exit before creating OpAMPClient."""
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path="unused",
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=["ReportsStatus"],
        log_level="debug",
    )
    monkeypatch.setattr(client.consumer_config, "load_config_with_overrides", lambda **_: config)
    monkeypatch.setattr(client, "OpAMPClient", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OpAMPClient should not be created for --help")))
    monkeypatch.setattr(client.sys, "argv", ["client.py", "--help"])

    client.main()

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["server_url"] == "http://localhost"
    assert payload["documentation_url"] == CONFIG_DOCS_URL


def test_get_agent_description_includes_config_and_version(monkeypatch) -> None:
    """Include configured service info and assert reported service version name includes Fluent Bit."""
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
    assert "Fluent Bit" in identifying[KEY_SERVICE_VERSION]
    assert non_identifying == {
        "os_type": "Linux",
        "os_version": "1",
        "hostname": "box",
    }


def test_get_agent_description_resolves_service_instance_template(monkeypatch) -> None:
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.config.service_instance_id = "__hostname__-__IP__-__mac-ad__"
    instance.data.agent_version = "3.0.0"

    monkeypatch.setattr(client.socket, "gethostname", lambda: "agent-01")
    monkeypatch.setattr(client.socket, "gethostbyname", lambda _name: "10.0.1.2")
    monkeypatch.setattr(client.uuid, "getnode", lambda: 0xA1B2C3D4E5F6)

    desc = instance.get_agent_description()
    identifying = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in desc.identifying_attributes
    }

    assert (
        identifying[KEY_SERVICE_INSTANCE_ID]
        == "agent-01-10.0.1.2-a1:b2:c3:d4:e5:f6"
    )


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

    import asyncio

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

    import asyncio

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
    msg = opamp_pb2.AgentToServer()
    instance._populate_disconnect(msg)
    assert msg.instance_uid == instance.data.uid_instance
    assert msg.HasField("agent_disconnect")


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

    monkeypatch.setattr(client.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())

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

    monkeypatch.setattr(client, "create_handler", lambda *_args, **_kwargs: _FakeHandler())

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
    msg = opamp_pb2.AgentToServer()

    populated = instance._populate_agent_to_server(msg)

    assert populated.HasField("custom_capabilities")
    assert populated.custom_capabilities.capabilities == [
        "request:org.mp3monster.opamp_provider.chatopcommand",
        "request:org.mp3monster.opamp_provider.command_shutdown_agent",
    ]
