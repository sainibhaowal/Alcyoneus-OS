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

"""Serializable RunState snapshot for pause/resume execution persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunState:
    """Full state snapshot of an active agent/runner execution for serialization."""

    run_id: str
    active_agent_name: str
    turn_count: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    state_data: dict[str, Any] = field(default_factory=dict)
    status: str = "running"

    def to_json(self) -> str:
        """Serialize RunState to JSON string."""
        return json.dumps(
            {
                "run_id": self.run_id,
                "active_agent_name": self.active_agent_name,
                "turn_count": self.turn_count,
                "messages": self.messages,
                "state_data": self.state_data,
                "status": self.status,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> RunState:
        """Deserialize RunState from JSON string."""
        d = json.loads(json_str)
        return cls(**d)


__all__ = ["RunState"]
