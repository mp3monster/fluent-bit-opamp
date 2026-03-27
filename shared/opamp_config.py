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

"""Common configuration enums and helpers for OpAMP projects."""

from __future__ import annotations

from enum import IntEnum
import logging
from typing import Any, Iterable


class AgentCapabilities(IntEnum):
    """Agent capability bit flags from OpAMP specification."""

    Unspecified = 0x00000000
    ReportsStatus = 0x00000001
    AcceptsRemoteConfig = 0x00000002
    ReportsEffectiveConfig = 0x00000004
    AcceptsPackages = 0x00000008
    ReportsPackageStatuses = 0x00000010
    ReportsOwnTraces = 0x00000020
    ReportsOwnMetrics = 0x00000040
    ReportsOwnLogs = 0x00000080
    AcceptsOpAMPConnectionSettings = 0x00000100
    AcceptsOtherConnectionSettings = 0x00000200
    AcceptsRestartCommand = 0x00000400
    ReportsHealth = 0x00000800
    ReportsRemoteConfig = 0x00001000
    ReportsHeartbeat = 0x00002000
    ReportsAvailableComponents = 0x00004000
    ReportsConnectionSettingsStatus = 0x00008000


AGENT_CAPABILITIES_MAP: dict[str, int] = {
    name: int(value) for name, value in AgentCapabilities.__members__.items()
}
AGENT_CAPABILITIES_MAP["UnspecifiedAgentCapability"] = int(AgentCapabilities.Unspecified)


class ServerCapabilities(IntEnum):
    """Server capability bit flags from OpAMP specification."""

    Unspecified = 0x00000000
    AcceptsStatus = 0x00000001
    OffersRemoteConfig = 0x00000002
    AcceptsEffectiveConfig = 0x00000004
    OffersPackages = 0x00000008
    AcceptsPackagesStatus = 0x00000010
    OffersConnectionSettings = 0x00000020
    AcceptsConnectionSettingsRequest = 0x00000040


OPAMP_HTTP_PATH = "/v1/opamp"
UTF8_ENCODING = "utf-8"
OPAMP_TRANSPORT_HEADER_NONE = 0
PB_FIELD_INSTANCE_UID = "instance_uid"
PB_FIELD_ERROR_RESPONSE = "error_response"
PB_FIELD_REMOTE_CONFIG = "remote_config"
PB_FIELD_CONNECTION_SETTINGS = "connection_settings"
PB_FIELD_PACKAGES_AVAILABLE = "packages_available"
PB_FIELD_AGENT_IDENTIFICATION = "agent_identification"
PB_FIELD_COMMAND = "command"
PB_FIELD_CUSTOM_CAPABILITIES = "custom_capabilities"
PB_FIELD_CUSTOM_MESSAGE = "custom_message"
PB_FIELD_RETRY_INFO = "retry_info"
PB_FIELD_AGENT_DESCRIPTION = "agent_description"
PB_FIELD_AGENT_DISCONNECT = "agent_disconnect"
PB_FIELD_HEALTH = "health"
PB_FIELD_PACKAGE_STATUSES = "package_statuses"
PB_FIELD_CONNECTION_SETTINGS_REQUEST = "connection_settings_request"
PB_FLAG_REPORT_FULL_STATE = "ReportFullState"


def parse_capabilities(names: Iterable[str], enum_cls: type[IntEnum]) -> int:
    """Convert capability names into a bitmask for the given enum class."""
    mask = 0
    if not isinstance(names, Iterable):
        logging.getLogger(__name__).warning("unknown capability: %s", names)
    else:
        for name in names:
            try:
                mask |= int(enum_cls[name])
            except KeyError:
                logging.getLogger(__name__).warning("unknown capability: %s", name)
    return mask


def anyvalue_to_string(value: Any) -> str | None:
    """Convert a protobuf AnyValue-like object into a string representation."""
    kind = value.WhichOneof("value")
    if kind == "string_value":
        return value.string_value
    if kind == "bytes_value":
        return value.bytes_value.hex()
    if kind == "int_value":
        return str(value.int_value)
    if kind == "bool_value":
        return "true" if value.bool_value else "false"
    if kind == "double_value":
        return str(value.double_value)
    return None
