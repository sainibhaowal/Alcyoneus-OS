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

"""Base abstract class and settings for multi-backend agent sessions."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class SessionSettings:
    """Settings controlling session history persistence and retention."""

    max_turns: int | None = 100
    compact_on_limit: bool = True
    session_id_header: str = "x-session-id"


class SessionABC(abc.ABC):
    """Abstract base class for all session storage backends."""

    def __init__(self, session_id: str, settings: SessionSettings | None = None) -> None:
        self.session_id = session_id
        self.settings = settings or SessionSettings()

    @abc.abstractmethod
    async def get_items(self) -> list[Any]:
        """Retrieve stored conversation history items for this session."""

    @abc.abstractmethod
    async def add_items(self, items: list[Any]) -> None:
        """Append new items to the session history."""

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all session history."""


class Session(SessionABC):
    """In-memory default session implementation."""

    def __init__(self, session_id: str, settings: SessionSettings | None = None) -> None:
        super().__init__(session_id, settings)
        self._items: list[Any] = []

    async def get_items(self) -> list[Any]:
        return list(self._items)

    async def add_items(self, items: list[Any]) -> None:
        self._items.extend(items)

    async def clear(self) -> None:
        self._items.clear()


__all__ = [
    "Session",
    "SessionABC",
    "SessionSettings",
]
