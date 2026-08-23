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

"""Tool namespace utilities for preventing tool name collisions across sub-agents."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def tool_namespace(namespace: str, tools: list[Callable[..., Any]]) -> list[Callable[..., Any]]:
    """Prefix a list of tools with a namespace string (e.g. `namespace__tool_name`).

    Args:
        namespace: Prefix string to prepended to tool names.
        tools: List of tool callables to namespace.

    Returns:
        List of tool functions with updated qualified names.
    """
    namespaced = []
    for tool in tools:
        orig_name = getattr(tool, "__name__", "tool")
        if not orig_name.startswith(f"{namespace}__"):
            new_name = f"{namespace}__{orig_name}"
            tool.__name__ = new_name
        namespaced.append(tool)
    return namespaced


__all__ = ["tool_namespace"]
