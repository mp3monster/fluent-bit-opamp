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

import sys

from opamp_provider import config as provider_config
from opamp_provider.config import ProviderConfig
from opamp_provider import server as provider_server


def test_server_main_invokes_app(monkeypatch) -> None:
    called = {}

    def fake_run(*, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    def fake_load_config_with_overrides(*, config_path):
        return ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8080,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=50,
        )

    def fake_set_config(config):
        called["config"] = config

    monkeypatch.setattr(provider_server.app, "run", fake_run)
    monkeypatch.setattr(provider_config, "load_config_with_overrides", fake_load_config_with_overrides)
    monkeypatch.setattr(provider_config, "set_config", fake_set_config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--host", "0.0.0.0", "--port", "9999"],
    )

    provider_server.main()

    assert called["host"] == "0.0.0.0"
    assert called["port"] == 9999
    assert isinstance(called["config"], ProviderConfig)
