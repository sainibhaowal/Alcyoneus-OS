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

"""ToolSearchTool for dynamically discovering registered tools at runtime."""

from __future__ import annotations

from typing import Any


class ToolSearchTool:
    """Tool that allows agents to search for tools by keyword or description query."""

    def __init__(self, tool_registry: list[Any] | None = None) -> None:
        self.tool_registry = tool_registry or []

    def search_tools(self, query: str) -> list[dict[str, Any]]:
        """Search available tool descriptors matching query string."""
        query_lower = query.lower()
        results = []
        for tool in self.tool_registry:
            name = getattr(tool, "__name__", str(tool))
            doc = getattr(tool, "__doc__", "") or ""
            if query_lower in name.lower() or query_lower in doc.lower():
                results.append({"name": name, "description": doc.strip()})
        return results


def tool_search(query: str, registry: list[Any] | None = None) -> list[dict[str, Any]]:
    """Functional helper for tool search."""
    searcher = ToolSearchTool(tool_registry=registry)
    return searcher.search_tools(query)


__all__ = ["ToolSearchTool", "tool_search"]
