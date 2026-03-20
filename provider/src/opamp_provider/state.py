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

"""In-memory client state for the OpAMP provider."""

from __future__ import annotations

import threading
import logging
import re
from enum import Enum
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from google.protobuf import text_format
from pydantic import BaseModel, ConfigDict, Field

from opamp_provider.command_record import CommandRecord
from opamp_provider.proto import opamp_pb2
from shared.uuid_utils import generate_uuid7_bytes


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _anyvalue_to_string(value: opamp_pb2.AnyValue) -> Optional[str]:
    """Convert a protobuf AnyValue into a string representation."""
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


def _extract_agent_version(agent_msg: opamp_pb2.AgentToServer) -> Optional[str]:
    """Extract the agent service.version string from the agent description."""
    agent_desc = agent_msg.agent_description
    if not agent_desc.identifying_attributes:
        return None
    for item in agent_desc.identifying_attributes:
        if item.key == "service.version":
            return _anyvalue_to_string(item.value)
    return None


def _capabilities_from_mask(mask: int) -> list[str]:
    """Decode an agent capability bitmask into enum names."""
    capabilities: list[str] = []
    logging.getLogger(__name__).debug(f"Decoding capability --> {mask}")
    for enum_value in opamp_pb2.AgentCapabilities.DESCRIPTOR.values:
        if enum_value.number == 0:
            continue
        if mask & enum_value.number:
            raw_name = enum_value.name
            if raw_name.startswith("AgentCapabilities_"):
                raw_name = raw_name[len("AgentCapabilities_") :]
            spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", raw_name)
            spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
            capabilities.append(spaced)
            logging.getLogger(__name__).debug(
                f"Capabilities include --> {capabilities[-1]}"
            )
    return capabilities


class ClientChannel(str, Enum):
    """Allowed transport channel values stored on ClientRecord."""

    HTTP = "HTTP"
    WEBSOCKET = "websocket"


class ClientRecord(BaseModel):
    """Snapshot of provider-side state for one connected (or known) client."""

    model_config = ConfigDict(frozen=False)

    client_id: str = Field(description="Unique client identifier (hex-encoded instance UID).")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Decoded list of agent capabilities currently reported by the client.",
    )
    agent_description: Optional[str] = Field(
        default=None,
        description="Text representation of the latest AgentDescription payload.",
    )
    node_age_seconds: Optional[float] = Field(
        default=None,
        description="Elapsed seconds since the provider first observed this client.",
    )
    last_communication: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the most recent AgentToServer message from this client.",
    )
    last_channel: Optional[ClientChannel] = Field(
        default=None,
        description="Last transport channel used by this client (for example HTTP or WebSocket).",
    )
    current_config: Optional[str] = Field(
        default=None,
        description="Latest effective/current config reported by the client.",
    )
    current_config_version: Optional[str] = Field(
        default=None,
        description="Version identifier for current_config when provided by the client.",
    )
    requested_config: Optional[str] = Field(
        default=None,
        description="Most recently requested config payload queued by the provider.",
    )
    requested_config_version: Optional[str] = Field(
        default=None,
        description="Version identifier attached to requested_config.",
    )
    requested_config_apply_at: Optional[datetime] = Field(
        default=None,
        description="Optional timestamp indicating when requested_config should be applied.",
    )
    client_version: Optional[str] = Field(
        default=None,
        description="Client software version extracted from service.version in agent description.",
    )
    features: list[str] = Field(
        default_factory=list,
        description="Feature flags or capabilities tracked outside OpAMP capability bits.",
    )
    commands: list[CommandRecord] = Field(
        default_factory=list,
        description="Queued command records for this client, including sent/unsent state.",
    )
    events: list[dict[str, str]] = Field(
        default_factory=list,
        description="Recent event log entries as {timestamp: description} maps.",
    )
    next_actions: Optional[list[str]] = Field(
        default=None,
        description="Ordered list of server next-actions to apply on upcoming client check-ins.",
    )
    next_expected_communication: Optional[datetime] = Field(
        default=None,
        description="Predicted next communication timestamp based on heartbeat behavior.",
    )
    first_seen: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp when this client record was first created in the store.",
    )
    component_health: Optional[dict[str, dict[str, Optional[str]]]] = Field(
        default=None,
        description="Latest flattened component health map keyed by component name.",
    )
    health: Optional[dict[str, Optional[str] | dict[str, dict[str, Optional[str]]]]] = (
        Field(
            default=None,
            description="Latest top-level health payload including component health map.",
        )
    )
    disconnected: bool = Field(
        default=False,
        description="Whether the client has sent an agent_disconnect notification.",
    )
    disconnected_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the client was marked disconnected.",
    )
    pending_agent_identification: Optional[bytes] = Field(
        default=None,
        description="Queued replacement instance UID to send in AgentIdentification.",
    )


class ClientStore:
    def __init__(self) -> None:
        """Initialize the in-memory client store."""
        self._lock = threading.Lock()
        self._clients: dict[str, ClientRecord] = {}

    def get(self, client_id: str) -> Optional[ClientRecord]:
        """Return a client record by ID if it exists."""
        with self._lock:
            return self._clients.get(client_id)

    def list(self) -> list[ClientRecord]:
        """Return a snapshot list of all client records."""
        with self._lock:
            return list(self._clients.values())

    def upsert_from_agent_msg(
        self, agent_msg: opamp_pb2.AgentToServer, *, channel: Optional[str] = None
    ) -> ClientRecord:
        """Create or update a client record from an AgentToServer message."""
        client_id = (
            agent_msg.instance_uid.hex() if agent_msg.instance_uid else "unknown"
        )
        now = _utc_now()
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            self._apply_comm_metadata(record, now, channel)
            self._apply_capabilities(record, agent_msg)
            self._apply_client_version(record, agent_msg)
            self._apply_health(record, agent_msg)
            self._apply_agent_description(record, agent_msg)
            self._apply_disconnect(record, agent_msg, now)
        return record

    def _apply_comm_metadata(
        self, record: ClientRecord, now: datetime, channel: Optional[str]
    ) -> None:
        """Apply last communication metadata to the client record."""
        record.last_communication = now
        if channel:
            normalized = channel.strip().lower()
            if normalized == ClientChannel.HTTP.value.lower():
                record.last_channel = ClientChannel.HTTP
            elif normalized == ClientChannel.WEBSOCKET.value.lower():
                record.last_channel = ClientChannel.WEBSOCKET
        record.node_age_seconds = (now - record.first_seen).total_seconds()

    def _apply_capabilities(
        self, record: ClientRecord, agent_msg: opamp_pb2.AgentToServer
    ) -> None:
        """Apply agent capability bitmask to the record."""
        record.capabilities = _capabilities_from_mask(agent_msg.capabilities)

    def _apply_client_version(
        self, record: ClientRecord, agent_msg: opamp_pb2.AgentToServer
    ) -> None:
        """Apply the client version extracted from the agent description."""
        record.client_version = _extract_agent_version(agent_msg)

    def _apply_health(
        self, record: ClientRecord, agent_msg: opamp_pb2.AgentToServer
    ) -> None:
        """Apply agent health and component health maps when provided."""
        if not agent_msg.HasField("health"):
            return
        component_health = {
            name: {
                "healthy": str(value.healthy),
                "status": value.status or None,
                "last_error": value.last_error or None,
                "start_time_unix_nano": str(value.start_time_unix_nano or 0),
                "status_time_unix_nano": str(value.status_time_unix_nano or 0),
            }
            for name, value in agent_msg.health.component_health_map.items()
        }
        record.component_health = component_health
        record.health = {
            "healthy": str(agent_msg.health.healthy),
            "status": agent_msg.health.status or None,
            "last_error": agent_msg.health.last_error or None,
            "start_time_unix_nano": str(agent_msg.health.start_time_unix_nano or 0),
            "status_time_unix_nano": str(
                agent_msg.health.status_time_unix_nano or 0
            ),
            "component_health_map": component_health,
        }

    def _apply_agent_description(
        self, record: ClientRecord, agent_msg: opamp_pb2.AgentToServer
    ) -> None:
        """Apply agent description text to the record."""
        if agent_msg.HasField("agent_description"):
            record.agent_description = text_format.MessageToString(
                agent_msg.agent_description
            )

    def _apply_disconnect(
        self, record: ClientRecord, agent_msg: opamp_pb2.AgentToServer, now: datetime
    ) -> None:
        """Mark a record as disconnected when an agent disconnect is received."""
        if agent_msg.HasField("agent_disconnect"):
            record.disconnected = True
            record.disconnected_at = now

    def queue_command(
        self,
        client_id: str,
        *,
        classifier: str,
        action: str,
        key_value_pairs: list[dict[str, str]],
    ) -> CommandRecord:
        """Queue a command for a client and return the command record."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            cmd = CommandRecord(
                command=action,
                classifier=classifier,
                action=action,
                key_value_pairs=key_value_pairs,
            )
            record.commands.append(cmd)
            return cmd

    def set_requested_config(
        self,
        client_id: str,
        *,
        config_text: str,
        version: Optional[str],
        apply_at: Optional[datetime],
    ) -> ClientRecord:
        """Store a requested configuration payload for a client."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            record.requested_config = config_text
            record.requested_config_version = version
            record.requested_config_apply_at = apply_at
            return record

    def set_next_actions(
        self, client_id: str, actions: Optional[list[str]]
    ) -> ClientRecord:
        """Set the next actions to be sent to a client."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            record.next_actions = actions if actions else None
            return record

    def add_event(
        self, client_id: str, *, description: str, max_events: int
    ) -> ClientRecord:
        """Append an event and retain only the latest max_events entries."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            event_time = _utc_now().isoformat()
            record.events.append({event_time: description})
            keep = max(1, int(max_events))
            if len(record.events) > keep:
                record.events = record.events[-keep:]
            return record

    def next_pending_command(self, client_id: str) -> Optional[CommandRecord]:
        """Return the next unsent command for a client, if any."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return None
            for cmd in record.commands:
                if cmd.sent_at is None:
                    return cmd
        return None

    def mark_command_sent(self, client_id: str, command: CommandRecord) -> None:
        """Mark a queued command as sent."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return
            for cmd in record.commands:
                if cmd is command:
                    cmd.sent_at = _utc_now()
                    return

    def pop_next_action(self, client_id: str) -> Optional[str]:
        """Pop the next queued action for a client."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None or not record.next_actions:
                return None
            action = record.next_actions.pop(0)
            if not record.next_actions:
                record.next_actions = None
            return action

    def remove_client(self, client_id: str) -> Optional[ClientRecord]:
        """Remove and return a client record by ID if it exists."""
        with self._lock:
            return self._clients.pop(client_id, None)

    def set_agent_identification(
        self, client_id: str, new_instance_uid: bytes
    ) -> Optional[ClientRecord]:
        """Attach a pending agent identification message to a client."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return None
            record.pending_agent_identification = new_instance_uid
            return record

    def pop_agent_identification(self, client_id: str) -> Optional[bytes]:
        """Pop the pending agent identification value for a client."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return None
            pending = record.pending_agent_identification
            record.pending_agent_identification = None
            return pending

    def generate_unique_instance_uid(self) -> bytes:
        """Generate a UUIDv7 that does not collide with existing client IDs."""
        with self._lock:
            existing_ids = set(self._clients.keys())
            while True:
                candidate = generate_uuid7_bytes()
                if candidate.hex() not in existing_ids:
                    return candidate

    def purge_disconnected(self, cutoff: datetime) -> list[ClientRecord]:
        """Remove disconnected clients older than the cutoff timestamp."""
        removed: list[ClientRecord] = []
        with self._lock:
            to_remove = [
                client_id
                for client_id, record in self._clients.items()
                if record.disconnected
                and record.disconnected_at is not None
                and record.disconnected_at <= cutoff
            ]
            for client_id in to_remove:
                removed_record = self._clients.pop(client_id, None)
                if removed_record is not None:
                    removed.append(removed_record)
        return removed


STORE = ClientStore()
