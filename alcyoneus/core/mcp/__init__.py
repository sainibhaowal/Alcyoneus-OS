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

"""Model Context Protocol (MCP) Server and Client Infrastructure for Alcyoneus OS."""

from .approval import (
    MCPToolApprovalFunction,
    MCPToolApprovalRequest,
    MCPToolApprovalResult,
)
from .manager import MCPManager
from .server import (
    MCPServer,
    MCPServerStdio,
    MCPServerStreamableHTTP,
)
from .transport import (
    MCPCapabilities,
    MCPClient,
    MCPServerInfo,
    MCPTransport,
    SSETransport,
    StdioTransport,
    WebSocketTransport,
    create_transport,
)


__all__ = [
    "MCPCapabilities",
    "MCPClient",
    "MCPManager",
    "MCPServer",
    "MCPServerInfo",
    "MCPServerStdio",
    "MCPServerStreamableHTTP",
    "MCPToolApprovalFunction",
    "MCPToolApprovalRequest",
    "MCPToolApprovalResult",
    "MCPTransport",
    "SSETransport",
    "StdioTransport",
    "WebSocketTransport",
    "create_transport",
]
