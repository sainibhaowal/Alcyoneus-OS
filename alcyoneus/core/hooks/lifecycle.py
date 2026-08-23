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

"""Lifecycle hook structures for Agent and Runner executions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentHooks:
    """Agent-level lifecycle event callbacks."""

    on_start: Callable[[Any], None] | None = None
    on_end: Callable[[Any], None] | None = None
    on_handoff: Callable[[Any, str, str], None] | None = None
    on_tool_call: Callable[[str, dict], None] | None = None


@dataclass
class RunHooks:
    """Run-level execution event callbacks."""

    on_agent_start: Callable[[str], None] | None = None
    on_agent_end: Callable[[str], None] | None = None
    on_turn_start: Callable[[int], None] | None = None
    on_turn_end: Callable[[int], None] | None = None


__all__ = ["AgentHooks", "RunHooks"]
