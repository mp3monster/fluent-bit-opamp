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

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_BROKER_ROOT = REPO_ROOT / "agent_broker"
if str(AGENT_BROKER_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_BROKER_ROOT))


def _install_dependency_stubs() -> None:
    if "slack_bolt.async_app" not in sys.modules:
        slack_bolt_module = types.ModuleType("slack_bolt")
        slack_bolt_async_app_module = types.ModuleType("slack_bolt.async_app")

        class _DummyAsyncApp:
            def __init__(self, *args, **kwargs):
                return None

        slack_bolt_async_app_module.AsyncApp = _DummyAsyncApp
        slack_bolt_module.async_app = slack_bolt_async_app_module
        sys.modules["slack_bolt"] = slack_bolt_module
        sys.modules["slack_bolt.async_app"] = slack_bolt_async_app_module

    if "slack_bolt.adapter.socket_mode.async_handler" not in sys.modules:
        slack_adapter_module = types.ModuleType("slack_bolt.adapter")
        slack_socket_mode_module = types.ModuleType("slack_bolt.adapter.socket_mode")
        slack_async_handler_module = types.ModuleType(
            "slack_bolt.adapter.socket_mode.async_handler"
        )

        class _DummyAsyncSocketModeHandler:
            def __init__(self, *_args, **_kwargs):
                return None

            async def start_async(self) -> None:
                return None

        slack_async_handler_module.AsyncSocketModeHandler = _DummyAsyncSocketModeHandler
        slack_socket_mode_module.async_handler = slack_async_handler_module
        slack_adapter_module.socket_mode = slack_socket_mode_module
        sys.modules["slack_bolt.adapter"] = slack_adapter_module
        sys.modules["slack_bolt.adapter.socket_mode"] = slack_socket_mode_module
        sys.modules["slack_bolt.adapter.socket_mode.async_handler"] = (
            slack_async_handler_module
        )


_install_dependency_stubs()

factory = importlib.import_module("opamp_broker.social_collaboration.factory")
slack_adapter_module = importlib.import_module(
    "opamp_broker.social_collaboration.adapters.slack"
)


def test_factory_builds_slack_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    fake_builder = Mock(return_value=sentinel)
    monkeypatch.setattr(
        slack_adapter_module.SlackSocialCollaborationAdapter,
        "from_environment",
        fake_builder,
    )

    adapter = factory.create_social_collaboration_adapter("slack")

    assert adapter is sentinel
    fake_builder.assert_called_once_with()


def test_factory_rejects_unknown_implementation() -> None:
    with pytest.raises(ValueError, match="unsupported social collaboration implementation"):
        factory.create_social_collaboration_adapter("teams")
