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

ENV_OPAMP_AUTH_MODE = "OPAMP_AUTH_MODE"  # Environment variable selecting OpAMP auth mode.
ENV_OPAMP_AUTH_PROTECTED_PATH_PREFIXES = "OPAMP_AUTH_PROTECTED_PATH_PREFIXES"  # Environment variable listing OpAMP protected path prefixes.
ENV_OPAMP_AUTH_STATIC_TOKEN = "OPAMP_AUTH_STATIC_TOKEN"  # Environment variable holding OpAMP static bearer token value.
ENV_OPAMP_AUTH_JWT_ISSUER = "OPAMP_AUTH_JWT_ISSUER"  # Environment variable for expected OpAMP JWT issuer claim.
ENV_OPAMP_AUTH_JWT_AUDIENCE = "OPAMP_AUTH_JWT_AUDIENCE"  # Environment variable for expected OpAMP JWT audience claim.
ENV_OPAMP_AUTH_JWT_JWKS_URL = "OPAMP_AUTH_JWT_JWKS_URL"  # Environment variable for OpAMP JWKS endpoint URL.
ENV_OPAMP_AUTH_JWT_LEEWAY_SECONDS = "OPAMP_AUTH_JWT_LEEWAY_SECONDS"  # Environment variable for OpAMP JWT clock-skew leeway.
ENV_OPAMP_AUTH_IDP_LOGIN_URL = "OPAMP_AUTH_IDP_LOGIN_URL"  # Optional explicit OpAMP IdP login URL used for browser redirects.
ENV_OPAMP_AUTH_IDP_CLIENT_ID = "OPAMP_AUTH_IDP_CLIENT_ID"  # Optional OpAMP IdP client id used when deriving login URL from issuer.

ENV_UI_AUTH_MODE = "UI_AUTH_MODE"  # Environment variable selecting non-OpAMP auth mode.
ENV_UI_AUTH_PROTECTED_PATH_PREFIXES = "UI_AUTH_PROTECTED_PATH_PREFIXES"  # Environment variable listing non-OpAMP protected path prefixes.
ENV_UI_AUTH_STATIC_TOKEN = "UI_AUTH_STATIC_TOKEN"  # Environment variable holding non-OpAMP static bearer token value.
ENV_UI_AUTH_JWT_ISSUER = "UI_AUTH_JWT_ISSUER"  # Environment variable for expected non-OpAMP JWT issuer claim.
ENV_UI_AUTH_JWT_AUDIENCE = "UI_AUTH_JWT_AUDIENCE"  # Environment variable for expected non-OpAMP JWT audience claim.
ENV_UI_AUTH_JWT_JWKS_URL = "UI_AUTH_JWT_JWKS_URL"  # Environment variable for non-OpAMP JWKS endpoint URL.
ENV_UI_AUTH_JWT_LEEWAY_SECONDS = "UI_AUTH_JWT_LEEWAY_SECONDS"  # Environment variable for non-OpAMP JWT clock-skew leeway.
ENV_UI_AUTH_IDP_LOGIN_URL = "UI_AUTH_IDP_LOGIN_URL"  # Optional explicit non-OpAMP IdP login URL.
ENV_UI_AUTH_IDP_CLIENT_ID = "UI_AUTH_IDP_CLIENT_ID"  # Optional non-OpAMP IdP client id used when deriving login URL from issuer.

# Backward-compatible aliases preserved for existing callers/tests.
ENV_AUTH_MODE = ENV_OPAMP_AUTH_MODE
ENV_AUTH_PROTECTED_PATH_PREFIXES = ENV_OPAMP_AUTH_PROTECTED_PATH_PREFIXES
ENV_AUTH_STATIC_TOKEN = ENV_OPAMP_AUTH_STATIC_TOKEN
ENV_AUTH_JWT_ISSUER = ENV_OPAMP_AUTH_JWT_ISSUER
ENV_AUTH_JWT_AUDIENCE = ENV_OPAMP_AUTH_JWT_AUDIENCE
ENV_AUTH_JWT_JWKS_URL = ENV_OPAMP_AUTH_JWT_JWKS_URL
ENV_AUTH_JWT_LEEWAY_SECONDS = ENV_OPAMP_AUTH_JWT_LEEWAY_SECONDS
ENV_AUTH_IDP_LOGIN_URL = ENV_OPAMP_AUTH_IDP_LOGIN_URL
ENV_AUTH_IDP_CLIENT_ID = ENV_OPAMP_AUTH_IDP_CLIENT_ID

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
    static_token_env_var: str = ENV_OPAMP_AUTH_STATIC_TOKEN
    jwt_issuer_env_var: str = ENV_OPAMP_AUTH_JWT_ISSUER
    jwt_jwks_url_env_var: str = ENV_OPAMP_AUTH_JWT_JWKS_URL


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


def _load_auth_settings_from_env(
    *,
    mode_env_var: str,
    protected_prefixes_env_var: str,
    static_token_env_var: str,
    jwt_issuer_env_var: str,
    jwt_audience_env_var: str,
    jwt_jwks_url_env_var: str,
    jwt_leeway_env_var: str,
    idp_login_url_env_var: str,
    idp_client_id_env_var: str,
) -> AuthSettings:
    """Load auth settings from a configured environment-variable namespace."""
    raw_mode = str(os.environ.get(mode_env_var, DEFAULT_AUTH_MODE)).strip().lower()
    mode = (
        raw_mode
        if raw_mode in {AUTH_MODE_DISABLED, AUTH_MODE_STATIC, AUTH_MODE_JWT}
        else DEFAULT_AUTH_MODE
    )
    raw_prefixes = os.environ.get(protected_prefixes_env_var, "")
    if raw_prefixes.strip():
        protected_path_prefixes = _normalize_prefixes(raw_prefixes.split(","))
    else:
        protected_path_prefixes = DEFAULT_PROTECTED_PATH_PREFIXES
    jwt_issuer = str(os.environ.get(jwt_issuer_env_var, "")).strip() or None
    jwt_jwks_url = str(os.environ.get(jwt_jwks_url_env_var, "")).strip() or None
    if jwt_jwks_url is None:
        jwt_jwks_url = _derive_default_jwks_url(jwt_issuer)
    try:
        jwt_leeway_seconds = max(
            0,
            int(os.environ.get(jwt_leeway_env_var, "30")),
        )
    except ValueError:
        jwt_leeway_seconds = 30
    return AuthSettings(
        mode=mode,
        protected_path_prefixes=protected_path_prefixes,
        static_token=str(os.environ.get(static_token_env_var, "")).strip() or None,
        jwt_issuer=jwt_issuer,
        jwt_audience=str(os.environ.get(jwt_audience_env_var, "")).strip() or None,
        jwt_jwks_url=jwt_jwks_url,
        jwt_leeway_seconds=jwt_leeway_seconds,
        idp_login_url=str(os.environ.get(idp_login_url_env_var, "")).strip() or None,
        idp_client_id=str(os.environ.get(idp_client_id_env_var, "")).strip() or None,
        static_token_env_var=static_token_env_var,
        jwt_issuer_env_var=jwt_issuer_env_var,
        jwt_jwks_url_env_var=jwt_jwks_url_env_var,
    )


OPAMP_AUTH_SETTINGS = _load_auth_settings_from_env(
    mode_env_var=ENV_OPAMP_AUTH_MODE,
    protected_prefixes_env_var=ENV_OPAMP_AUTH_PROTECTED_PATH_PREFIXES,
    static_token_env_var=ENV_OPAMP_AUTH_STATIC_TOKEN,
    jwt_issuer_env_var=ENV_OPAMP_AUTH_JWT_ISSUER,
    jwt_audience_env_var=ENV_OPAMP_AUTH_JWT_AUDIENCE,
    jwt_jwks_url_env_var=ENV_OPAMP_AUTH_JWT_JWKS_URL,
    jwt_leeway_env_var=ENV_OPAMP_AUTH_JWT_LEEWAY_SECONDS,
    idp_login_url_env_var=ENV_OPAMP_AUTH_IDP_LOGIN_URL,
    idp_client_id_env_var=ENV_OPAMP_AUTH_IDP_CLIENT_ID,
)  # Module-level OpAMP auth settings singleton loaded from environment.
UI_AUTH_SETTINGS = _load_auth_settings_from_env(
    mode_env_var=ENV_UI_AUTH_MODE,
    protected_prefixes_env_var=ENV_UI_AUTH_PROTECTED_PATH_PREFIXES,
    static_token_env_var=ENV_UI_AUTH_STATIC_TOKEN,
    jwt_issuer_env_var=ENV_UI_AUTH_JWT_ISSUER,
    jwt_audience_env_var=ENV_UI_AUTH_JWT_AUDIENCE,
    jwt_jwks_url_env_var=ENV_UI_AUTH_JWT_JWKS_URL,
    jwt_leeway_env_var=ENV_UI_AUTH_JWT_LEEWAY_SECONDS,
    idp_login_url_env_var=ENV_UI_AUTH_IDP_LOGIN_URL,
    idp_client_id_env_var=ENV_UI_AUTH_IDP_CLIENT_ID,
)  # Module-level UI auth settings singleton loaded from environment.
AUTH_SETTINGS = OPAMP_AUTH_SETTINGS  # Backward-compatible alias for legacy callers.


def reload_opamp_auth_settings() -> AuthSettings:
    """Reload environment-backed OpAMP auth settings."""
    global OPAMP_AUTH_SETTINGS, AUTH_SETTINGS
    OPAMP_AUTH_SETTINGS = _load_auth_settings_from_env(
        mode_env_var=ENV_OPAMP_AUTH_MODE,
        protected_prefixes_env_var=ENV_OPAMP_AUTH_PROTECTED_PATH_PREFIXES,
        static_token_env_var=ENV_OPAMP_AUTH_STATIC_TOKEN,
        jwt_issuer_env_var=ENV_OPAMP_AUTH_JWT_ISSUER,
        jwt_audience_env_var=ENV_OPAMP_AUTH_JWT_AUDIENCE,
        jwt_jwks_url_env_var=ENV_OPAMP_AUTH_JWT_JWKS_URL,
        jwt_leeway_env_var=ENV_OPAMP_AUTH_JWT_LEEWAY_SECONDS,
        idp_login_url_env_var=ENV_OPAMP_AUTH_IDP_LOGIN_URL,
        idp_client_id_env_var=ENV_OPAMP_AUTH_IDP_CLIENT_ID,
    )
    AUTH_SETTINGS = OPAMP_AUTH_SETTINGS
    return OPAMP_AUTH_SETTINGS


def reload_ui_auth_settings() -> AuthSettings:
    """Reload environment-backed UI auth settings."""
    global UI_AUTH_SETTINGS
    UI_AUTH_SETTINGS = _load_auth_settings_from_env(
        mode_env_var=ENV_UI_AUTH_MODE,
        protected_prefixes_env_var=ENV_UI_AUTH_PROTECTED_PATH_PREFIXES,
        static_token_env_var=ENV_UI_AUTH_STATIC_TOKEN,
        jwt_issuer_env_var=ENV_UI_AUTH_JWT_ISSUER,
        jwt_audience_env_var=ENV_UI_AUTH_JWT_AUDIENCE,
        jwt_jwks_url_env_var=ENV_UI_AUTH_JWT_JWKS_URL,
        jwt_leeway_env_var=ENV_UI_AUTH_JWT_LEEWAY_SECONDS,
        idp_login_url_env_var=ENV_UI_AUTH_IDP_LOGIN_URL,
        idp_client_id_env_var=ENV_UI_AUTH_IDP_CLIENT_ID,
    )
    return UI_AUTH_SETTINGS


def reload_auth_settings() -> AuthSettings:
    """Reload both OpAMP and UI environment-backed auth settings."""
    reload_opamp_auth_settings()
    reload_ui_auth_settings()
    return OPAMP_AUTH_SETTINGS


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
        return (
            f"jwt mode requires {settings.jwt_jwks_url_env_var} "
            f"or {settings.jwt_issuer_env_var}"
        )
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
                reason=f"{settings.static_token_env_var} not set",
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


def build_idp_login_redirect_url(
    *,
    return_to: str | None = None,
    settings: AuthSettings | None = None,
) -> str | None:
    """Return an IdP login URL suitable for redirecting browser users."""
    effective = settings or AUTH_SETTINGS
    explicit = effective.idp_login_url
    if explicit:
        if return_to and "redirect_uri=" not in explicit:
            separator = "&" if "?" in explicit else "?"
            return f"{explicit}{separator}redirect_uri={quote(return_to, safe='')}"
        return explicit
    if not effective.jwt_issuer:
        return None
    client_id = effective.idp_client_id or effective.jwt_audience
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
        f"{effective.jwt_issuer.rstrip('/')}/protocol/openid-connect/auth"
        f"?{urlencode(params)}"
    )


def _scope_auth_inputs(scope: dict) -> tuple[str, str, str | None, str]:
    """Extract auth-relevant ASGI scope values (path, method, auth header, remote addr)."""
    path = str(scope.get("path", "/"))
    scope_type = str(scope.get("type", "")).strip().lower()
    default_method = "WEBSOCKET" if scope_type == "websocket" else "GET"
    method = str(scope.get("method", default_method))
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
    return path, method, authorization_header, remote_addr


def evaluate_required_asgi_scope_auth(
    scope: dict,
    *,
    mode: str,
    static_token: str | None = None,
    jwt_settings: AuthSettings | None = None,
) -> AuthDecision:
    """Authorize an ASGI scope using required bearer validation (no path-prefix gating)."""
    path, method, authorization_header, remote_addr = _scope_auth_inputs(scope)
    return evaluate_required_bearer_auth(
        mode=mode,
        path=path,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
        static_token=static_token,
        jwt_settings=jwt_settings,
    )


def evaluate_asgi_scope_auth(scope: dict) -> AuthDecision:
    """Authorize MCP ASGI scope requests using legacy OPAMP_AUTH_* protected-path gating."""
    path, method, authorization_header, remote_addr = _scope_auth_inputs(scope)
    return evaluate_bearer_auth(
        path=path,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
    )
