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

"""Core Async Trigger Engine interfaces for Alcyoneus OS.

A Trigger is a long-lived async function that runs concurrently alongside an agent
session. It reacts to external events (cron, file changes, webhooks) and pushes
messages into the agent's turn loop.
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Awaitable, Callable
from typing import Protocol

import pydantic


class TriggerConnection(Protocol):
    """Protocol for live connection capable of receiving trigger notifications."""

    async def send_trigger_notification(self, content: str) -> None: ...


class TriggerContext:
    """Context object provided to every active trigger.

    Allows triggers to asynchronously send event messages into the agent loop.
    """

    def __init__(self, connection: TriggerConnection) -> None:
        self._connection = connection

    async def send(self, content: str) -> None:
        """Sends an event notification message to the agent."""
        await self._connection.send_trigger_notification(content)


Trigger = Callable[[TriggerContext], Awaitable[None]]


def trigger(
    func: Callable[[TriggerContext], Awaitable[None]],
) -> Callable[[TriggerContext], Awaitable[None]]:
    """Decorator for async Trigger functions.

    Validates that the function is a coroutine accepting exactly one parameter (TriggerContext).
    """
    if not inspect.iscoroutinefunction(func):
        raise ValueError("Trigger must be an async function (coroutine).")

    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    if len(params) != 1:
        raise ValueError("Trigger function must accept exactly one parameter (TriggerContext).")

    func.__is_trigger__ = True
    return func


class FileChangeKind(str, enum.Enum):
    """Types of filesystem change events."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class FileChange(pydantic.BaseModel):
    """A single filesystem change event detected by a file-watching trigger."""

    model_config = pydantic.ConfigDict(frozen=True)

    kind: FileChangeKind
    path: str


__all__ = [
    "FileChange",
    "FileChangeKind",
    "Trigger",
    "TriggerConnection",
    "TriggerContext",
    "trigger",
]
