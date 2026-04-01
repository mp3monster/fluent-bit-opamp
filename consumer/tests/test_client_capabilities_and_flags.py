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

import logging

import opamp_consumer.fluentbit_client as client
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.fluentbit_client import CAPABILITIES_MAP, CONFIG_DOCS_URL
from opamp_consumer.proto import opamp_pb2


def _set_config(agent_capabilities) -> None:
    """Install a test config with the requested agent capabilities."""
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path="unused",
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=agent_capabilities,
        log_level="debug",
        service_name="Fluentbit",
        service_namespace="FluentBitNS",
    )
    client.CONFIG = config


def test_get_agent_capabilities_from_names(caplog) -> None:
    """Return a bitmask built from the hardwired required capabilities."""
    _set_config(["ReportsStatus", "ReportsHealth", "ReportsHeartbeat"])
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost")

    mask = instance.get_agent_capabilities()
    expected = (
        CAPABILITIES_MAP["ReportsStatus"]
        | CAPABILITIES_MAP["AcceptsRestartCommand"]
        | CAPABILITIES_MAP["ReportsHealth"]
    )
    assert mask == expected
    assert "unknown agent capability" not in caplog.text


def test_get_agent_capabilities_warns_unknown(caplog) -> None:
    """Ignore config capability values and always return the required capability mask."""
    _set_config(["ReportsStatus", "UnknownCapability"])
    caplog.set_level(logging.WARNING)
    instance = client.OpAMPClient("http://localhost")

    mask = instance.get_agent_capabilities()
    assert mask == (
        CAPABILITIES_MAP["ReportsStatus"]
        | CAPABILITIES_MAP["AcceptsRestartCommand"]
        | CAPABILITIES_MAP["ReportsHealth"]
    )
    assert "unknown agent capability" not in caplog.text


def test_get_config_parameters_includes_docs_url() -> None:
    """Return config parameters plus documentation URL reference."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    config_params = instance.get_config_parameters()
    assert config_params["server_url"] == "http://localhost"
    assert config_params["documentation_url"] == CONFIG_DOCS_URL


def test_reporting_flags_default_to_true() -> None:
    """OpAMPClientData should default all ReportingFlag values to True."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    assert instance.data.reporting_flags
    assert set(instance.data.reporting_flags.keys()) == set(client.ReportingFlag)
    assert all(instance.data.reporting_flags.values())


def test_reporting_flags_setall_updates_all_values() -> None:
    """set_all_reporting_flags should apply the given value to all reporting flags."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")

    instance.data.set_all_reporting_flags(False)
    assert all(value is False for value in instance.data.reporting_flags.values())

    instance.data.set_all_reporting_flags()
    assert all(value is True for value in instance.data.reporting_flags.values())


def test_reportingflag_setall_updates_all_values() -> None:
    """ReportingFlag.set_all_reporting_flags should update every flag entry in-place."""
    flags = {flag: True for flag in client.ReportingFlag}
    client.ReportingFlag.set_all_reporting_flags(flags, False)
    assert all(value is False for value in flags.values())


def test_handle_flags_logs_names_and_sets_all_for_report_full_state(caplog) -> None:
    """handle_flags should decode names and set all flags when ReportFullState is present."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.set_all_flags(False)
    caplog.set_level(logging.INFO)

    instance.handle_flags(
        opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportFullState
        | opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportAvailableComponents
    )

    assert all(instance.data.reporting_flags.values())
    assert "ReportFullState" in caplog.text
    assert "ReportAvailableComponents" in caplog.text


def test_handle_flags_without_report_full_state_does_not_set_all() -> None:
    """handle_flags should not force-enable reporting flags without ReportFullState."""
    _set_config(["ReportsStatus"])
    instance = client.OpAMPClient("http://localhost")
    instance.data.set_all_flags(False)

    instance.handle_flags(
        opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportAvailableComponents
    )

    assert not any(instance.data.reporting_flags.values())
