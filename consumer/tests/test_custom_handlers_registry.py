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

from opamp_consumer.client import OpAMPClientData
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.custom_handlers import create_handler, discover_handlers
from opamp_consumer.exceptions import CommandException
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
    async def send(
        self,
        msg: opamp_pb2.AgentToServer | None = None,
        *,
        send_as_is: bool = False,
    ) -> opamp_pb2.ServerToAgent:
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


def test_registry_discovers_and_creates_handlers(tmp_path) -> None:
    """Discover handlers from a folder and instantiate by FQDN."""
    handler_code = '''
from opamp_consumer.custom_handlers.handler_interface import CustomMessageHandlerInterface

class SampleHandler(CustomMessageHandlerInterface):
    def __init__(self):
        self._data = None
    def set_client_data(self, data):
        self._data = data
    def get_fqdn(self):
        return "sample.handler"
    def handle_message(self, message, message_type):
        pass
    def execute_action(self, action, opamp_client):
        pass
'''
    handler_path = tmp_path / "sample_handler.py"
    handler_path.write_text(handler_code)

    registry = discover_handlers(
        tmp_path,
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    assert registry == {"sample.handler": "SampleHandler"}

    instance = create_handler(
        "sample.handler",
        tmp_path,
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    assert instance is not None
    assert instance.get_fqdn() == "sample.handler"
    assert instance._data is not None


def test_registry_ignores_missing_folder(tmp_path) -> None:
    """Return empty results when the handler folder is missing."""
    missing = tmp_path / "missing"
    registry = discover_handlers(
        missing,
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    assert registry == {}
    assert (
        create_handler(
            "sample.handler",
            missing,
            client_data=_make_client_data(),
            allow_custom_capabilities=True,
        )
        is None
    )


def test_registry_ignores_non_handler_classes(tmp_path) -> None:
    """Ignore classes that do not implement the handler interface."""
    handler_path = tmp_path / "not_handler.py"
    handler_path.write_text("\nclass NotAHandler:\n    pass\n")

    registry = discover_handlers(
        tmp_path,
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    assert registry == {}


def test_registry_skips_broken_module(tmp_path) -> None:
    """Skip modules that fail to import without raising."""
    handler_path = tmp_path / "broken.py"
    handler_path.write_text("raise RuntimeError('boom')\n")

    registry = discover_handlers(
        tmp_path,
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    assert registry == {}


def test_execute_returns_commandexception_on_handler_error(tmp_path) -> None:
    """execute should return CommandException when a handler raises."""
    handler_code = '''
from opamp_consumer.custom_handlers.handler_interface import CustomMessageHandlerInterface

class BrokenHandler(CustomMessageHandlerInterface):
    def __init__(self):
        super().__init__()
        self._data = None
    def set_client_data(self, data):
        self._data = data
    def get_fqdn(self):
        return "broken.handler"
    def handle_message(self, message, message_type):
        raise RuntimeError("boom")
    def execute_action(self, action, opamp_client):
        pass
'''
    handler_path = tmp_path / "broken_handler.py"
    handler_path.write_text(handler_code)
    instance = create_handler(
        "broken.handler",
        tmp_path,
        client_data=_make_client_data(),
        allow_custom_capabilities=True,
    )
    assert instance is not None

    payload = opamp_pb2.CustomMessage()
    payload.capability = "broken.handler"
    payload.type = "test"
    payload.data = b'{"action":"run"}'
    instance.set_custom_message_handler(payload)

    result = instance.execute(_FakeOpAMPClient())
    assert isinstance(result, CommandException)
