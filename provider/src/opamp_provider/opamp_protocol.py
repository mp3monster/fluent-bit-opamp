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

"""Protocol/auth helper functions used by OpAMP transport handlers."""

from __future__ import annotations

import logging
from http import HTTPStatus

from quart import Response

from opamp_provider import auth as provider_auth
from opamp_provider import config as provider_config
from opamp_provider.proto import opamp_pb2

CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
CHANNEL_HTTP = "HTTP"  # Client channel label for HTTP transport.


def extract_client_id(agent_msg: opamp_pb2.AgentToServer) -> str:
    """Return hex-encoded instance UID when present; otherwise an empty string."""
    if not agent_msg.instance_uid:
        return ""
    return agent_msg.instance_uid.hex()


def header_value(
    *,
    headers: dict[str, str],
    name: str,
) -> str | None:
    """Return a case-insensitive header value from a plain header dictionary."""
    for key, value in headers.items():
        if str(key).strip().lower() == name.lower():
            return str(value)
    return None


def provider_authorization_mode_to_auth_mode(
    provider_mode: str,
) -> str | None:
    """Map provider config authorization values to auth module mode."""
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_NONE:
        return provider_auth.AUTH_MODE_DISABLED
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN:
        return provider_auth.AUTH_MODE_STATIC
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_IDP:
        return provider_auth.AUTH_MODE_JWT
    return None


def evaluate_opamp_transport_auth(
    *,
    headers: dict[str, str],
    remote_addr: str | None,
    channel: str,
    opamp_http_path: str,
    invalid_config_error: str,
) -> provider_auth.AuthDecision:
    """Authorize OpAMP transport requests using provider config mode."""
    opamp_mode = str(provider_config.CONFIG.opamp_use_authorization).strip().lower()
    mapped_mode = provider_authorization_mode_to_auth_mode(opamp_mode)
    if mapped_mode is None:
        logging.getLogger(__name__).error(
            "unsupported provider.%s value=%s",
            provider_config.CFG_OPAMP_USE_AUTHORIZATION,
            opamp_mode,
        )
        return provider_auth.AuthDecision(
            allowed=False,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            error=invalid_config_error,
            reason=f"unsupported mode {opamp_mode}",
        )
    authorization_header = header_value(headers=headers, name="Authorization")
    method = "POST" if channel == CHANNEL_HTTP else "WEBSOCKET"
    return provider_auth.evaluate_required_bearer_auth(
        mode=mapped_mode,
        path=opamp_http_path,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
        static_token=provider_auth.OPAMP_AUTH_SETTINGS.static_token,
        jwt_settings=provider_auth.OPAMP_AUTH_SETTINGS,
    )


def evaluate_non_opamp_http_auth(
    *,
    path: str,
    method: str,
    authorization_header: str | None,
    remote_addr: str | None,
    invalid_config_error: str,
) -> provider_auth.AuthDecision:
    """Authorize non-OpAMP HTTP requests using provider.ui-use-authorization."""
    ui_mode = str(provider_config.CONFIG.ui_use_authorization).strip().lower()
    mapped_mode = provider_authorization_mode_to_auth_mode(ui_mode)
    if mapped_mode is None:
        logging.getLogger(__name__).error(
            "unsupported provider.%s value=%s",
            provider_config.CFG_UI_USE_AUTHORIZATION,
            ui_mode,
        )
        return provider_auth.AuthDecision(
            allowed=False,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            error=invalid_config_error,
            reason=f"unsupported mode {ui_mode}",
        )
    return provider_auth.evaluate_required_bearer_auth(
        mode=mapped_mode,
        path=path,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
        static_token=provider_auth.UI_AUTH_SETTINGS.static_token,
        jwt_settings=provider_auth.UI_AUTH_SETTINGS,
    )


def build_error_message(
    *,
    instance_uid: bytes | None,
    error_message: str,
    error_type: opamp_pb2.ServerErrorResponseType = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    ),
) -> opamp_pb2.ServerToAgent:
    """Build a ServerToAgent error payload without requiring prior response state."""
    response = opamp_pb2.ServerToAgent()
    if instance_uid:
        response.instance_uid = instance_uid
    response.error_response.type = error_type
    response.error_response.error_message = error_message
    return response


def build_opamp_http_error_response(
    *,
    instance_uid: bytes | None,
    status_code: int,
    error_message: str,
    headers: dict[str, str] | None = None,
    error_type: opamp_pb2.ServerErrorResponseType = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    ),
) -> Response:
    """Build a protobuf HTTP response carrying a ServerToAgent error payload."""
    payload = build_error_message(
        instance_uid=instance_uid,
        error_message=error_message,
        error_type=error_type,
    ).SerializeToString()
    response = Response(
        payload,
        content_type=CONTENT_TYPE_PROTO,
        status=status_code,
    )
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
    return response


def log_blocked_agent_attempt(
    *,
    client_id: str,
    channel: str,
    headers: dict[str, str],
    remote_addr: str | None,
    logger: logging.Logger,
) -> None:
    """Log one blocked-agent request with headers for audit visibility."""
    logger.warning(
        "blocked agent rejected client_id=%s channel=%s remote_addr=%s headers=%s",
        client_id or "missing",
        channel,
        remote_addr or "unknown",
        headers,
    )

