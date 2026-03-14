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
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from google.protobuf import text_format
from pydantic import BaseModel, ConfigDict, Field

from opamp_provider.proto import opamp_pb2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _anyvalue_to_string(value: opamp_pb2.AnyValue) -> Optional[str]:
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
    agent_desc = agent_msg.agent_description
    if not agent_desc.identifying_attributes:
        return None
    for item in agent_desc.identifying_attributes:
        if item.key == "service.version":
            return _anyvalue_to_string(item.value)
    return None


def _capabilities_from_mask(mask: int) -> list[str]:
    capabilities: list[str] = []
    for enum_value in opamp_pb2.AgentCapabilities.DESCRIPTOR.values:
        if enum_value.number == 0:
            continue
        if mask & enum_value.number:
            capabilities.append(enum_value.name)
    return capabilities


class CommandRecord(BaseModel):
    model_config = ConfigDict(frozen=False)

    command: str
    received_at: datetime = Field(default_factory=_utc_now)
    sent_at: Optional[datetime] = None


class ClientRecord(BaseModel):
    model_config = ConfigDict(frozen=False)

    client_id: str
    capabilities: list[str] = Field(default_factory=list)
    agent_description: Optional[str] = None
    node_age_seconds: Optional[float] = None
    last_communication: Optional[datetime] = None
    current_config: Optional[str] = None
    current_config_version: Optional[str] = None
    requested_config: Optional[str] = None
    requested_config_version: Optional[str] = None
    requested_config_apply_at: Optional[datetime] = None
    client_version: Optional[str] = None
    features: list[str] = Field(default_factory=list)
    commands: list[CommandRecord] = Field(default_factory=list)
    next_expected_communication: Optional[datetime] = None
    first_seen: datetime = Field(default_factory=_utc_now)


class ClientStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: dict[str, ClientRecord] = {}

    def get(self, client_id: str) -> Optional[ClientRecord]:
        with self._lock:
            return self._clients.get(client_id)

    def list(self) -> list[ClientRecord]:
        with self._lock:
            return list(self._clients.values())

    def upsert_from_agent_msg(self, agent_msg: opamp_pb2.AgentToServer) -> ClientRecord:
        client_id = agent_msg.instance_uid.hex() if agent_msg.instance_uid else "unknown"
        now = _utc_now()
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            record.last_communication = now
            record.node_age_seconds = (now - record.first_seen).total_seconds()
            record.capabilities = _capabilities_from_mask(agent_msg.capabilities)
            record.client_version = _extract_agent_version(agent_msg)
            if agent_msg.HasField("agent_description"):
                record.agent_description = text_format.MessageToString(
                    agent_msg.agent_description
                )
        return record

    def queue_command(self, client_id: str, command: str) -> CommandRecord:
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            cmd = CommandRecord(command=command)
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
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                record = ClientRecord(client_id=client_id)
                self._clients[client_id] = record
            record.requested_config = config_text
            record.requested_config_version = version
            record.requested_config_apply_at = apply_at
            return record

    def next_pending_command(self, client_id: str) -> Optional[CommandRecord]:
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return None
            for cmd in record.commands:
                if cmd.sent_at is None:
                    return cmd
        return None

    def mark_command_sent(self, client_id: str, command: CommandRecord) -> None:
        with self._lock:
            record = self._clients.get(client_id)
            if record is None:
                return
            for cmd in record.commands:
                if cmd is command:
                    cmd.sent_at = _utc_now()
                    return


STORE = ClientStore()
