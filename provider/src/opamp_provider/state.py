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
import sys
from enum import Enum
from datetime import datetime, timezone
from typing import Iterable, Optional

from google.protobuf import text_format
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from opamp_provider.command_record import CommandRecord
from opamp_provider.event_history import EventHistory
from opamp_provider.proto import opamp_pb2
from shared.opamp_config import anyvalue_to_string
from shared.uuid_utils import generate_uuid7_bytes

MIN_INTEGER = -sys.maxsize - 1  # Sentinel initial sequence number before first AgentToServer message.
FORCE_RESYNC_CLASSIFIER = "command"  # Classifier used for queued force-resync command events.
FORCE_RESYNC_ACTION = "forceresync"  # Action name used to request full-state resend from client.
FORCE_RESYNC_EVENT_DESCRIPTION = "Force Resync"  # User-visible description for force-resync events.
DEFAULT_HISTORY_MAX_EVENTS = 50  # Default per-client event history length when none configured.
DEFAULT_HEARTBEAT_FREQUENCY = 30  # Default expected heartbeat interval assigned to a client.
HEARTBEAT_FREQUENCY_EVENT_DESCRIPTION = "send heartbeatfrequency event"  # User-visible event text for heartbeat updates.


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _extract_agent_version(agent_msg: opamp_pb2.AgentToServer) -> Optional[str]:
    """Extract the agent service.version string from the agent description."""
    agent_desc = agent_msg.agent_description
    if not agent_desc.identifying_attributes:
        return None
    for item in agent_desc.identifying_attributes:
        if item.key == "service.version":
            return anyvalue_to_string(item.value)
    return None


def _capabilities_from_mask(mask: int) -> list[str]:
    """Decode an agent capability bitmask into enum names."""
    capabilities: list[str] = []
    logging.getLogger(__name__).debug("Decoding capability --> %s", mask)
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
                "Capabilities include --> %s",
                capabilities[-1],
            )
    return capabilities


def _normalize_custom_capabilities(capabilities: Iterable[str]) -> list[str]:
    """Normalize, deduplicate, and sort custom capability FQDN values."""
    normalized: set[str] = set()
    for capability in capabilities:
        value = str(capability).strip()
        if not value:
            continue
        if value.lower().startswith("request:"):
            value = value.split(":", 1)[1].strip()
        if not value:
            continue
        normalized.add(value)
    return sorted(normalized)


class ClientChannel(str, Enum):
    """Allowed transport channel values stored on ClientRecord."""

    HTTP = "HTTP"  # Message arrived over HTTP transport.
    WEBSOCKET = "websocket"  # Message arrived over WebSocket transport.


class ClientRecord(BaseModel):
    """Snapshot of provider-side state for one connected (or known) client."""

    model_config = ConfigDict(frozen=False)

    client_id: str = Field(description="Unique client identifier (hex-encoded instance UID).")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Decoded list of agent capabilities currently reported by the client.",
    )
    custom_capabilities_reported: list[str] = Field(
        default_factory=list,
        description="Custom capability FQDN values reported by the client in AgentToServer payloads.",
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
    events: list[EventHistory | CommandRecord] = Field(
        default_factory=list,
        description="Recent event timeline entries (generic events and command events).",
    )
    next_actions: Optional[list[str]] = Field(
        default=None,
        description="Ordered list of server next-actions to apply on upcoming client check-ins.",
    )
    next_expected_communication: Optional[datetime] = Field(
        default=None,
        description="Predicted next communication timestamp based on heartbeat behavior.",
    )
    heartbeat_frequency: int = Field(
        default=DEFAULT_HEARTBEAT_FREQUENCY,
        description="Expected heartbeat frequency in seconds for this client.",
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
    message_id: int = Field(
        default=MIN_INTEGER,
        description=(
            "Last received AgentToServer sequence number for this client. "
            "Initialized to minimum integer sentinel."
        ),
    )

    @field_serializer("pending_agent_identification", when_used="json")
    def serialize_pending_agent_identification(
        self, pending_agent_identification: Optional[bytes]
    ) -> Optional[str]:
        """Serialize pending instance UID bytes as hex for JSON responses."""
        if pending_agent_identification is None:
            return None
        return pending_agent_identification.hex()


class ClientStore:
    def __init__(self) -> None:
        """Initialize the in-memory client store."""
        self._lock = threading.Lock()
        self._clients: dict[str, ClientRecord] = {}
        self._pending_instance_uid_replacements: dict[str, str] = {}
        self._default_heartbeat_frequency = DEFAULT_HEARTBEAT_FREQUENCY

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
        incoming_message_id = int(agent_msg.sequence_num)
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = self._rekey_client_record_for_reissued_uid_locked(client_id)
            if record is None:
                record = ClientRecord(
                    client_id=client_id,
                    heartbeat_frequency=self._default_heartbeat_frequency,
                )
                self._clients[client_id] = record
            self.check_sequence_num(record, incoming_message_id)
            self._apply_comm_metadata(record, now, channel)
            self._apply_capabilities(record, agent_msg)
            self._apply_custom_capabilities(record, agent_msg)
            self._apply_client_version(record, agent_msg)
            self._apply_health(record, agent_msg)
            self._apply_agent_description(record, agent_msg)
            self._apply_disconnect(record, agent_msg, now)
        return record

    def _rekey_client_record_for_reissued_uid_locked(
        self, new_client_id: str
    ) -> Optional[ClientRecord]:
        """Move an existing client record to a server-issued replacement instance UID."""
        previous_client_id = self._pending_instance_uid_replacements.pop(
            new_client_id, None
        )
        if not previous_client_id:
            return None
        record = self._clients.pop(previous_client_id, None)
        if record is None:
            logging.getLogger(__name__).warning(
                "pending identification source client missing previous_client_id=%s new_client_id=%s",
                previous_client_id,
                new_client_id,
            )
            return None
        record.client_id = new_client_id
        record.pending_agent_identification = None
        self._clients[new_client_id] = record
        logging.getLogger(__name__).info(
            "rekeyed client record after identification previous_client_id=%s new_client_id=%s",
            previous_client_id,
            new_client_id,
        )
        return record

    def _queue_force_resync_if_missing_locked(self, record: ClientRecord) -> bool:
        """Queue one unsent force-resync command when none is pending."""
        for command in record.commands:
            if command.sent_at is not None:
                continue
            if (
                command.classifier.strip().lower() == FORCE_RESYNC_CLASSIFIER
                and command.action.strip().lower() == FORCE_RESYNC_ACTION
            ):
                return False
        command = CommandRecord(
            classifier=FORCE_RESYNC_CLASSIFIER,
            action=FORCE_RESYNC_ACTION,
            key_value_pairs=[
                {"key": "classifier", "value": FORCE_RESYNC_CLASSIFIER},
                {"key": "action", "value": FORCE_RESYNC_ACTION},
                {"key": "source", "value": "server-sequence-check"},
            ],
            event_description=FORCE_RESYNC_EVENT_DESCRIPTION,
        )
        record.commands.append(command)
        self._append_history_event(
            record,
            command,
            max_events=self._resolve_event_history_size(),
        )
        return True

    def _resolve_event_history_size(self) -> int:
        """Resolve configured event-history size with a safe default fallback."""
        try:
            from opamp_provider import config as provider_config

            return int(provider_config.CONFIG.client_event_history_size)
        except Exception:
            return DEFAULT_HISTORY_MAX_EVENTS

    def check_sequence_num(self, record: ClientRecord, message_id: int) -> None:
        """Validate incoming sequence number continuity and queue force-resync when needed."""
        logger = logging.getLogger(__name__)
        current_message_id = int(record.message_id)
        requires_full_report = (
            current_message_id == MIN_INTEGER or message_id != (current_message_id + 1)
        )
        if requires_full_report:
            queued = self._queue_force_resync_if_missing_locked(record)
            logger.warning(
                (
                    "check_sequence_num outcome=force_resync_required client_id=%s "
                    "previous_message_id=%s incoming_message_id=%s queued=%s"
                ),
                record.client_id,
                current_message_id,
                message_id,
                queued,
            )
        else:
            logger.info(
                (
                    "check_sequence_num outcome=sequential_ok client_id=%s "
                    "previous_message_id=%s incoming_message_id=%s"
                ),
                record.client_id,
                current_message_id,
                message_id,
            )
        record.message_id = message_id

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

    def _apply_custom_capabilities(
        self, record: ClientRecord, agent_msg: opamp_pb2.AgentToServer
    ) -> None:
        """Apply custom capability FQDN values when provided by the client."""
        if not agent_msg.HasField("custom_capabilities"):
            return
        record.custom_capabilities_reported = _normalize_custom_capabilities(
            agent_msg.custom_capabilities.capabilities
        )

    def _apply_client_version(
        self, record: ClientRecord, agent_msg: opamp_pb2.AgentToServer
    ) -> None:
        """Apply the client version extracted from the agent description."""
        if not agent_msg.HasField("agent_description"):
            return
        version = _extract_agent_version(agent_msg)
        if version is not None:
            record.client_version = version

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
        event_description: str,
        max_events: int,
    ) -> CommandRecord:
        """Queue a command for a client and add it to unified event history."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(
                    client_id=client_id,
                    heartbeat_frequency=self._default_heartbeat_frequency,
                )
                self._clients[client_id] = record
            cmd = CommandRecord(
                classifier=classifier,
                action=action,
                key_value_pairs=key_value_pairs,
                event_description=event_description,
            )
            record.commands.append(cmd)
            self._append_history_event(record, cmd, max_events=max_events)
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
                record = ClientRecord(
                    client_id=client_id,
                    heartbeat_frequency=self._default_heartbeat_frequency,
                )
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
                record = ClientRecord(
                    client_id=client_id,
                    heartbeat_frequency=self._default_heartbeat_frequency,
                )
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
                record = ClientRecord(
                    client_id=client_id,
                    heartbeat_frequency=self._default_heartbeat_frequency,
                )
                self._clients[client_id] = record
            event = EventHistory(event_description=description)
            self._append_history_event(record, event, max_events=max_events)
            return record

    def get_default_heartbeat_frequency(self) -> int:
        """Return the default heartbeat frequency in seconds used for client records."""
        with self._lock:
            return int(self._default_heartbeat_frequency)

    def set_default_heartbeat_frequency(
        self, heartbeat_frequency: int, *, max_events: int
    ) -> int:
        """Set default heartbeat frequency and apply it to all known clients."""
        with self._lock:
            frequency = max(1, int(heartbeat_frequency))
            self._default_heartbeat_frequency = frequency
            for record in self._clients.values():
                record.heartbeat_frequency = frequency
                event = EventHistory(
                    event_description=HEARTBEAT_FREQUENCY_EVENT_DESCRIPTION
                )
                self._append_history_event(record, event, max_events=max_events)
            logging.getLogger(__name__).info(
                (
                    "set_default_heartbeat_frequency updated_clients=%s "
                    "heartbeat_frequency=%s"
                ),
                len(self._clients),
                frequency,
            )
            return len(self._clients)

    def set_client_heartbeat_frequency(
        self,
        client_id: str,
        heartbeat_frequency: int,
        *,
        max_events: int,
    ) -> Optional[ClientRecord]:
        """Set heartbeat frequency for a single client and append an event."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return None
            frequency = max(1, int(heartbeat_frequency))
            record.heartbeat_frequency = frequency
            event = EventHistory(
                event_description=HEARTBEAT_FREQUENCY_EVENT_DESCRIPTION
            )
            self._append_history_event(record, event, max_events=max_events)
            logging.getLogger(__name__).info(
                "set_client_heartbeat_frequency client_id=%s heartbeat_frequency=%s",
                client_id,
                frequency,
            )
            return record

    def _append_history_event(
        self,
        record: ClientRecord,
        event: EventHistory | CommandRecord,
        *,
        max_events: int,
    ) -> None:
        """Append one event object and cap the per-client timeline."""
        record.events.append(event)
        keep = max(1, int(max_events))
        if len(record.events) > keep:
            record.events = record.events[-keep:]

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
            record = self._clients.pop(client_id, None)
            pending_targets = [
                target_id
                for target_id, source_id in self._pending_instance_uid_replacements.items()
                if source_id == client_id or target_id == client_id
            ]
            for target_id in pending_targets:
                self._pending_instance_uid_replacements.pop(target_id, None)
            return record

    def set_agent_identification(
        self, client_id: str, new_instance_uid: bytes
    ) -> Optional[ClientRecord]:
        """Attach a pending agent identification message to a client."""
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return None
            if record.pending_agent_identification:
                self._pending_instance_uid_replacements.pop(
                    record.pending_agent_identification.hex(), None
                )
            record.pending_agent_identification = new_instance_uid
            self._pending_instance_uid_replacements[new_instance_uid.hex()] = client_id
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
            existing_ids.update(self._pending_instance_uid_replacements.keys())
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


STORE = ClientStore()  # Module-level in-memory client store singleton.
