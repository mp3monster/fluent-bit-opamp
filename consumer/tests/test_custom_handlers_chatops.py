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
from opamp_consumer.custom_handlers.chatops_command import ChatOpsCommand
from opamp_consumer.fluentbit_client import OpAMPClientData
from opamp_consumer.opamp_client_interface import OpAMPClientInterface
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


class _FakeOpAMPClient(OpAMPClientInterface):
    def __init__(self) -> None:
        self.sent_messages: list[opamp_pb2.AgentToServer] = []

    async def send(
        self,
        msg: opamp_pb2.AgentToServer | None = None,
        *,
        send_as_is: bool = False,
    ) -> opamp_pb2.ServerToAgent:
        if msg is not None:
            self.sent_messages.append(msg)
        return opamp_pb2.ServerToAgent()

    async def send_disconnect(self) -> None:
        return None

    def launch_agent_process(self) -> bool:
        return True

    def terminate_agent_process(self) -> None:
        return None

    def restart_agent_process(self) -> bool:
        return True

    def handle_custom_message(self, custom_message: opamp_pb2.CustomMessage) -> None:
        return None

    def handle_custom_capabilities(
        self, custom_capabilities: opamp_pb2.CustomCapabilities
    ) -> None:
        return None

    def handle_connection_settings(
        self, connection_settings: opamp_pb2.ConnectionSettingsOffers
    ) -> None:
        return None

    def handle_packages_available(
        self, packages_available: opamp_pb2.PackagesAvailable
    ) -> None:
        return None

    def handle_remote_config(self, remote_config: opamp_pb2.AgentRemoteConfig) -> None:
        return None

    def poll_local_status_with_codes(
        self, port: int
    ) -> tuple[dict[str, str], dict[str, str]]:
        return {}, {}

    def add_agent_version(self, port: int) -> None:
        return None

    def get_agent_description(
        self, instance_uid: bytes | str | None = None
    ) -> opamp_pb2.AgentDescription:
        return opamp_pb2.AgentDescription()

    def get_agent_capabilities(self) -> int:
        return 0

    def finalize(self) -> None:
        return None


def test_chatops_command_logs(caplog, monkeypatch) -> None:
    """Verify ChatOpsCommand logs each stub method invocation."""
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        "opamp_consumer.custom_handlers.chatops_command.httpx.post",
        lambda *_args, **_kwargs: type("Resp", (), {"status_code": 200, "text": "ok"})(),
    )
    handler = ChatOpsCommand()
    handler.set_client_data(_make_client_data())
    handler.get_fqdn()
    handler.handle_message('{"tag":"trace","attributes":"{\\"a\\":\\"b\\"}"}', "text")
    handler.execute_action("run", _FakeOpAMPClient())

    assert "ChatOpsCommand.set_client_data called" in caplog.text
    assert "ChatOpsCommand.get_fqdn called" in caplog.text
    assert "ChatOpsCommand.handle_message called" in caplog.text
    assert "ChatOpsCommand.execute_action called" in caplog.text


def test_chatops_execute_logs_start_and_end(caplog, monkeypatch) -> None:
    """Execute should log start/end and return no error for valid payload."""
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        "opamp_consumer.custom_handlers.chatops_command.httpx.post",
        lambda *_args, **_kwargs: type("Resp", (), {"status_code": 200, "text": "ok"})(),
    )
    handler = ChatOpsCommand()
    handler.set_client_data(_make_client_data())
    payload = opamp_pb2.CustomMessage()
    payload.capability = handler.get_reverse_fqdn()
    payload.type = "by REST Call"
    payload.data = json.dumps({"action": "run"}).encode("utf-8")
    handler.set_custom_message_handler(payload)

    result = handler.execute(_FakeOpAMPClient())

    assert result is None
    assert "custom handler execute start" in caplog.text
    assert "custom handler execute end" in caplog.text


def test_chatops_execute_action_reports_failure_custom_message(monkeypatch) -> None:
    """Non-2xx local HTTP responses should return a failure custom message."""
    captured: dict[str, object] = {}

    def _fake_post(url, content=None, headers=None, timeout=None):  # noqa: ANN001
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout
        return type("Resp", (), {"status_code": 500, "text": 'bad "payload"\nline2'})()

    monkeypatch.setattr(
        "opamp_consumer.custom_handlers.chatops_command.httpx.post",
        _fake_post,
    )

    handler = ChatOpsCommand()
    handler.set_client_data(_make_client_data())
    handler.handle_message(
        '{"tag":"events","attributes":"{\\"service\\":\\"orders\\",\\"count\\":1}"}',
        "test",
    )
    fake_client = _FakeOpAMPClient()

    returned = handler.execute_action("run", fake_client)

    assert captured["url"] == "http://localhost:8888/events"
    assert json.loads(captured["content"].decode("utf-8")) == {
        "service": "orders",
        "count": 1,
    }
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["headers"]["Content-Length"] == str(len(captured["content"]))
    assert captured["timeout"] == 5.0
    assert len(fake_client.sent_messages) == 0
    assert returned is not None

    assert returned.capability == "org.mp3monster.opamp_provider.chatopcommand"
    assert returned.type == "failure"
    payload = json.loads(returned.data.decode("utf-8"))
    assert payload["http_code"] == "500"
    assert payload["err_msg"] == 'bad \\"payload\\"\\nline2'
