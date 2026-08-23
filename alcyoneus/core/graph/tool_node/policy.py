"""Alcyoneus OS Policy Engine.

This module provides a declarative policy system for controlling tool execution.
It allows fine-grained control over which tools can be executed, with support
for allowlists, denylists, and user confirmation workflows.

Usage:
    from alcyoneus.core.graph.tool_node.policy import (
        Policy,
        PolicyAction,
        PolicyConfig,
        allow_all,
        deny_all,
        allow,
        deny,
        ask_user,
    )

    # Allow all tools
    policies = [allow_all()]

    # Deny by default, allow specific tools
    policies = [deny_all(), allow(["safe_tool"])]

    # Ask user for specific tools
    policies = [allow_all(), ask_user(["dangerous_tool"], handler=my_handler)]
"""

from __future__ import annotations

import logging
import typing as t
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger("alcyoneus.graph.tool_node.policy")


logger = logging.getLogger("alcyoneus.graph.tool_node.policy")


class PolicyAction(Enum):
    """Action to take when a policy matches."""

    ALLOW = "allow"
    DENY = "deny"
    ASK_USER = "ask_user"


@dataclass
class Policy:
    """A single policy rule for tool execution control.

    Attributes:
        action: The action to take (ALLOW, DENY, ASK_USER).
        tool_names: List of tool names this policy applies to. Empty means all tools.
        mcp_server_names: List of MCP server names this policy applies to. Empty means all.
        handler: Optional async handler function for ASK_USER action.
        description: Human-readable description of this policy.
    """

    action: PolicyAction
    tool_names: list[str] = field(default_factory=list)
    mcp_server_names: list[str] = field(default_factory=list)
    handler: t.Callable[[str, dict], t.Awaitable[bool]] | None = None
    description: str = ""
    argument_predicate: t.Callable[[dict], bool] | None = None
    user_ids: list[str] = field(default_factory=list)
    tenant_ids: list[str] = field(default_factory=list)

    def matches(
        self,
        tool_name: str,
        mcp_server_name: str | None = None,
        args: dict | None = None,
        context: dict | None = None,
    ) -> bool:
        """Check if this policy matches the given tool and server.

        Args:
            tool_name: Name of the tool being executed.
            mcp_server_name: Optional name of the MCP server.

        Returns:
            True if this policy applies to the tool/server combination.
        """
        # Check tool name match
        if self.tool_names:
            if tool_name not in self.tool_names:
                return False

        # Check MCP server match
        if self.mcp_server_names:
            if not mcp_server_name or mcp_server_name not in self.mcp_server_names:
                return False

        context = context or {}
        if self.user_ids and str(context.get("user_id")) not in self.user_ids:
            return False
        if self.tenant_ids and str(context.get("tenant_id")) not in self.tenant_ids:
            return False
        if self.argument_predicate and not self.argument_predicate(args or {}):
            return False

        return True


@dataclass
class PolicyConfig:
    """Configuration for the policy system.

    Attributes:
        policies: List of policy rules to apply.
        default_action: Default action when no policies match.
        deny_by_default: If True, deny all tools unless explicitly allowed.
    """

    policies: list[Policy] = field(default_factory=list)
    default_action: PolicyAction = PolicyAction.ALLOW
    deny_by_default: bool = False

    def evaluate(
        self,
        tool_name: str,
        mcp_server_name: str | None = None,
        args: dict | None = None,
        context: dict | None = None,
    ) -> tuple[PolicyAction, Policy | None]:
        """Evaluate policies for a tool execution request.

        Args:
            tool_name: Name of the tool being executed.
            mcp_server_name: Optional name of the MCP server.

        Returns:
            Tuple of (action, matching_policy). If no policy matches,
            returns (default_action, None).
        """
        # Check each policy in order
        for policy in self.policies:
            if policy.matches(tool_name, mcp_server_name, args, context):
                return policy.action, policy

        # No policy matched, use default
        if self.deny_by_default:
            return PolicyAction.DENY, None
        return self.default_action, None


# Declarative policy builder functions


def allow_all() -> Policy:
    """Create a policy that allows all tools.

    Returns:
        A Policy with ALLOW action and no tool restrictions.
    """
    return Policy(action=PolicyAction.ALLOW, description="Allow all tools")


def deny_all() -> Policy:
    """Create a policy that denies all tools.

    Returns:
        A Policy with DENY action and no tool restrictions.
    """
    return Policy(action=PolicyAction.DENY, description="Deny all tools")


def allow(
    tool_names: list[str] | str,
    mcp_server_names: list[str] | str | None = None,
    mcp_server_config: t.Any | None = None,
    argument_predicate: t.Callable[[dict], bool] | None = None,
    user_ids: list[str] | None = None,
    tenant_ids: list[str] | None = None,
) -> Policy:
    """Create a policy that allows specific tools.

    Args:
        tool_names: List of tool names or single tool name to allow.
        mcp_server_names: Optional list of MCP server names or single server name.
        mcp_server_config: Optional MCP server configuration object. If provided,
            extracts server name from config and allows all tools from that server.

    Returns:
        A Policy with ALLOW action for the specified tools.
    """
    if isinstance(tool_names, str):
        tool_names = [tool_names]

    if isinstance(mcp_server_names, str):
        mcp_server_names = [mcp_server_names]
    elif mcp_server_names is None:
        mcp_server_names = []

    # If MCP server config is provided, extract server name
    if mcp_server_config is not None:
        if hasattr(mcp_server_config, "name"):
            mcp_server_names = [mcp_server_config.name]
            # If no tool names specified, allow all tools from this server
            if not tool_names:
                tool_names = []  # Empty means all tools from this server

    return Policy(
        action=PolicyAction.ALLOW,
        tool_names=tool_names,
        mcp_server_names=mcp_server_names,
        argument_predicate=argument_predicate,
        user_ids=user_ids or [],
        tenant_ids=tenant_ids or [],
        description=f"Allow tools: {tool_names if tool_names else 'all'} from servers: {mcp_server_names if mcp_server_names else 'all'}",  # noqa: E501
    )


def deny(
    tool_names: list[str] | str,
    mcp_server_names: list[str] | str | None = None,
    mcp_server_config: t.Any | None = None,
    argument_predicate: t.Callable[[dict], bool] | None = None,
    user_ids: list[str] | None = None,
    tenant_ids: list[str] | None = None,
) -> Policy:
    """Create a policy that denies specific tools.

    Args:
        tool_names: List of tool names or single tool name to deny.
        mcp_server_names: Optional list of MCP server names or single server name.
        mcp_server_config: Optional MCP server configuration object. If provided,
            extracts server name from config and denies all tools from that server.

    Returns:
        A Policy with DENY action for the specified tools.
    """
    if isinstance(tool_names, str):
        tool_names = [tool_names]

    if isinstance(mcp_server_names, str):
        mcp_server_names = [mcp_server_names]
    elif mcp_server_names is None:
        mcp_server_names = []

    # If MCP server config is provided, extract server name
    if mcp_server_config is not None:
        if hasattr(mcp_server_config, "name"):
            mcp_server_names = [mcp_server_config.name]
            # If no tool names specified, deny all tools from this server
            if not tool_names:
                tool_names = []  # Empty means all tools from this server

    return Policy(
        action=PolicyAction.DENY,
        tool_names=tool_names,
        mcp_server_names=mcp_server_names,
        argument_predicate=argument_predicate,
        user_ids=user_ids or [],
        tenant_ids=tenant_ids or [],
        description=f"Deny tools: {tool_names if tool_names else 'all'} from servers: {mcp_server_names if mcp_server_names else 'all'}",  # noqa: E501
    )


def ask_user(
    tool_names: list[str] | str,
    mcp_server_names: list[str] | str | None = None,
    handler: t.Callable[[str, dict], t.Awaitable[bool]] | None = None,
    mcp_server_config: t.Any | None = None,
    argument_predicate: t.Callable[[dict], bool] | None = None,
    user_ids: list[str] | None = None,
    tenant_ids: list[str] | None = None,
) -> Policy:
    """Create a policy that asks user for confirmation before executing tools.

    Args:
        tool_names: List of tool names or single tool name to require confirmation.
        mcp_server_names: Optional list of MCP server names or single server name.
        handler: Optional async handler function. If None, uses default handler.
                  Handler receives (tool_name, args) and should return True to allow.
        mcp_server_config: Optional MCP server configuration object. If provided,
            extracts server name from config and asks user for all tools from that server.

    Returns:
        A Policy with ASK_USER action for the specified tools.
    """
    if isinstance(tool_names, str):
        tool_names = [tool_names]

    if isinstance(mcp_server_names, str):
        mcp_server_names = [mcp_server_names]
    elif mcp_server_names is None:
        mcp_server_names = []

    # If MCP server config is provided, extract server name
    if mcp_server_config is not None:
        if hasattr(mcp_server_config, "name"):
            mcp_server_names = [mcp_server_config.name]
            # If no tool names specified, ask user for all tools from this server
            if not tool_names:
                tool_names = []  # Empty means all tools from this server

    return Policy(
        action=PolicyAction.ASK_USER,
        tool_names=tool_names,
        mcp_server_names=mcp_server_names,
        handler=handler,
        argument_predicate=argument_predicate,
        user_ids=user_ids or [],
        tenant_ids=tenant_ids or [],
        description=f"Ask user for tools: {tool_names if tool_names else 'all'} from servers: {mcp_server_names if mcp_server_names else 'all'}",  # noqa: E501
    )


# Default handler for ask_user
async def default_ask_user_handler(tool_name: str, args: dict) -> bool:
    """Default handler for ask_user policy - prompts user in terminal.

    Args:
        tool_name: Name of the tool being executed.
        args: Arguments being passed to the tool.

    Returns:
        True if user approves, False otherwise.
    """
    try:
        response = input(f"Allow tool '{tool_name}' with args {args}? (y/n): ")
        return response.lower().strip() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
