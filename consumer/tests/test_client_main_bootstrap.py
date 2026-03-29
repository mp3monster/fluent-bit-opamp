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

import json

import opamp_consumer.client as client
from opamp_consumer.client import CONFIG_DOCS_URL
from opamp_consumer.config import ConsumerConfig


def test_main_help_prints_config_parameters_and_skips_client(
    monkeypatch, capsys
) -> None:
    """`--help` should print config parameters and skip creating OpAMPClient."""
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path="unused",
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=["ReportsStatus"],
        log_level="debug",
    )
    monkeypatch.setattr(
        client.consumer_config, "load_config_with_overrides", lambda **_: config
    )
    monkeypatch.setattr(
        client,
        "OpAMPClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("OpAMPClient should not be created for --help")
        ),
    )
    monkeypatch.setattr(client.sys, "argv", ["client.py", "--help"])

    client.main()

    out = capsys.readouterr().out
    json_start = out.find("{")
    assert json_start >= 0
    payload = json.loads(out[json_start:])
    assert payload["server_url"] == "http://localhost"
    assert payload["documentation_url"] == CONFIG_DOCS_URL
