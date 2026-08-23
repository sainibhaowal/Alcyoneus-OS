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

"""ProgrammaticToolCallingTool for programmatic tool invocation from code."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ProgrammaticToolCallingTool:
    """Special tool wrapper enabling models to execute tool chains programmatically."""

    def __init__(self, target_tool: Callable[..., Any]) -> None:
        self.target_tool = target_tool
        self.name = getattr(target_tool, "__name__", "programmatic_tool")

    async def invoke(self, kwargs: dict[str, Any]) -> Any:
        res = self.target_tool(**kwargs)
        if hasattr(res, "__await__"):
            return await res
        return res


__all__ = ["ProgrammaticToolCallingTool"]
