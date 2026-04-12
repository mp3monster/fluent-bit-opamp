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

"""Always-send full update controller."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from opamp_consumer.full_update_controller.update_interface import (
    FullUpdateControllerInterface,
)


class AlwaysSend(FullUpdateControllerInterface):
    """Always trigger full reporting flags whenever an update is sent."""

    def __init__(self, *, set_all_reporting_flags: Callable[[bool], None]) -> None:
        self._set_all_reporting_flags = set_all_reporting_flags

    def configure(self, full_update_controller: dict[str, Any] | str | None) -> None:
        """Accept configuration input for interface parity; no values are required."""
        logging.getLogger(__name__).debug(
            "AlwaysSend.configure full_update_controller=%s",
            full_update_controller,
        )

    def update_sent(self, ms_from_epoch: int | None = None) -> None:
        """Trigger a full reporting flag reset for every send operation."""
        if ms_from_epoch is None:
            ms_from_epoch = int(time.time() * 1000)
        logging.getLogger(__name__).info(
            "AlwaysSend.update_sent ms_from_epoch=%s",
            ms_from_epoch,
        )
        self._set_all_reporting_flags()
