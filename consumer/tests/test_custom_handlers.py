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

from opamp_consumer.client import OpAMPClientData
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.custom_handlers import (
    ChatOpsCommand,
    create_handler,
    discover_handlers,
)


def _make_client_data() -> OpAMPClientData:
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


def test_registry_discovers_and_creates_handlers(tmp_path) -> None:
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

    instance = create_handler("sample.handler", tmp_path, client_data=_make_client_data())
    assert instance is not None
    assert instance.get_fqdn() == "sample.handler"
    assert getattr(instance, "_data") is not None


def test_registry_ignores_missing_folder(tmp_path) -> None:
    missing = tmp_path / "missing"
    registry = discover_handlers(missing, client_data=_make_client_data())
    assert registry == {}
    assert create_handler("sample.handler", missing, client_data=_make_client_data()) is None


def test_registry_ignores_non_handler_classes(tmp_path) -> None:
    handler_code = '''\nclass NotAHandler:\n    pass\n'''
    handler_path = tmp_path / "not_handler.py"
    handler_path.write_text(handler_code)

    registry = discover_handlers(tmp_path, client_data=_make_client_data())
    assert registry == {}


def test_registry_skips_broken_module(tmp_path) -> None:
    handler_code = "raise RuntimeError('boom')\n"
    handler_path = tmp_path / "broken.py"
    handler_path.write_text(handler_code)

    registry = discover_handlers(tmp_path, client_data=_make_client_data())
    assert registry == {}
