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

"""CustomTool wrapper for registering custom tool specifications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


ToolCaller = Literal["direct", "programmatic"]


@dataclass
class CustomTool:
    """Explicit Custom Tool container with custom JSON schema and handler."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    fn: Callable[..., Any]
    caller_type: ToolCaller = "direct"

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the underlying tool function."""
        res = self.fn(**kwargs)
        if hasattr(res, "__await__"):
            return await res
        return res


__all__ = ["CustomTool", "ToolCaller"]
