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

"""RunConfig configuration container for execution runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolExecutionConfig:
    """Tool execution options."""

    parallel: bool = True
    timeout_seconds: float = 120.0


@dataclass
class RunConfig:
    """Run configuration container for state graph and agent executions."""

    max_turns: int = 25
    tracing_disabled: bool = False
    tool_config: ToolExecutionConfig = field(default_factory=ToolExecutionConfig)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "RunConfig",
    "ToolExecutionConfig",
]
