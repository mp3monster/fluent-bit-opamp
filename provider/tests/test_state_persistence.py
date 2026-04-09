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
from datetime import datetime, timezone

from opamp_provider.config import ProviderStatePersistenceConfig
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import ClientStore
from opamp_provider.state_persistence import (
    RESTORE_AUTO,
    resolve_restore_snapshot_path,
    restore_state_snapshot,
    save_state_snapshot,
)


def test_save_state_snapshot_writes_timestamped_files_and_prunes(tmp_path) -> None:
    """Verify timestamped snapshot save behavior and retention pruning."""
    store = ClientStore()
    first = opamp_pb2.AgentToServer(instance_uid=b"\x01" * 16)
    first.sequence_num = 1
    store.upsert_from_agent_msg(first)
    persistence = ProviderStatePersistenceConfig(
        enabled=True,
        state_file_prefix=str(tmp_path / "snapshots" / "opamp_server_state"),
        retention_count=2,
        autosave_interval_seconds_since_change=600,
    )

    path_one = save_state_snapshot(
        store=store,
        persistence=persistence,
        reason="test-1",
        now=datetime(2026, 4, 9, 10, 30, 0, tzinfo=timezone.utc),
    )
    path_two = save_state_snapshot(
        store=store,
        persistence=persistence,
        reason="test-2",
        now=datetime(2026, 4, 9, 10, 30, 1, tzinfo=timezone.utc),
    )
    path_three = save_state_snapshot(
        store=store,
        persistence=persistence,
        reason="test-3",
        now=datetime(2026, 4, 9, 10, 30, 2, tzinfo=timezone.utc),
    )

    assert path_one is not None
    assert path_two is not None
    assert path_three is not None
    snapshots = sorted((tmp_path / "snapshots").glob("opamp_server_state.*.json"))
    assert len(snapshots) == 2
    assert path_one.exists() is False
    assert path_three.exists() is True


def test_resolve_restore_snapshot_path_auto_uses_latest_snapshot(tmp_path) -> None:
    """Verify auto restore mode resolves the latest timestamped snapshot."""
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    older = snapshots_dir / "opamp_server_state.20260409T103000Z.json"
    newer = snapshots_dir / "opamp_server_state.20260409T103100Z.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")

    resolved = resolve_restore_snapshot_path(
        state_file_prefix=str(snapshots_dir / "opamp_server_state"),
        restore_option=RESTORE_AUTO,
    )

    assert resolved == newer


def test_restore_state_snapshot_tolerates_schema_mismatch(tmp_path) -> None:
    """Verify schema mismatch logs warning path but still restores compatible provider_state payload."""
    client_id = "1234567890abcdef1234567890abcdef"
    snapshot_path = tmp_path / "opamp_server_state.20260409T103000Z.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "saved_at_utc": "2026-04-09T10:30:00Z",
                "provider_state": {
                    "default_heartbeat_frequency": 45,
                    "clients": [{"client_id": client_id}],
                    "pending_approvals": [],
                    "blocked_agents": [],
                    "pending_instance_uid_replacements": {},
                },
            }
        ),
        encoding="utf-8",
    )
    store = ClientStore()

    summary = restore_state_snapshot(store=store, snapshot_path=snapshot_path)

    assert summary["schema_version"] == 999
    assert summary["clients"] == 1
    assert store.get_default_heartbeat_frequency() == 45
