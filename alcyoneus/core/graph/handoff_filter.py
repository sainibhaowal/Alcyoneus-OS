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

"""HandoffInputFilter for mapping/filtering conversation history during agent handoffs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class HandoffInputData:
    """Input payload passed during handoff filter evaluation."""

    history: list[Any]
    target_agent_name: str


class HandoffInputFilter:
    """Filter controlling which messages are passed when handing off control to another agent."""

    def __init__(self, filter_fn: Callable[[HandoffInputData], list[Any]] | None = None) -> None:
        self.filter_fn = filter_fn or default_handoff_history_mapper

    def apply(self, history: list[Any], target_agent: str) -> list[Any]:
        """Apply filter to conversation history."""
        return self.filter_fn(HandoffInputData(history=history, target_agent_name=target_agent))


def default_handoff_history_mapper(data: HandoffInputData) -> list[Any]:
    """Default handoff history mapper passing full conversation history."""
    return data.history


__all__ = [
    "HandoffInputData",
    "HandoffInputFilter",
    "default_handoff_history_mapper",
]
