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

"""Full update controller interface definitions.

Implementations of this interface can control when client-side data attributes
should be re-sent to the server (for example by triggering full reporting flags).
This control is primarily needed for HTTP communication cycles; WebSocket flows
already push updates when data changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FullUpdateControllerInterface(ABC):
    """Decide when the client should force a broader data re-send to the server.

    Implementations can influence which attributes are emitted by setting
    reporting behavior in the client data model. This is mainly intended for
    HTTP polling-style communication, where periodic full-state resends may be
    required. WebSocket communication typically sends updates on change.
    """

    @abstractmethod
    def configure(self, full_update_controller: dict[str, Any] | str | None) -> None:
        """Apply controller-specific configuration from consumer config.

        Args:
            full_update_controller: Configuration payload from
                `consumer.full_update_controller`. This may be a dictionary or a
                JSON string.
        """

    @abstractmethod
    def update_sent(self, ms_from_epoch: int | None = None) -> None:
        """Record a send event and update reporting strategy as needed.

        Args:
            ms_from_epoch: Epoch timestamp in milliseconds. When None, the
                implementation should use the current epoch milliseconds.
        """
