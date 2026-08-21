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

"""MCP Tool Approval workflow data structures and callback types."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeAlias


@dataclass
class MCPToolApprovalRequest:
    """Approval request details for invoking an MCP tool."""

    server_name: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class MCPToolApprovalResult:
    """Outcome of an MCP tool approval check."""

    approved: bool
    reason: str | None = None


MCPToolApprovalFunction: TypeAlias = Callable[
    [MCPToolApprovalRequest], bool | MCPToolApprovalResult | Awaitable[bool | MCPToolApprovalResult]
]

__all__ = [
    "MCPToolApprovalFunction",
    "MCPToolApprovalRequest",
    "MCPToolApprovalResult",
]
