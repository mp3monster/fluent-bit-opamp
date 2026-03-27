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

"""UUID helper utilities shared by provider and consumer."""

from __future__ import annotations

import secrets
import time
import uuid


def generate_uuid7_bytes() -> bytes:
    """Generate UUIDv7 bytes without requiring third-party libraries."""
    timestamp_ms = int(time.time_ns() / 1_000_000)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    uuid_int = (
        (timestamp_ms & ((1 << 48) - 1)) << 80
        | (0x7 << 76)
        | (rand_a << 64)
        | (0x2 << 62)
        | rand_b
    )
    return uuid.UUID(int=uuid_int).bytes
