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

import os
import pathlib
import sys

import pytest


def pytest_configure() -> None:
    root = pathlib.Path(__file__).resolve().parents[2]
    src = root / "provider" / "src"
    for path in (root, src):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.environ.setdefault("OPAMP_CONFIG_PATH", str(root / "tests" / "opamp.json"))


@pytest.fixture(autouse=True)
def disable_auth_by_default(monkeypatch):
    """Keep auth disabled for tests unless a test explicitly enables it."""
    from opamp_provider import auth as provider_auth

    monkeypatch.setenv(provider_auth.ENV_OPAMP_AUTH_MODE, provider_auth.AUTH_MODE_DISABLED)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_STATIC_TOKEN, raising=False)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_JWT_ISSUER, raising=False)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_JWT_AUDIENCE, raising=False)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_JWT_JWKS_URL, raising=False)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_JWT_LEEWAY_SECONDS, raising=False)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_IDP_LOGIN_URL, raising=False)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_IDP_CLIENT_ID, raising=False)
    monkeypatch.delenv(provider_auth.ENV_OPAMP_AUTH_PROTECTED_PATH_PREFIXES, raising=False)
    monkeypatch.setenv(provider_auth.ENV_UI_AUTH_MODE, provider_auth.AUTH_MODE_DISABLED)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_STATIC_TOKEN, raising=False)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_JWT_ISSUER, raising=False)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_JWT_AUDIENCE, raising=False)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_JWT_JWKS_URL, raising=False)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_JWT_LEEWAY_SECONDS, raising=False)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_IDP_LOGIN_URL, raising=False)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_IDP_CLIENT_ID, raising=False)
    monkeypatch.delenv(provider_auth.ENV_UI_AUTH_PROTECTED_PATH_PREFIXES, raising=False)
    provider_auth.reload_auth_settings()
    yield
    provider_auth.reload_auth_settings()
