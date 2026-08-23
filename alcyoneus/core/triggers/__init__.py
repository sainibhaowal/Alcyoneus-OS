# Copyright 2026 Alcyoneus Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Alcyoneus OS Trigger Package supporting both Event-based and Background Decorator triggers."""

from alcyoneus.core.triggers.event_triggers import (
    EventBasedTrigger,
    EventTrigger,
    TriggerConfig,
    TriggerEvent,
    TriggerEventType,
    create_message_trigger,
    create_tool_call_trigger,
    create_tool_error_trigger,
)
from alcyoneus.core.triggers.helpers import every, on_file_change
from alcyoneus.core.triggers.trigger_runner import QueueTriggerConnection, TriggerRunner
from alcyoneus.core.triggers.triggers import (
    FileChange,
    FileChangeKind,
    Trigger,
    TriggerConnection,
    TriggerContext,
    trigger,
)


__all__ = [
    # Event-based Triggers
    "TriggerEventType",
    "TriggerEvent",
    "EventTrigger",
    "EventBasedTrigger",
    "TriggerConfig",
    "create_tool_error_trigger",
    "create_tool_call_trigger",
    "create_message_trigger",
    # Decorator & Background Triggers
    "TriggerConnection",
    "TriggerContext",
    "Trigger",
    "trigger",
    "FileChangeKind",
    "FileChange",
    "TriggerRunner",
    "QueueTriggerConnection",
    "every",
    "on_file_change",
]
