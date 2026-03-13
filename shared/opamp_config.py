"""Common configuration enums and helpers for OpAMP projects."""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable
import logging


class AgentCapabilities(IntEnum):
    """Agent capability bit flags from OpAMP specification."""

    # The capabilities field is unspecified.
    Unspecified = 0x00000000
    # The Agent can report status (required).
    ReportsStatus = 0x00000001
    # The Agent can accept remote configuration from the Server.
    AcceptsRemoteConfig = 0x00000002
    # The Agent will report EffectiveConfig in AgentToServer.
    ReportsEffectiveConfig = 0x00000004
    # The Agent can accept package offers.
    AcceptsPackages = 0x00000008
    # The Agent can report package status.
    ReportsPackageStatuses = 0x00000010
    # The Agent can report own traces via connection settings.
    ReportsOwnTraces = 0x00000020
    # The Agent can report own metrics via connection settings.
    ReportsOwnMetrics = 0x00000040
    # The Agent can report own logs via connection settings.
    ReportsOwnLogs = 0x00000080
    # The Agent can accept OpAMP connection settings.
    AcceptsOpAMPConnectionSettings = 0x00000100
    # The Agent can accept other connection settings.
    AcceptsOtherConnectionSettings = 0x00000200
    # The Agent can accept restart commands.
    AcceptsRestartCommand = 0x00000400
    # The Agent will report health.
    ReportsHealth = 0x00000800
    # The Agent will report remote config status.
    ReportsRemoteConfig = 0x00001000
    # The Agent can report heartbeats.
    ReportsHeartbeat = 0x00002000
    # The Agent will report available components.
    ReportsAvailableComponents = 0x00004000
    # The Agent will report connection settings status.
    ReportsConnectionSettingsStatus = 0x00008000


class ServerCapabilities(IntEnum):
    """Server capability bit flags from OpAMP specification."""

    # The capabilities field is unspecified.
    Unspecified = 0x00000000
    # The Server can accept status reports (required).
    AcceptsStatus = 0x00000001
    # The Server can offer remote configuration to the Agent.
    OffersRemoteConfig = 0x00000002
    # The Server can accept EffectiveConfig in AgentToServer.
    AcceptsEffectiveConfig = 0x00000004
    # The Server can offer packages.
    OffersPackages = 0x00000008
    # The Server can accept package status.
    AcceptsPackagesStatus = 0x00000010
    # The Server can offer connection settings.
    OffersConnectionSettings = 0x00000020
    # The Server can accept connection settings requests.
    AcceptsConnectionSettingsRequest = 0x00000040


OPAMP_HTTP_PATH = "/v1/opamp"  # Standard OpAMP HTTP/WebSocket path.
UTF8_ENCODING = "utf-8"  # Default UTF-8 encoding name.
OPAMP_TRANSPORT_HEADER_NONE = 0  # OpAMP transport header value for "no header".


def parse_capabilities(names: Iterable[str], enum_cls: type[IntEnum]) -> int:
    """Convert capability names into a bitmask for the given enum class."""
    mask = 0
    if not isinstance(names, Iterable):
        logging.getLogger(__name__).warning(f"unknown capability: {names}")
    else:
        for name in names:
            try:
                mask |= int(enum_cls[name])
            except KeyError:
                logging.getLogger(__name__).warning(f"unknown capability: {name}")
    return mask
