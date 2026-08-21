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

"""Hierarchical HookContext types (SessionContext, TurnContext, OperationContext)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class StateStore:
    """Key-value state store attached to hook context layers."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def clear(self) -> None:
        self._data.clear()


@dataclass
class HookContext:
    """Root HookContext class."""

    store: StateStore = field(default_factory=StateStore)


@dataclass
class SessionContext(HookContext):
    """Session-level context spanning multiple turns."""

    session_id: str = "default_session"


@dataclass
class TurnContext(HookContext):
    """Single turn execution context."""

    session_id: str = "default_session"
    turn_id: int = 1


@dataclass
class OperationContext(HookContext):
    """Specific tool or model operation context."""

    operation_name: str = "op"


__all__ = [
    "HookContext",
    "OperationContext",
    "SessionContext",
    "StateStore",
    "TurnContext",
]
