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

"""Realtime tool filtering and validation for live streaming audio sessions."""

from __future__ import annotations

from typing import Any


class RealtimeToolFilter:
    """Filter to validate and constrain tool availability during real-time duplex audio sessions."""

    def __init__(self, allowed_tools: list[str] | None = None) -> None:
        self.allowed_tools = set(allowed_tools) if allowed_tools else None

    def is_allowed(self, tool_name: str) -> bool:
        if self.allowed_tools is None:
            return True
        return tool_name in self.allowed_tools

    def filter_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.allowed_tools is None:
            return tools
        return [t for t in tools if t.get("name") in self.allowed_tools]


__all__ = ["RealtimeToolFilter"]
