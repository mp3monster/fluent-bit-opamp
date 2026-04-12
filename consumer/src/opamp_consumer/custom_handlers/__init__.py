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

from opamp_consumer.custom_handlers.handler_interface import (
    CommandHandlerInterface,
    CustomMessageHandlerInterface,
)

# Design intent: concrete handlers are discovered dynamically from this package
# directory by `registry.build_factory_lookup(...)`. We intentionally do not
# re-export concrete handler classes here so imports do not imply static wiring.
# from opamp_consumer.custom_handlers.chatops_command import ChatOpsCommand
# from opamp_consumer.custom_handlers.nullcommand import NullCommand
# from opamp_consumer.custom_handlers.shutdowncommand import ShutdownCommand
from opamp_consumer.custom_handlers.registry import (
    build_factory_lookup,
    create_handler,
    discover_handlers,
)

__all__ = [
    "CommandHandlerInterface",
    "CustomMessageHandlerInterface",
    "build_factory_lookup",
    "create_handler",
    "discover_handlers",
]
