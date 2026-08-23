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

"""MCPManager for managing multiple MCP servers lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from .approval import MCPToolApprovalFunction
from .server import MCPServer


logger = logging.getLogger("alcyoneus.mcp.manager")


class MCPManager:
    """Manager for registering, connecting, and routing calls across MCP servers."""

    def __init__(
        self,
        servers: list[MCPServer] | None = None,
        approval_fn: MCPToolApprovalFunction | None = None,
    ) -> None:
        self.servers: dict[str, MCPServer] = {s.name: s for s in (servers or [])}
        self.approval_fn = approval_fn

    def add_server(self, server: MCPServer) -> None:
        """Register an MCP server instance."""
        self.servers[server.name] = server

    async def connect_all(self) -> None:
        """Connect to all registered MCP servers."""
        for s in self.servers.values():
            await s.connect()

    async def disconnect_all(self) -> None:
        """Disconnect all registered MCP servers."""
        for s in self.servers.values():
            await s.disconnect()

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """Aggregate tools across all registered MCP servers."""
        all_tools = []
        for s in self.servers.values():
            tools = await s.list_tools()
            for t in tools:
                t["server_name"] = s.name
                all_tools.append(t)
        return all_tools


__all__ = ["MCPManager"]
