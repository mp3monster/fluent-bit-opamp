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

"""Helpers for building outbound AgentToServer payloads."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

from opamp_consumer.proto import opamp_pb2
from opamp_consumer.reporting_flag import ReportingFlag


def populate_agent_to_server(
    *,
    data: Any,
    msg: opamp_pb2.AgentToServer,
    get_agent_description: Callable[[], opamp_pb2.AgentDescription],
    get_agent_capabilities: Callable[[], int],
    get_custom_capabilities_payload: Callable[[], opamp_pb2.CustomCapabilities],
    populate_agent_to_server_health: Callable[
        [opamp_pb2.AgentToServer], opamp_pb2.AgentToServer
    ],
) -> opamp_pb2.AgentToServer:
    """Populate outbound AgentToServer fields based on reporting flags."""
    msg.sequence_num = data.msg_sequence_number
    data.msg_sequence_number = data.msg_sequence_number + 1
    msg.instance_uid = data.uid_instance

    if data.reporting_flags[ReportingFlag.REPORT_DESCRIPTION]:
        msg.agent_description.CopyFrom(get_agent_description())
        data.reporting_flags[ReportingFlag.REPORT_DESCRIPTION] = False

    if data.reporting_flags[ReportingFlag.REPORT_CAPABILITIES]:
        msg.capabilities = get_agent_capabilities()
        data.reporting_flags[ReportingFlag.REPORT_CAPABILITIES] = False

    if data.reporting_flags[ReportingFlag.REPORT_CUSTOM_CAPABILITIES]:
        custom_capabilities = get_custom_capabilities_payload()
        if custom_capabilities.capabilities:
            msg.custom_capabilities.CopyFrom(custom_capabilities)
        data.reporting_flags[ReportingFlag.REPORT_CUSTOM_CAPABILITIES] = False

    if data.reporting_flags[ReportingFlag.REPORT_HEALTH]:
        msg = populate_agent_to_server_health(msg)
        data.reporting_flags[ReportingFlag.REPORT_HEALTH] = False
    return msg


def populate_agent_to_server_health(
    *,
    data: Any,
    msg: opamp_pb2.AgentToServer,
    health_from_metrics: Callable[[opamp_pb2.AgentToServer, str], opamp_pb2.AgentToServer],
    health_key: str,
    err_prefix: str,
    value_heartbeat_status: str,
    value_supervisor_no_state: str,
) -> opamp_pb2.AgentToServer:
    """Populate health fields on AgentToServer using latest heartbeat poll state."""
    healthy = True
    if data.last_heartbeat_results:
        healthy = (
            data.last_heartbeat_http_codes is not None
            and data.last_heartbeat_http_codes[health_key]
        )
        last_error = ""
        for value in data.last_heartbeat_results.values():
            text = str(value)
            if text.startswith(err_prefix):
                healthy = False
                last_error = text

            msg = health_from_metrics(msg, text)

        msg.health.status = value_heartbeat_status
        if not healthy and last_error:
            msg.health.last_error = last_error
    else:
        healthy = False
        msg.health.last_error = value_supervisor_no_state

    msg.health.start_time_unix_nano = time.time_ns() - data.launched_at
    msg.health.status_time_unix_nano = time.time_ns()
    msg.health.healthy = int(healthy)
    logging.getLogger(__name__).debug("Health info sending is >%s<", msg.health)
    return msg


def parse_fluentbit_metrics_health(
    msg: opamp_pb2.AgentToServer,
    text: str,
) -> opamp_pb2.AgentToServer:
    """Parse Fluent Bit metrics text and update component health entries in-place."""
    lines = text.splitlines()
    metric_pattern: str = 'errors_total{name="'
    for line in lines:
        line_idx = line.find(metric_pattern)
        if line_idx >= 0:
            name_start: int = line_idx + len(metric_pattern)
            name_end: int = line.index('"', name_start)
            component_name: str = line[name_start:name_end]
            last_num_text = re.findall(r"\d+(?:\.\d+)?", line[name_end:])[-1]
            last_num = int(last_num_text)
            msg.health.component_health_map[component_name].CopyFrom(
                opamp_pb2.ComponentHealth(
                    healthy=(last_num == 0),
                    status=f"error count={last_num_text}",
                )
            )
            logging.getLogger(__name__).debug(
                "Component metric %s",
                msg.health.component_health_map[component_name],
            )
    return msg
