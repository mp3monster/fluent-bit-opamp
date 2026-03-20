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

from opamp_consumer.client import OpAMPClientData
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.custom_handlers import (
    ChatOpsCommand,
    build_factory_lookup,
    create_handler,
    discover_handlers,
)
from opamp_consumer.exceptions import CommandException
from opamp_consumer.proto import opamp_pb2


def _make_client_data() -> OpAMPClientData:
    """Create a minimal OpAMPClientData instance for handler tests."""
    config = ConsumerConfig(
        server_url="http://localhost",
        fluentbit_config_path="unused",
        additional_fluent_bit_params=[],
        heartbeat_frequency=30,
        agent_capabilities=["ReportsStatus"],
        log_level="debug",
    )
    return OpAMPClientData(config=config, base_url="http://localhost", uid_instance=b"id")


def test_chatops_command_logs(caplog) -> None:
    """Verify ChatOpsCommand logs each stub method invocation."""
    caplog.set_level(logging.INFO)
    handler = ChatOpsCommand()
    handler.set_client_data(_make_client_data())
    handler.get_fqdn()
    handler.handle_message("hello", "text")
    handler.execute_action("run")

    assert "ChatOpsCommand.set_client_data called" in caplog.text
    assert "ChatOpsCommand.get_fqdn called" in caplog.text
    assert "ChatOpsCommand.handle_message called" in caplog.text
    assert "ChatOpsCommand.execute_action called" in caplog.text


def test_chatops_execute_logs_start_and_end(caplog) -> None:
    """Execute should log start/end and return no error for valid payload."""
    caplog.set_level(logging.INFO)
    handler = ChatOpsCommand()
    handler.set_client_data(_make_client_data())
    payload = opamp_pb2.CustomMessage()
    payload.capability = handler.get_reverse_fqdn()
    payload.type = "by REST Call"
    payload.data = json.dumps({"action": "run"}).encode("utf-8")
    handler.set_custom_message_handler(payload)

    result = handler.execute()

    assert result is None
    assert "custom handler execute start" in caplog.text
    assert "custom handler execute end" in caplog.text


def test_registry_discovers_and_creates_handlers(tmp_path) -> None:
    """Discover handlers from a folder and instantiate by FQDN."""
    handler_code = '''
from opamp_consumer.custom_handlers.interface import CustomMessageHandlerInterface

class SampleHandler(CustomMessageHandlerInterface):
    def __init__(self):
        self._data = None
    def set_client_data(self, data):
        self._data = data
    def get_fqdn(self):
        return "sample.handler"
    def handle_message(self, message, message_type):
        pass
    def execute_action(self, action):
        pass
'''
    handler_path = tmp_path / "sample_handler.py"
    handler_path.write_text(handler_code)

    registry = discover_handlers(tmp_path, client_data=_make_client_data())
    assert registry == {"sample.handler": "SampleHandler"}
    lookup = build_factory_lookup(tmp_path, client_data=_make_client_data())
    assert "sample.handler" in lookup

    instance = create_handler("sample.handler", tmp_path, client_data=_make_client_data())
    assert instance is not None
    assert instance.get_fqdn() == "sample.handler"
    assert getattr(instance, "_data") is not None


def test_registry_ignores_missing_folder(tmp_path) -> None:
    """Return empty results when the handler folder is missing."""
    missing = tmp_path / "missing"
    registry = discover_handlers(missing, client_data=_make_client_data())
    assert registry == {}
    assert create_handler("sample.handler", missing, client_data=_make_client_data()) is None


def test_registry_ignores_non_handler_classes(tmp_path) -> None:
    """Ignore classes that do not implement the handler interface."""
    handler_code = '''\nclass NotAHandler:\n    pass\n'''
    handler_path = tmp_path / "not_handler.py"
    handler_path.write_text(handler_code)

    registry = discover_handlers(tmp_path, client_data=_make_client_data())
    assert registry == {}


def test_registry_skips_broken_module(tmp_path) -> None:
    """Skip modules that fail to import without raising."""
    handler_code = "raise RuntimeError('boom')\n"
    handler_path = tmp_path / "broken.py"
    handler_path.write_text(handler_code)

    registry = discover_handlers(tmp_path, client_data=_make_client_data())
    assert registry == {}


def test_execute_returns_commandexception_on_handler_error(tmp_path) -> None:
    """execute should return CommandException when a handler raises."""
    handler_code = '''
from opamp_consumer.custom_handlers.interface import CustomMessageHandlerInterface

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
    def execute_action(self, action):
        pass
'''
    handler_path = tmp_path / "broken_handler.py"
    handler_path.write_text(handler_code)
    instance = create_handler("broken.handler", tmp_path, client_data=_make_client_data())
    assert instance is not None

    payload = opamp_pb2.CustomMessage()
    payload.capability = "broken.handler"
    payload.type = "test"
    payload.data = b'{"action":"run"}'
    instance.set_custom_message_handler(payload)

    result = instance.execute()
    assert isinstance(result, CommandException)
