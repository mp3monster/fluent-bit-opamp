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

import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_BROKER_ROOT = REPO_ROOT / "agent_broker"
if str(AGENT_BROKER_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_BROKER_ROOT))

nodes = importlib.import_module("opamp_broker.graph.nodes")
planner_engine = importlib.import_module("opamp_broker.planner.engine")
ai_svc_planner = importlib.import_module("opamp_broker.planner.ai_svc_planner")
openai_compatible_connection = importlib.import_module(
    "opamp_broker.planner.openai_compatible_connection"
)
state_module = importlib.import_module("opamp_broker.graph.state")
mcp_client_module = importlib.import_module("opamp_broker.mcp.client")


class _FakeToolRegistry:
    def __init__(self, tools: dict[str, dict[str, Any]]) -> None:
        self._tools = tools

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def get(self, name: str) -> dict[str, Any] | None:
        return self._tools.get(name)


class _FakePlanner:
    def __init__(self, plan: dict[str, Any]) -> None:
        self._plan = plan

    async def plan(self, *, text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        return self._plan


class _RaisingPlanner:
    async def plan(self, *, text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        del text, tools
        raise RuntimeError("planner unavailable")


def test_create_planner_returns_rule_first_without_api_key() -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ.pop(api_key_env_var, None)
    planner = planner_engine.create_planner(
        {"planner": {"llm_enabled": True, "model": "gpt-5.4"}}
    )
    assert isinstance(planner, planner_engine.RuleFirstPlanner)


def test_create_planner_returns_ai_svc_planner_with_api_key() -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ[api_key_env_var] = "test-key"
    planner = planner_engine.create_planner(
        {
            "planner": {
                "llm_enabled": True,
                "model": "gpt-5.4",
                "prompts": {
                    "system_prompt": "system prompt",
                    "verification_prompt": "verification prompt",
                },
            }
        }
    )
    assert isinstance(planner, planner_engine.AISvcPlanner)
    os.environ.pop(api_key_env_var, None)


def test_create_planner_applies_configured_max_completion_tokens() -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ[api_key_env_var] = "test-key"
    planner = planner_engine.create_planner(
        {
            "planner": {
                "llm_enabled": True,
                "model": "gpt-5.4",
                "max_completion_tokens": 2048,
                "prompts": {
                    "system_prompt": "system prompt",
                    "verification_prompt": "verification prompt",
                },
            }
        }
    )
    assert isinstance(planner, planner_engine.AISvcPlanner)
    assert planner.connection.max_completion_tokens == 2048
    os.environ.pop(api_key_env_var, None)


def test_create_planner_returns_rule_first_for_unsupported_provider() -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ[api_key_env_var] = "test-key"
    planner = planner_engine.create_planner(
        {
            "planner": {
                "llm_enabled": True,
                "provider": "unsupported-provider",
                "model": "gpt-5.4",
                "prompts": {
                    "system_prompt": "system prompt",
                    "verification_prompt": "verification prompt",
                },
            }
        }
    )
    assert isinstance(planner, planner_engine.RuleFirstPlanner)
    os.environ.pop(api_key_env_var, None)


def test_create_planner_accepts_openai_compatible_provider_alias() -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ[api_key_env_var] = "test-key"
    planner = planner_engine.create_planner(
        {
            "planner": {
                "llm_enabled": True,
                "provider": "openai-compatible",
                "model": "gpt-5.4",
                "prompts": {
                    "system_prompt": "system prompt",
                    "verification_prompt": "verification prompt",
                },
            }
        }
    )
    assert isinstance(planner, planner_engine.AISvcPlanner)
    os.environ.pop(api_key_env_var, None)


def test_create_planner_returns_rule_first_for_template_provider() -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ[api_key_env_var] = "test-key"
    planner = planner_engine.create_planner(
        {
            "planner": {
                "llm_enabled": True,
                "provider": "template",
                "model": "gpt-5.4",
                "prompts": {
                    "system_prompt": "system prompt",
                    "verification_prompt": "verification prompt",
                },
            }
        }
    )
    assert isinstance(planner, planner_engine.RuleFirstPlanner)
    os.environ.pop(api_key_env_var, None)


def test_sanitize_plan_rejects_unknown_tool() -> None:
    sanitized = planner_engine._sanitize_plan(
        parsed={
            planner_engine.TOOL_NAME_KEY: "tool.not.allowed",
            planner_engine.TOOL_ARGS_KEY: {"target": "collector-a"},
            planner_engine.RESPONSE_TEXT_KEY: "",
            planner_engine.REQUIRES_CONFIRMATION_KEY: False,
        },
        tools=[{"name": "tool.status"}],
    )
    assert sanitized[planner_engine.TOOL_NAME_KEY] is None
    assert sanitized[planner_engine.TOOL_ARGS_KEY] == {}


def test_broker_plan_schema_uses_openai_strict_safe_tool_arg_value_types() -> None:
    tool_args = planner_engine.BROKER_PLAN_JSON_SCHEMA["properties"][
        planner_engine.TOOL_ARGS_KEY
    ]
    assert tool_args["type"] == "string"


def test_sanitize_plan_parses_tool_args_json_string() -> None:
    sanitized = planner_engine._sanitize_plan(
        parsed={
            planner_engine.RESPONSE_TEXT_KEY: "Running status",
            planner_engine.TOOL_NAME_KEY: "tool.status",
            planner_engine.TOOL_ARGS_KEY: '{"target":"collector-a"}',
            planner_engine.REQUIRES_CONFIRMATION_KEY: False,
        },
        tools=[{"name": "tool.status"}],
    )
    assert sanitized[planner_engine.TOOL_ARGS_KEY] == {"target": "collector-a"}


def test_rule_first_planner_lists_tools() -> None:
    planner = planner_engine.RuleFirstPlanner()
    plan = asyncio.run(
        planner.plan(
            text="tools",
            tools=[{"name": "tool.status"}, {"name": "tool.health"}],
        )
    )
    assert "Available MCP tools" in plan[planner_engine.RESPONSE_TEXT_KEY]
    assert plan[planner_engine.TOOL_NAME_KEY] is None


def test_rule_first_planner_describes_tools_with_argument_hints() -> None:
    planner = planner_engine.RuleFirstPlanner()
    plan = asyncio.run(
        planner.plan(
            text="what can you do?",
            tools=[
                {
                    "name": "tool.status",
                    "description": "Check agent status",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "verbose": {"type": "boolean"},
                        },
                        "required": ["target"],
                    },
                }
            ],
        )
    )
    response = plan[planner_engine.RESPONSE_TEXT_KEY]
    assert "tool.status" in response
    assert "Check agent status" in response
    assert "target (string, required)" in response
    assert "verbose (boolean, optional)" in response
    assert plan[planner_engine.TOOL_NAME_KEY] is None


def test_rule_first_planner_allows_direct_tool_name_invocation() -> None:
    planner = planner_engine.RuleFirstPlanner()
    plan = asyncio.run(
        planner.plan(
            text="tool_otel_agents",
            tools=[
                {
                    "name": "tool_otel_agents",
                    "description": "List OpenTelemetry agents",
                }
            ],
        )
    )
    assert plan[planner_engine.TOOL_NAME_KEY] == "tool_otel_agents"
    assert plan[planner_engine.TOOL_ARGS_KEY] == {}
    assert plan[planner_engine.REQUIRES_CONFIRMATION_KEY] is False


def test_rule_first_planner_allows_direct_tool_name_with_target() -> None:
    planner = planner_engine.RuleFirstPlanner()
    plan = asyncio.run(
        planner.plan(
            text="tool.status collector-a",
            tools=[
                {
                    "name": "tool.status",
                    "description": "Get status",
                }
            ],
        )
    )
    assert plan[planner_engine.TOOL_NAME_KEY] == "tool.status"
    assert plan[planner_engine.TOOL_ARGS_KEY] == {"target": "collector-a"}
    assert plan[planner_engine.REQUIRES_CONFIRMATION_KEY] is False


def test_plan_action_uses_only_discovered_tool_names() -> None:
    tool_registry = _FakeToolRegistry(
        {
            "tool.status": {"name": "tool.status", "description": "status"},
        }
    )
    planner = _FakePlanner(
        {
            planner_engine.RESPONSE_TEXT_KEY: "",
            planner_engine.TOOL_NAME_KEY: "tool.unknown",
            planner_engine.TOOL_ARGS_KEY: {"target": "collector-a"},
            planner_engine.REQUIRES_CONFIRMATION_KEY: False,
        }
    )
    state = {
        state_module.STATE_KEY_TEXT: "status collector-a",
        state_module.STATE_KEY_NORMALIZED_TEXT: "status collector-a",
    }

    updated = asyncio.run(nodes.plan_action(state, tool_registry, planner))

    assert updated[state_module.STATE_KEY_TOOL_NAME] is None
    assert updated[state_module.STATE_KEY_TOOL_ARGS] == {}
    assert "couldn't map" in updated[state_module.STATE_KEY_RESPONSE_TEXT]


def test_plan_action_accepts_discovered_tool_name() -> None:
    tool_registry = _FakeToolRegistry(
        {
            "tool.status": {"name": "tool.status", "description": "status"},
        }
    )
    planner = _FakePlanner(
        {
            planner_engine.RESPONSE_TEXT_KEY: "",
            planner_engine.TOOL_NAME_KEY: "tool.status",
            planner_engine.TOOL_ARGS_KEY: {"target": "collector-a"},
            planner_engine.REQUIRES_CONFIRMATION_KEY: False,
        }
    )
    state = {
        state_module.STATE_KEY_TEXT: "status collector-a",
        state_module.STATE_KEY_NORMALIZED_TEXT: "status collector-a",
    }

    updated = asyncio.run(nodes.plan_action(state, tool_registry, planner))

    assert updated[state_module.STATE_KEY_TOOL_NAME] == "tool.status"
    assert updated[state_module.STATE_KEY_TOOL_ARGS] == {"target": "collector-a"}
    assert updated[state_module.STATE_KEY_TARGET] == "collector-a"


def test_plan_action_returns_offline_message_when_mcp_unavailable() -> None:
    class _UnavailableToolRegistry:
        def list_names(self) -> list[str]:
            return []

        async def refresh(self) -> None:
            raise mcp_client_module.MCPServerUnavailableError("offline")

        def get(self, name: str) -> dict[str, Any] | None:
            return None

    planner = _FakePlanner(
        {
            planner_engine.RESPONSE_TEXT_KEY: "",
            planner_engine.TOOL_NAME_KEY: None,
            planner_engine.TOOL_ARGS_KEY: {},
            planner_engine.REQUIRES_CONFIRMATION_KEY: False,
        }
    )
    state = {
        state_module.STATE_KEY_TEXT: "status collector-a",
        state_module.STATE_KEY_NORMALIZED_TEXT: "status collector-a",
    }

    updated = asyncio.run(
        nodes.plan_action(
            state,
            _UnavailableToolRegistry(),
            planner,
            "The OpAMP server is currently offline.",
        )
    )

    assert updated[state_module.STATE_KEY_TOOL_NAME] is None
    assert updated[state_module.STATE_KEY_TOOL_ARGS] == {}
    assert updated[state_module.STATE_KEY_TOOLS_AVAILABLE] == []
    assert updated[state_module.STATE_KEY_RESPONSE_TEXT] == (
        "The OpAMP server is currently offline."
    )


def test_plan_action_falls_back_to_rule_first_when_planner_raises() -> None:
    tool_registry = _FakeToolRegistry(
        {
            "tool.status": {"name": "tool.status", "description": "status"},
        }
    )
    state = {
        state_module.STATE_KEY_TEXT: "status collector-a",
        state_module.STATE_KEY_NORMALIZED_TEXT: "status collector-a",
    }

    updated = asyncio.run(nodes.plan_action(state, tool_registry, _RaisingPlanner()))

    assert updated[state_module.STATE_KEY_TOOL_NAME] == "tool.status"
    assert updated[state_module.STATE_KEY_TOOL_ARGS] == {"target": "collector-a"}
    assert updated[state_module.STATE_KEY_TARGET] == "collector-a"


def test_execute_or_summarize_returns_offline_message_when_mcp_unavailable() -> None:
    class _UnavailableToolRegistry:
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any],
        ) -> dict[str, Any]:
            raise mcp_client_module.MCPServerUnavailableError(
                f"offline while calling {name}"
            )

    state = {
        state_module.STATE_KEY_TOOL_NAME: "tool.status",
        state_module.STATE_KEY_TOOL_ARGS: {"target": "collector-a"},
    }

    updated = asyncio.run(
        nodes.execute_or_summarize(
            state,
            _UnavailableToolRegistry(),
            "The OpAMP server is currently offline.",
        )
    )

    assert updated[state_module.STATE_KEY_RESPONSE_TEXT] == (
        "The OpAMP server is currently offline."
    )
    assert "offline while calling tool.status" in str(
        updated[state_module.STATE_KEY_TOOL_RESULT]
    )


def test_execute_or_summarize_renders_otel_agents_json_as_plain_english() -> None:
    class _FakeToolRegistry:
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any],
        ) -> dict[str, Any]:
            del name, arguments
            return {
                "content": [
                    {
                        "type": "text",
                        "text": '{"agents":[],"total":0}',
                    }
                ]
            }

    state = {
        state_module.STATE_KEY_TOOL_NAME: "tool_otel_agents",
        state_module.STATE_KEY_TOOL_ARGS: {},
    }
    updated = asyncio.run(nodes.execute_or_summarize(state, _FakeToolRegistry()))
    assert updated[state_module.STATE_KEY_RESPONSE_TEXT] == (
        "I checked and found no OpenTelemetry agents."
    )


def test_execute_or_summarize_renders_commands_json_as_plain_english() -> None:
    class _FakeToolRegistry:
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any],
        ) -> dict[str, Any]:
            del name, arguments
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"commands":[{"operation":"restart","classifier":"opamp"},'
                            '{"displayname":"Shutdown Agent","operation":"shutdown","classifier":"custom"}],'
                            '"total":2}'
                        ),
                    }
                ]
            }

    state = {
        state_module.STATE_KEY_TOOL_NAME: "tool_commands",
        state_module.STATE_KEY_TOOL_ARGS: {},
    }
    updated = asyncio.run(nodes.execute_or_summarize(state, _FakeToolRegistry()))
    response = str(updated[state_module.STATE_KEY_RESPONSE_TEXT])
    assert "I found 2 available command(s)" in response
    assert "opamp/restart" in response
    assert "Shutdown Agent" in response
    assert "<structured>" not in response


def test_verify_ai_svc_connection_uses_connection_factory(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeConnection:
        async def verify_connection(self, *, model: str) -> dict[str, Any]:
            captured["model"] = model
            return {"ok": True, "message": "ok"}

    def _fake_create_ai_connection(**kwargs: Any) -> _FakeConnection:
        captured["kwargs"] = kwargs
        return _FakeConnection()

    monkeypatch.setattr(
        ai_svc_planner,
        "create_ai_connection",
        _fake_create_ai_connection,
    )

    result = asyncio.run(
        ai_svc_planner.verify_ai_svc_connection(
            model="gpt-5.4",
            provider="openai",
            timeout_seconds=7,
            api_key_env_var=planner_engine.DEFAULT_AI_SVC_API_KEY_ENV,
            base_url="https://api.openai.com/v1",
        )
    )

    assert result["ok"] is True
    assert captured["kwargs"]["provider"] == "openai"
    assert captured["kwargs"]["timeout_seconds"] == 7
    assert captured["kwargs"]["api_key_env_var"] == planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    assert captured["kwargs"]["base_url"] == "https://api.openai.com/v1"
    assert captured["kwargs"]["temperature"] == 0.0
    assert captured["kwargs"]["max_completion_tokens"] == 1024
    assert captured["kwargs"]["verify_max_completion_tokens_attempts"] == (64, 512)
    assert captured["kwargs"]["verification_prompt"] == ""
    assert captured["model"] == "gpt-5.4"


def test_verify_ai_svc_connection_template_provider_is_not_ok() -> None:
    result = asyncio.run(
        ai_svc_planner.verify_ai_svc_connection(
            model="gpt-5.4",
            provider="template",
            timeout_seconds=7,
            api_key_env_var=planner_engine.DEFAULT_AI_SVC_API_KEY_ENV,
            base_url="https://example.invalid/v1",
        )
    )
    assert result["ok"] is False
    assert "not implemented" in str(result["error"])


def test_openai_verify_connection_retries_on_output_limit_error(
    monkeypatch: Any,
) -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ[api_key_env_var] = "test-key"
    captured_max_tokens: list[int] = []

    class _FakeResponse:
        def __init__(
            self,
            *,
            url: str,
            fail_with_limit_error: bool,
            max_completion_tokens: int,
        ) -> None:
            self._url = url
            self._fail_with_limit_error = fail_with_limit_error
            self._max_completion_tokens = max_completion_tokens

        def raise_for_status(self) -> None:
            if self._fail_with_limit_error:
                request = httpx.Request("POST", self._url)
                response = httpx.Response(
                    400,
                    request=request,
                    text=(
                        '{"error":{"message":"Could not finish the message because '
                        'max_tokens or model output limit was reached."}}'
                    ),
                )
                raise httpx.HTTPStatusError(
                    "verification token limit",
                    request=request,
                    response=response,
                )

        def json(self) -> dict[str, Any]:
            return {
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 5,
                    "total_tokens": 16,
                },
                "choices": [
                    {
                        "message": {
                            "content": (
                                f"verify ok {self._max_completion_tokens}"
                            )
                        }
                    }
                ],
            }

    class _FakeAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(
            self,
            exc_type: Any,
            exc: Any,
            tb: Any,
        ) -> bool:
            return False

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _FakeResponse:
            del headers
            captured_max_tokens.append(int(json["max_completion_tokens"]))
            # First attempt fails with output limit; retry succeeds.
            return _FakeResponse(
                url=url,
                fail_with_limit_error=len(captured_max_tokens) == 1,
                max_completion_tokens=int(json["max_completion_tokens"]),
            )

    monkeypatch.setattr(
        openai_compatible_connection.httpx,
        "AsyncClient",
        _FakeAsyncClient,
    )

    connection = openai_compatible_connection.OpenAICompatibleConnection(
        provider="openai",
        api_key_env_var=api_key_env_var,
        base_url="https://api.openai.com/v1",
        timeout_seconds=7,
        verification_prompt="Connection check. Reply with OK.",
    )
    result = asyncio.run(connection.verify_connection(model="gpt-5.4"))

    assert result["ok"] is True
    assert captured_max_tokens == [64, 512]
    assert result["verify_max_completion_tokens_attempts"] == [64, 512]
    assert result["verification_attempt_count"] == 2
    assert result["verification_max_completion_tokens_used"] == 512
    assert result["usage"]["prompt_tokens"] == 11
    assert result["usage"]["completion_tokens"] == 5
    assert result["usage"]["total_tokens"] == 16
    os.environ.pop(api_key_env_var, None)


def test_openai_request_includes_provider_error_details_on_http_failure(
    monkeypatch: Any,
) -> None:
    api_key_env_var = planner_engine.DEFAULT_AI_SVC_API_KEY_ENV
    os.environ[api_key_env_var] = "test-key"

    class _FakeErrorResponse:
        def __init__(self, *, url: str) -> None:
            self._url = url

        def raise_for_status(self) -> None:
            request = httpx.Request("POST", self._url)
            response = httpx.Response(
                400,
                request=request,
                text=(
                    '{"error":{"message":"Unsupported parameter: max_tokens",'
                    '"type":"invalid_request_error","param":"max_tokens",'
                    '"code":"unsupported_parameter"}}'
                ),
                headers={"content-type": "application/json"},
            )
            raise httpx.HTTPStatusError(
                "planner failure",
                request=request,
                response=response,
            )

    class _FakeAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(
            self,
            exc_type: Any,
            exc: Any,
            tb: Any,
        ) -> bool:
            return False

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _FakeErrorResponse:
            del headers, json
            return _FakeErrorResponse(url=url)

    monkeypatch.setattr(
        openai_compatible_connection.httpx,
        "AsyncClient",
        _FakeAsyncClient,
    )

    connection = openai_compatible_connection.OpenAICompatibleConnection(
        provider="openai",
        api_key_env_var=api_key_env_var,
        base_url="https://api.openai.com/v1",
        timeout_seconds=7,
    )

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(
            connection.request_json_schema_completion(
                model="gpt-5.2",
                messages=[{"role": "user", "content": "hello"}],
                schema_name="broker_plan",
                schema=planner_engine.BROKER_PLAN_JSON_SCHEMA,
            )
        )

    message = str(exc_info.value)
    assert "AI service returned 400 for planner request" in message
    assert "unsupported_parameter" in message
    assert "max_tokens" in message
    os.environ.pop(api_key_env_var, None)
