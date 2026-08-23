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

"""Dynamic inline routing Command object for Graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Command:
    """Dynamic routing and state update command returned inline by graph nodes or tools.

    Attributes:
        goto: Target node name or list of node names to transition to next.
        update: Dictionary of state updates to apply before transitioning.
        resume: Value to resume execution with if interrupting.
    """

    goto: str | list[str] | None = None
    update: dict[str, Any] = field(default_factory=dict)
    resume: Any | None = None


__all__ = ["Command"]
