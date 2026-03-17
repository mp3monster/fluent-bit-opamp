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

"""Custom message handler interfaces and utilities."""

from opamp_consumer.custom_handlers.interface import CustomMessageHandlerInterface
from opamp_consumer.custom_handlers.chatops_command import ChatOpsCommand
from opamp_consumer.custom_handlers.registry import (
    create_handler,
    discover_handlers,
)

__all__ = [
    "ChatOpsCommand",
    "CustomMessageHandlerInterface",
    "create_handler",
    "discover_handlers",
]
