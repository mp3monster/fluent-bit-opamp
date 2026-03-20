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

from datetime import datetime

import pytest

from opamp_provider.commands import ChatOpCommand, RestartAgent, command_object_factory


def test_restart_agent_implements_command_interface_methods() -> None:
    obj = RestartAgent()
    obj.set_key_value_dictionary({"classifier": "command", "action": "restart"})

    assert obj.get_command_classifier() == "command"
    assert obj.get_command_type() == "restart"
    assert obj.get_command_description() == "restart command queued"
    assert isinstance(obj.get_command_time(), datetime)
    assert obj.get_key_value_dictionary() == {
        "classifier": "command",
        "action": "restart",
    }


def test_command_object_factory_creates_restart_agent() -> None:
    obj = command_object_factory(
        classifier="command",
        operation="restart",
        key_values={"classifier": "command", "action": "restart"},
    )

    assert isinstance(obj, RestartAgent)
    assert obj.get_command_classifier() == "command"
    assert obj.get_command_type() == "restart"


def test_chatopcommand_implements_command_interface_methods() -> None:
    obj = ChatOpCommand()
    obj.set_key_value_dictionary({"classifier": "custom", "action": "chatopcommand"})

    assert obj.get_command_classifier() == "custom"
    assert obj.get_command_type() == "chatopcommand"
    assert obj.get_command_description() == "custom chatopcommand queued"
    assert isinstance(obj.get_command_time(), datetime)
    assert obj.get_key_value_dictionary() == {
        "classifier": "custom",
        "action": "chatopcommand",
    }


def test_command_object_factory_creates_chatopcommand() -> None:
    obj = command_object_factory(
        classifier="custom",
        operation="chatopcommand",
        key_values={"classifier": "custom", "action": "chatopcommand"},
    )

    assert isinstance(obj, ChatOpCommand)
    assert obj.get_command_classifier() == "custom"
    assert obj.get_command_type() == "chatopcommand"


def test_command_object_factory_rejects_unknown_mapping() -> None:
    with pytest.raises(ValueError):
        command_object_factory(
            classifier="custom_command",
            operation="unknown",
            key_values={"classifier": "custom_command", "action": "unknown"},
        )
