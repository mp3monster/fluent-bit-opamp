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
import json

import pytest

from opamp_provider.commands import (
    ChatOpCommand,
    RestartAgent,
    command_object_factory,
    get_command_metadata,
    get_available_command_keys,
    get_command_fqdn,
    get_custom_capabilities_list,
    get_registered_command_fqdns,
    get_registered_command_keys,
)
from opamp_provider.chatop_command import (
    CHATOPCOMMAND_CAPABILITY,
    CHATOPCOMMAND_TYPE,
)
from opamp_provider.command_shutdown_agent import (
    SHUTDOWN_AGENT_CAPABILITY,
    SHUTDOWN_AGENT_TYPE,
)
from opamp_provider.command_nullcommand import (
    NULLCOMMAND_CAPABILITY,
    NULLCOMMAND_TYPE,
)


def test_restart_agent_implements_command_interface_methods() -> None:
    obj = RestartAgent()
    obj.set_key_value_dictionary({"classifier": "command", "action": "restart"})

    assert obj.get_command_classifier() == "command"
    assert obj.get_command_type() == "restart"
    assert obj.get_command_description() == "Restart Agent"
    assert obj.getdisplayname() == "Restart Agent"
    assert isinstance(obj.get_command_time(), datetime)
    assert obj.get_key_value_dictionary() == {
        "classifier": "command",
        "action": "restart",
    }
    assert obj.isOpAMPStandard() is True
    assert obj.get_user_parameter_schema() == [
        {
            "parametername": "action",
            "type": "string",
            "description": "Command action to execute.",
            "isrequired": True,
        },
    ]


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
    assert obj.getdisplayname() == "ChatOps Command"
    assert isinstance(obj.get_command_time(), datetime)
    assert obj.get_key_value_dictionary() == {
        "classifier": "custom",
        "action": "chatopcommand",
    }
    assert obj.isOpAMPStandard() is False
    assert obj.get_user_parameter_schema() == [
        {
            "parametername": "action",
            "type": "string",
            "description": "Custom command operation name.",
            "isrequired": True,
        },
    ]


def test_command_object_factory_creates_chatopcommand() -> None:
    obj = command_object_factory(
        classifier="custom",
        operation="chatopcommand",
        key_values={"classifier": "custom", "action": "chatopcommand"},
    )

    assert isinstance(obj, ChatOpCommand)
    assert obj.get_command_classifier() == "custom"
    assert obj.get_command_type() == "chatopcommand"


def test_command_object_factory_creates_shutdownagent() -> None:
    obj = command_object_factory(
        classifier="custom",
        operation="shutdownagent",
        key_values={"classifier": "custom", "action": "shutdownagent"},
    )

    assert obj.get_command_classifier() == "custom"
    assert obj.get_command_type() == "shutdownagent"
    assert obj.getdisplayname() == "Shutdown Agent"
    assert obj.get_user_parameter_schema() == []


def test_command_object_factory_creates_nullcommand() -> None:
    obj = command_object_factory(
        classifier="custom",
        operation="nullcommand",
        key_values={"classifier": "custom", "action": "nullcommand"},
    )

    assert obj.get_command_classifier() == "custom"
    assert obj.get_command_type() == "nullcommand"
    assert obj.getdisplayname() == "Null Command"
    assert obj.get_user_parameter_schema() == []


def test_chatopcommand_generates_custom_message_with_reverse_fqdn_capability() -> None:
    obj = ChatOpCommand()
    obj.set_key_value_dictionary(
        {
            "classifier": "custom",
            "action": "chatopcommand",
            "type": "notify",
            "data": "hello",
        }
    )

    message = obj.to_custom_message()
    assert message.capability == CHATOPCOMMAND_CAPABILITY
    assert message.type == CHATOPCOMMAND_TYPE
    assert message.data == json.dumps(
        {
            "classifier": "custom",
            "action": "chatopcommand",
            "type": "notify",
            "data": "hello",
        },
        sort_keys=True,
    ).encode("utf-8")


def test_shutdownagent_generates_custom_message_with_reverse_fqdn_capability() -> None:
    obj = command_object_factory(
        classifier="custom",
        operation="shutdownagent",
        key_values={"classifier": "custom", "action": "shutdownagent"},
    )
    message = obj.to_custom_message()
    assert message.capability == SHUTDOWN_AGENT_CAPABILITY
    assert message.type == SHUTDOWN_AGENT_TYPE


def test_nullcommand_generates_custom_message_with_reverse_fqdn_capability() -> None:
    obj = command_object_factory(
        classifier="custom",
        operation="nullcommand",
        key_values={"classifier": "custom", "action": "nullcommand"},
    )
    message = obj.to_custom_message()
    assert message.capability == NULLCOMMAND_CAPABILITY
    assert message.type == NULLCOMMAND_TYPE


def test_command_object_factory_rejects_unknown_mapping() -> None:
    with pytest.raises(ValueError):
        command_object_factory(
            classifier="custom_command",
            operation="unknown",
            key_values={"classifier": "custom_command", "action": "unknown"},
        )


def test_command_registry_discovers_supported_commands_on_startup() -> None:
    keys = get_registered_command_keys(includedisplayname=False)
    assert ("custom", "chatopcommand") in keys
    assert ("custom", "nullcommand") in keys
    assert ("custom", "shutdownagent") in keys
    assert ("command", "restart") not in keys


def test_command_registry_can_return_opamp_standard_entries() -> None:
    keys = get_registered_command_keys(
        parameter_exclude_opamp_standard=False,
        includedisplayname=False,
    )
    assert ("command", "restart") in keys
    assert ("custom", "chatopcommand") not in keys


def test_available_command_list_excludes_opamp_standard_entries() -> None:
    keys = get_available_command_keys(includedisplayname=False)
    assert ("custom", "chatopcommand") in keys
    assert ("custom", "nullcommand") in keys
    assert ("custom", "shutdownagent") in keys
    assert ("command", "restart") not in keys


def test_registered_command_list_returns_display_map_by_default() -> None:
    commands = get_registered_command_keys()
    assert commands == {
        CHATOPCOMMAND_CAPABILITY: "ChatOps Command",
        NULLCOMMAND_CAPABILITY: "Null Command",
        SHUTDOWN_AGENT_CAPABILITY: "Shutdown Agent",
    }


def test_command_metadata_returns_custom_schema_with_display_name() -> None:
    metadata = get_command_metadata(parameter_exclude_opamp_standard=True, custom_only=True)
    entries = {entry["operation"]: entry for entry in metadata}
    assert set(entries.keys()) == {"chatopcommand", "nullcommand", "shutdownagent"}
    entry = entries["chatopcommand"]
    assert entry["fqdn"] == CHATOPCOMMAND_CAPABILITY
    assert entry["displayname"] == "ChatOps Command"
    assert entry["description"] == "custom chatopcommand queued"
    assert entry["classifier"] == "custom"
    assert entry["operation"] == "chatopcommand"
    assert {
        "parametername": "action",
        "type": "string",
        "description": "Custom command operation name.",
        "isrequired": True,
    } in entry["schema"]
    for row in entry["schema"]:
        assert row.get("parametername") not in {"classifier", "type", "data"}
    assert entries["shutdownagent"]["fqdn"] == SHUTDOWN_AGENT_CAPABILITY
    assert entries["shutdownagent"]["displayname"] == "Shutdown Agent"
    assert entries["shutdownagent"]["description"] == "custom shutdownagent queued"
    assert entries["shutdownagent"]["schema"] == []
    assert entries["nullcommand"]["fqdn"] == NULLCOMMAND_CAPABILITY
    assert entries["nullcommand"]["displayname"] == "Null Command"
    assert entries["nullcommand"]["description"] == "custom nullcommand queued"
    assert entries["nullcommand"]["schema"] == []


def test_command_registry_exposes_reverse_fqdn_map() -> None:
    fqdns = get_registered_command_fqdns()
    assert ("custom", "chatopcommand") in fqdns
    assert ("custom", "nullcommand") in fqdns
    assert ("custom", "shutdownagent") in fqdns
    assert fqdns[("custom", "chatopcommand")] == CHATOPCOMMAND_CAPABILITY
    assert fqdns[("custom", "nullcommand")] == NULLCOMMAND_CAPABILITY
    assert fqdns[("custom", "shutdownagent")] == SHUTDOWN_AGENT_CAPABILITY
    assert (
        get_command_fqdn(classifier="custom", operation="chatopcommand")
        == CHATOPCOMMAND_CAPABILITY
    )
    assert (
        get_command_fqdn(classifier="custom", operation="nullcommand")
        == NULLCOMMAND_CAPABILITY
    )
    assert (
        get_command_fqdn(classifier="custom", operation="shutdownagent")
        == SHUTDOWN_AGENT_CAPABILITY
    )
    assert get_command_fqdn(classifier="command", operation="restart") == ""


def test_custom_capabilities_list_excludes_empty_or_none_capabilities() -> None:
    capabilities = get_custom_capabilities_list()
    assert CHATOPCOMMAND_CAPABILITY in capabilities
    assert NULLCOMMAND_CAPABILITY in capabilities
    assert SHUTDOWN_AGENT_CAPABILITY in capabilities
    assert all(capability for capability in capabilities)
