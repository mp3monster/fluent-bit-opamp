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

"""Authentication helpers for provider HTTP and MCP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hmac
import logging
import os
from http import HTTPStatus
from typing import Iterable, Optional
from urllib.parse import quote, urlencode

try:
    import jwt
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some dev envs
    jwt = None  # type: ignore[assignment]

AUTH_MODE_DISABLED = "disabled"  # Auth mode that bypasses bearer validation checks.
AUTH_MODE_STATIC = "static"  # Auth mode using a single configured static bearer token.
AUTH_MODE_JWT = "jwt"  # Auth mode validating JWT bearer tokens against JWKS.
DEFAULT_AUTH_MODE = AUTH_MODE_DISABLED  # Default auth mode when none is configured.
DEFAULT_PROTECTED_PATH_PREFIXES = (
    "/tool",
    "/sse",
    "/messages",
    "/mcp",
    "/api",
)  # Default route prefixes protected by bearer auth.

ENV_AUTH_MODE = "OPAMP_AUTH_MODE"  # Environment variable selecting auth mode.
ENV_AUTH_PROTECTED_PATH_PREFIXES = "OPAMP_AUTH_PROTECTED_PATH_PREFIXES"  # Environment variable listing protected path prefixes.
ENV_AUTH_STATIC_TOKEN = "OPAMP_AUTH_STATIC_TOKEN"  # Environment variable holding static bearer token value.
ENV_AUTH_JWT_ISSUER = "OPAMP_AUTH_JWT_ISSUER"  # Environment variable for expected JWT issuer claim.
ENV_AUTH_JWT_AUDIENCE = "OPAMP_AUTH_JWT_AUDIENCE"  # Environment variable for expected JWT audience claim.
ENV_AUTH_JWT_JWKS_URL = "OPAMP_AUTH_JWT_JWKS_URL"  # Environment variable for JWKS endpoint URL.
ENV_AUTH_JWT_LEEWAY_SECONDS = "OPAMP_AUTH_JWT_LEEWAY_SECONDS"  # Environment variable for JWT clock-skew leeway.
ENV_AUTH_IDP_LOGIN_URL = "OPAMP_AUTH_IDP_LOGIN_URL"  # Optional explicit IdP login URL used for browser redirects.
ENV_AUTH_IDP_CLIENT_ID = "OPAMP_AUTH_IDP_CLIENT_ID"  # Optional IdP client id used when deriving login URL from issuer.

WWW_AUTHENTICATE_BEARER = 'Bearer realm="opamp-provider"'  # WWW-Authenticate challenge for bearer-protected endpoints.


@dataclass(frozen=True)
class AuthSettings:
    """Resolved bearer auth settings from environment variables."""

    mode: str
    protected_path_prefixes: tuple[str, ...]
    static_token: str | None
    jwt_issuer: str | None
    jwt_audience: str | None
    jwt_jwks_url: str | None
    jwt_leeway_seconds: int
    idp_login_url: str | None
    idp_client_id: str | None


@dataclass(frozen=True)
class AuthDecision:
    """Authorization decision details used by Quart and ASGI handlers."""

    allowed: bool
    status_code: int = HTTPStatus.OK
    error: str = ""
    reason: str = ""


def _normalize_path(path: str) -> str:
    """Normalize path for robust exact-or-descendant prefix checks."""
    return path.rstrip("/") or "/"


def _normalize_prefixes(raw_prefixes: Iterable[str]) -> tuple[str, ...]:
    """Normalize configured protected path prefixes."""
    normalized: list[str] = []
    for value in raw_prefixes:
        prefix = _normalize_path(str(value).strip())
        if not prefix or prefix == "":
            continue
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        if prefix not in normalized:
            normalized.append(prefix)
    return tuple(normalized)


def _derive_default_jwks_url(jwt_issuer: str | None) -> str | None:
    """Derive the Keycloak-compatible JWKS endpoint when issuer is provided."""
    if not jwt_issuer:
        return None
    return f"{jwt_issuer.rstrip('/')}/protocol/openid-connect/certs"


def _load_auth_settings_from_env() -> AuthSettings:
    """Load auth settings from environment variables."""
    raw_mode = str(os.environ.get(ENV_AUTH_MODE, DEFAULT_AUTH_MODE)).strip().lower()
    mode = (
        raw_mode
        if raw_mode in {AUTH_MODE_DISABLED, AUTH_MODE_STATIC, AUTH_MODE_JWT}
        else DEFAULT_AUTH_MODE
    )
    raw_prefixes = os.environ.get(ENV_AUTH_PROTECTED_PATH_PREFIXES, "")
    if raw_prefixes.strip():
        protected_path_prefixes = _normalize_prefixes(raw_prefixes.split(","))
    else:
        protected_path_prefixes = DEFAULT_PROTECTED_PATH_PREFIXES
    jwt_issuer = str(os.environ.get(ENV_AUTH_JWT_ISSUER, "")).strip() or None
    jwt_jwks_url = str(os.environ.get(ENV_AUTH_JWT_JWKS_URL, "")).strip() or None
    if jwt_jwks_url is None:
        jwt_jwks_url = _derive_default_jwks_url(jwt_issuer)
    try:
        jwt_leeway_seconds = max(
            0,
            int(os.environ.get(ENV_AUTH_JWT_LEEWAY_SECONDS, "30")),
        )
    except ValueError:
        jwt_leeway_seconds = 30
    return AuthSettings(
        mode=mode,
        protected_path_prefixes=protected_path_prefixes,
        static_token=str(os.environ.get(ENV_AUTH_STATIC_TOKEN, "")).strip() or None,
        jwt_issuer=jwt_issuer,
        jwt_audience=str(os.environ.get(ENV_AUTH_JWT_AUDIENCE, "")).strip() or None,
        jwt_jwks_url=jwt_jwks_url,
        jwt_leeway_seconds=jwt_leeway_seconds,
        idp_login_url=str(os.environ.get(ENV_AUTH_IDP_LOGIN_URL, "")).strip() or None,
        idp_client_id=str(os.environ.get(ENV_AUTH_IDP_CLIENT_ID, "")).strip() or None,
    )


AUTH_SETTINGS = _load_auth_settings_from_env()  # Module-level auth settings singleton loaded from environment.


def reload_auth_settings() -> AuthSettings:
    """Reload environment-backed auth settings (used by tests and runtime tweaks)."""
    global AUTH_SETTINGS
    AUTH_SETTINGS = _load_auth_settings_from_env()  # Refreshed module-level auth settings singleton.
    return AUTH_SETTINGS


def _is_protected_path(path: str, settings: AuthSettings) -> bool:
    """Return whether the given request path requires bearer auth checks."""
    normalized_path = _normalize_path(path)
    return any(
        normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
        for prefix in settings.protected_path_prefixes
    )


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    """Extract bearer token from Authorization header."""
    if authorization_header is None:
        return None
    value = str(authorization_header).strip()
    if not value:
        return None
    parts = value.split(" ", 1)
    if len(parts) != 2:
        return None
    if parts[0].strip().lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str):
    """Return a cached JWKS client for JWT signature verification."""
    if jwt is None:
        raise RuntimeError("PyJWT is not installed")
    return jwt.PyJWKClient(jwks_url)


def _reject(
    *,
    status_code: int,
    error: str,
    reason: str,
    path: str,
    method: str,
    remote_addr: str,
    mode: str,
) -> AuthDecision:
    """Create a reject decision and write a structured warning log entry."""
    logging.getLogger(__name__).warning(
        "authorization rejected mode=%s method=%s path=%s remote_addr=%s reason=%s",
        mode,
        method,
        path,
        remote_addr or "unknown",
        reason,
    )
    return AuthDecision(
        allowed=False,
        status_code=status_code,
        error=error,
        reason=reason,
    )


def _validate_jwt_token(token: str, settings: AuthSettings) -> Optional[str]:
    """Validate JWT signature and standard claims; return reason on failure."""
    if jwt is None:
        return "jwt mode requires PyJWT dependency"
    if not settings.jwt_jwks_url:
        return "jwt mode requires OPAMP_AUTH_JWT_JWKS_URL or OPAMP_AUTH_JWT_ISSUER"
    try:
        signing_key = _jwks_client(settings.jwt_jwks_url).get_signing_key_from_jwt(token)
        decode_options = {
            "verify_aud": bool(settings.jwt_audience),
            "verify_iss": bool(settings.jwt_issuer),
        }
        jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options=decode_options,
            leeway=settings.jwt_leeway_seconds,
        )
    except Exception as err:  # pragma: no cover - library exception classes vary
        return f"jwt validation failed: {err}"
    return None


def evaluate_bearer_auth(
    *,
    path: str,
    method: str,
    authorization_header: str | None,
    remote_addr: str | None,
) -> AuthDecision:
    """Authorize a request based on current mode and protected-path gating."""
    settings = AUTH_SETTINGS
    if not _is_protected_path(path, settings):
        return AuthDecision(allowed=True)
    return evaluate_required_bearer_auth(
        mode=settings.mode,
        path=path,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
        static_token=settings.static_token,
        jwt_settings=settings,
    )


def evaluate_required_bearer_auth(
    *,
    mode: str,
    path: str,
    method: str,
    authorization_header: str | None,
    remote_addr: str | None,
    static_token: str | None = None,
    jwt_settings: AuthSettings | None = None,
) -> AuthDecision:
    """Authorize a request using bearer validation without protected-path gating."""
    settings = jwt_settings or AUTH_SETTINGS
    if method.upper() == "OPTIONS":
        return AuthDecision(allowed=True)
    if mode == AUTH_MODE_DISABLED:
        return AuthDecision(allowed=True)

    token = _extract_bearer_token(authorization_header)
    if token is None:
        return _reject(
            status_code=HTTPStatus.UNAUTHORIZED,
            error="missing bearer token",
            reason="authorization header missing or malformed",
            path=path,
            method=method,
            remote_addr=str(remote_addr or ""),
            mode=mode,
        )

    if mode == AUTH_MODE_STATIC:
        expected_token = static_token if static_token is not None else settings.static_token
        if not expected_token:
            return _reject(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                error="static auth token is not configured",
                reason="OPAMP_AUTH_STATIC_TOKEN not set",
                path=path,
                method=method,
                remote_addr=str(remote_addr or ""),
                mode=mode,
            )
        if not hmac.compare_digest(token, expected_token):
            return _reject(
                status_code=HTTPStatus.UNAUTHORIZED,
                error="invalid bearer token",
                reason="static token mismatch",
                path=path,
                method=method,
                remote_addr=str(remote_addr or ""),
                mode=mode,
            )
        return AuthDecision(allowed=True)

    if mode == AUTH_MODE_JWT:
        validation_error = _validate_jwt_token(token, settings)
        if validation_error:
            return _reject(
                status_code=HTTPStatus.UNAUTHORIZED,
                error="invalid bearer token",
                reason=validation_error,
                path=path,
                method=method,
                remote_addr=str(remote_addr or ""),
                mode=mode,
            )
        return AuthDecision(allowed=True)

    return _reject(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        error="invalid auth mode configuration",
        reason=f"unsupported auth mode: {mode}",
        path=path,
        method=method,
        remote_addr=str(remote_addr or ""),
        mode=mode,
    )


def build_idp_login_redirect_url(*, return_to: str | None = None) -> str | None:
    """Return an IdP login URL suitable for redirecting browser users."""
    settings = AUTH_SETTINGS
    explicit = settings.idp_login_url
    if explicit:
        if return_to and "redirect_uri=" not in explicit:
            separator = "&" if "?" in explicit else "?"
            return f"{explicit}{separator}redirect_uri={quote(return_to, safe='')}"
        return explicit
    if not settings.jwt_issuer:
        return None
    client_id = settings.idp_client_id or settings.jwt_audience
    if not client_id:
        return None
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": "openid",
    }
    if return_to:
        params["redirect_uri"] = return_to
    return (
        f"{settings.jwt_issuer.rstrip('/')}/protocol/openid-connect/auth"
        f"?{urlencode(params)}"
    )


def evaluate_asgi_scope_auth(scope: dict) -> AuthDecision:
    """Authorize MCP ASGI scope requests."""
    path = str(scope.get("path", "/"))
    method = str(scope.get("method", "GET"))
    raw_headers = scope.get("headers") or []
    authorization_header = None
    for key, value in raw_headers:
        if bytes(key).lower() == b"authorization":
            authorization_header = bytes(value).decode("utf-8", errors="replace")
            break
    remote_addr = ""
    client = scope.get("client")
    if isinstance(client, tuple) and client:
        remote_addr = str(client[0])
    return evaluate_bearer_auth(
        path=path,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
    )
