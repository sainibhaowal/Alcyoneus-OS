"""ToolNode package.

This package provides a modularized implementation of ToolNode. Public API:

- ToolNode
- HAS_FASTMCP, HAS_MCP
"""

from alcyoneus.core.state.tool_result import ToolResult

from .base import ToolNode
from .deps import HAS_FASTMCP, HAS_MCP
from .registry import ToolDescriptor, ToolRegistry


__all__ = ["HAS_FASTMCP", "HAS_MCP", "ToolDescriptor", "ToolNode", "ToolRegistry", "ToolResult"]
