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

"""Sent-count based full update controller."""

from __future__ import annotations

import logging
import time
from typing import Callable
import json
from typing import Any

from opamp_consumer.full_update_controller.update_interface import (
    FullUpdateControllerInterface,
)


class SentCount(FullUpdateControllerInterface):
    """Count sent updates and request full reporting after a configured threshold."""

    def __init__(
        self,
        *,
        set_all_reporting_flags: Callable[[bool], None],
    ) -> None:
        self.full_resend_after = 1
        self.sent_count = 0
        self._set_all_reporting_flags = set_all_reporting_flags

    def configure(self, full_update_controller: dict[str, Any] | str | None) -> None:
        """Set `full_resend_after` from full update controller configuration."""
        default_value = 1
        raw_config: dict[str, Any] | Any = full_update_controller
        if isinstance(full_update_controller, str):
            try:
                raw_config = json.loads(full_update_controller)
            except json.JSONDecodeError:
                logging.getLogger(__name__).warning(
                    "SentCount.configure invalid JSON; using default fullResendAfter=%s",
                    default_value,
                )
                raw_config = {}
        if not isinstance(raw_config, dict):
            raw_config = {}
        raw_value = raw_config.get("fullResendAfter", default_value)
        try:
            self.full_resend_after = max(1, int(raw_value))
        except (TypeError, ValueError):
            logging.getLogger(__name__).warning(
                "SentCount.configure invalid fullResendAfter=%s; defaulting to %s",
                raw_value,
                default_value,
            )
            self.full_resend_after = default_value

    def update_sent(self, ms_from_epoch: int | None = None) -> None:
        """Record a sent update and trigger full reporting when threshold is hit."""
        if ms_from_epoch is None:
            ms_from_epoch = int(time.time() * 1000)
        self.sent_count += 1
        logging.getLogger(__name__).info(
            "SentCount.update_sent ms_from_epoch=%s sent_count=%s full_resend_after=%s",
            ms_from_epoch,
            self.sent_count,
            self.full_resend_after,
        )
        if self.sent_count >= self.full_resend_after:
            self._set_all_reporting_flags()
            self.sent_count = 0
