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

"""Time-window based full update controller."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from opamp_consumer.full_update_controller.update_interface import (
    FullUpdateControllerInterface,
)


class TimeSend(FullUpdateControllerInterface):
    """Trigger full reporting when a configured time window has elapsed."""

    def __init__(
        self,
        *,
        set_all_reporting_flags: Callable[[bool], None],
    ) -> None:
        self.full_update_after_seconds = 1
        self.last_full_update_ms = 0
        self._set_all_reporting_flags = set_all_reporting_flags

    def configure(self, full_update_controller: dict[str, Any] | str | None) -> None:
        """Set `full_update_after_seconds` from controller configuration."""
        default_value = 1
        raw_config: dict[str, Any] | Any = full_update_controller
        if isinstance(full_update_controller, str):
            try:
                raw_config = json.loads(full_update_controller)
            except json.JSONDecodeError:
                logging.getLogger(__name__).warning(
                    (
                        "TimeSend.configure invalid JSON; using default "
                        "fullUpdateAfterSeconds=%s"
                    ),
                    default_value,
                )
                raw_config = {}
        if not isinstance(raw_config, dict):
            raw_config = {}
        raw_value = raw_config.get(
            "fullUpdateAfterSeconds",
            raw_config.get("timeSendSeconds", default_value),
        )
        try:
            self.full_update_after_seconds = max(1, int(raw_value))
        except (TypeError, ValueError):
            logging.getLogger(__name__).warning(
                (
                    "TimeSend.configure invalid fullUpdateAfterSeconds=%s; "
                    "defaulting to %s"
                ),
                raw_value,
                default_value,
            )
            self.full_update_after_seconds = default_value

    def update_sent(self, ms_from_epoch: int | None = None) -> None:
        """Trigger full reporting when `last_full_update + interval < now`."""
        if ms_from_epoch is None:
            ms_from_epoch = int(time.time() * 1000)
        threshold_ms = self.full_update_after_seconds * 1000
        should_trigger = (self.last_full_update_ms + threshold_ms) < ms_from_epoch
        logging.getLogger(__name__).info(
            (
                "TimeSend.update_sent ms_from_epoch=%s last_full_update_ms=%s "
                "full_update_after_seconds=%s should_trigger=%s"
            ),
            ms_from_epoch,
            self.last_full_update_ms,
            self.full_update_after_seconds,
            should_trigger,
        )
        if should_trigger:
            self._set_all_reporting_flags()
            self.last_full_update_ms = ms_from_epoch
