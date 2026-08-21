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

"""Event-based trigger system for Alcyoneus OS.

Provides event-based triggers (TOOL_CALL, TOOL_RESULT, TOOL_ERROR, AGENT_START, AGENT_END,
MESSAGE_RECEIVED, MESSAGE_SENT, CUSTOM) with source/data filtering and debouncing.
"""

from __future__ import annotations

import asyncio
import logging
import typing as t
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger("alcyoneus.triggers")


class TriggerEventType(Enum):
    """Types of events that can trigger actions."""

    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    CUSTOM = "custom"


@dataclass
class TriggerEvent:
    """An event that can trigger actions.

    Attributes:
        event_type: Type of the event.
        data: Event-specific data.
        timestamp: When the event occurred.
        source: Source of the event (e.g., tool name, agent name).
    """

    event_type: TriggerEventType
    data: dict[str, t.Any]
    timestamp: float
    source: str = ""

    def to_dict(self) -> dict[str, t.Any]:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


@dataclass
class EventTrigger:
    """A trigger that executes an action when an event occurs.

    Attributes:
        name: Unique name for this trigger.
        event_type: Type of event to listen for.
        source_filter: Optional filter for event source (e.g., specific tool name).
        data_filter: Optional filter for event data (key-value pairs to match).
        action: Async function to execute when trigger fires.
        enabled: Whether this trigger is active.
        debounce_seconds: Minimum time between trigger executions.
    """

    name: str
    event_type: TriggerEventType
    action: t.Callable[[TriggerEvent], t.Awaitable[None]]
    source_filter: str | None = None
    data_filter: dict[str, t.Any] | None = None
    enabled: bool = True
    debounce_seconds: float = 0.0
    _last_execution: float = 0.0

    def matches(self, event: TriggerEvent) -> bool:
        """Check if this trigger matches the given event."""
        if not self.enabled:
            return False

        if event.event_type != self.event_type:
            return False

        if self.source_filter and event.source != self.source_filter:
            return False

        if self.data_filter:
            for key, value in self.data_filter.items():
                if event.data.get(key) != value:
                    return False

        # Check debounce
        if self.debounce_seconds > 0:
            try:
                current_time = asyncio.get_event_loop().time()
            except RuntimeError:
                import time

                current_time = time.time()
            if current_time - self._last_execution < self.debounce_seconds:
                return False

        return True

    async def execute(self, event: TriggerEvent) -> None:
        """Execute the trigger action."""
        try:
            current_time = asyncio.get_event_loop().time()
        except RuntimeError:
            import time

            current_time = time.time()
        self._last_execution = current_time
        try:
            await self.action(event)
            logger.debug(f"Trigger '{self.name}' executed successfully")
        except Exception as e:
            logger.exception(f"Trigger '{self.name}' execution failed: {e}")


# Alias for backward compatibility
EventBasedTrigger = EventTrigger


@dataclass
class TriggerConfig:
    """Configuration for the event trigger system.

    Attributes:
        triggers: List of triggers to monitor.
        enabled: Whether the trigger system is enabled.
    """

    triggers: list[EventTrigger] = field(default_factory=list)
    enabled: bool = True


def create_tool_error_trigger(
    name: str,
    action: t.Callable[[TriggerEvent], t.Awaitable[None]],
    tool_name: str | None = None,
) -> EventTrigger:
    """Create a trigger that fires on tool errors."""
    return EventTrigger(
        name=name,
        event_type=TriggerEventType.TOOL_ERROR,
        action=action,
        source_filter=tool_name,
    )


def create_tool_call_trigger(
    name: str,
    action: t.Callable[[TriggerEvent], t.Awaitable[None]],
    tool_name: str | None = None,
) -> EventTrigger:
    """Create a trigger that fires on tool calls."""
    return EventTrigger(
        name=name,
        event_type=TriggerEventType.TOOL_CALL,
        action=action,
        source_filter=tool_name,
    )


def create_message_trigger(
    name: str,
    action: t.Callable[[TriggerEvent], t.Awaitable[None]],
    event_type: TriggerEventType = TriggerEventType.MESSAGE_RECEIVED,
) -> EventTrigger:
    """Create a trigger that fires on message events."""
    return EventTrigger(
        name=name,
        event_type=event_type,
        action=action,
    )


__all__ = [
    "EventBasedTrigger",
    "EventTrigger",
    "TriggerConfig",
    "TriggerEvent",
    "TriggerEventType",
    "create_message_trigger",
    "create_tool_call_trigger",
    "create_tool_error_trigger",
]
