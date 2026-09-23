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

"""Declarative Safety & Policy Engine for Alcyoneus OS.

Provides a unified, priority-based tool authorization policy framework
with 9 evaluation priority buckets, MCP server filtering, workspace path
sandboxing (workspace_only), user/tenant scoping, and fail-closed default
execution guardrails.

Priority Hierarchy:
  Specific Deny > Specific Ask > Specific Allow >
  Prefix Deny   > Prefix Ask   > Prefix Allow   >
  Global Deny   > Global Ask   > Global Allow
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import functools
import inspect
import logging
import os
import pathlib
import sys
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from typing import Any, Union, cast


_logger = logging.getLogger("alcyoneus.core.policy")

Predicate = Callable[..., bool | Awaitable[bool]]
AskUserHandler = Callable[[str, dict[str, Any]], bool | Awaitable[bool]]

_WILDCARD = "*"


class Decision(enum.Enum):
    """Outcome a policy rule can produce."""

    APPROVE = "APPROVE"
    DENY = "DENY"
    ASK_USER = "ASK_USER"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            val = other.upper()
            if self is Decision.APPROVE and val in ("APPROVE", "ALLOW"):
                return True
            if self is Decision.DENY and val == "DENY":
                return True
            if self is Decision.ASK_USER and val == "ASK_USER":
                return True
            return False
        if isinstance(other, enum.Enum):
            if self is Decision.APPROVE and other.name in ("APPROVE", "ALLOW"):
                return True
            if self is Decision.DENY and other.name == "DENY":
                return True
            if self is Decision.ASK_USER and other.name == "ASK_USER":
                return True
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)


class PolicyAction(enum.Enum):
    """Action to take when a policy matches (alias compatible with Decision)."""

    ALLOW = "allow"
    DENY = "deny"
    ASK_USER = "ask_user"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            val = other.lower()
            if self is PolicyAction.ALLOW and val in ("allow", "approve"):
                return True
            if self is PolicyAction.DENY and val == "deny":
                return True
            if self is PolicyAction.ASK_USER and val == "ask_user":
                return True
            return False
        if isinstance(other, enum.Enum):
            if self is PolicyAction.ALLOW and other.name in ("ALLOW", "APPROVE"):
                return True
            if self is PolicyAction.DENY and other.name == "DENY":
                return True
            if self is PolicyAction.ASK_USER and other.name == "ASK_USER":
                return True
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)


@dataclasses.dataclass(frozen=True)
class Policy:
    """A single tool authorization policy rule.

    Supports both single-tool and multi-tool definitions, priority tiers (1-9),
    MCP server names, user/tenant isolation, and custom argument predicates.
    """

    tool: str = _WILDCARD
    decision: Decision = Decision.APPROVE
    when: Predicate | None = None
    ask_user: AskUserHandler | None = None
    name: str = ""
    tool_names: tuple[str, ...] = dataclasses.field(default_factory=tuple)
    mcp_server_names: tuple[str, ...] = dataclasses.field(default_factory=tuple)
    handler: AskUserHandler | None = None
    description: str = ""
    argument_predicate: Predicate | None = None
    user_ids: tuple[str, ...] = dataclasses.field(default_factory=tuple)
    tenant_ids: tuple[str, ...] = dataclasses.field(default_factory=tuple)
    action: PolicyAction | None = None

    def __post_init__(self) -> None:
        # Normalize tool_names tuple
        if self.tool_names and isinstance(self.tool_names, (list, tuple)):
            names_tuple = tuple(self.tool_names)
            object.__setattr__(self, "tool_names", names_tuple)
            if self.tool == _WILDCARD and names_tuple:
                object.__setattr__(
                    self, "tool", names_tuple[0] if len(names_tuple) == 1 else ",".join(names_tuple)
                )
        elif self.tool and self.tool != _WILDCARD and not self.tool_names:
            object.__setattr__(self, "tool_names", (self.tool,))

        # Harmonize decision and action
        if self.action is not None and self.decision == Decision.APPROVE:
            if self.action == PolicyAction.DENY:
                object.__setattr__(self, "decision", Decision.DENY)
            elif self.action == PolicyAction.ASK_USER:
                object.__setattr__(self, "decision", Decision.ASK_USER)
            else:
                object.__setattr__(self, "decision", Decision.APPROVE)

        if self.action is None:
            if self.decision == Decision.DENY:
                object.__setattr__(self, "action", PolicyAction.DENY)
            elif self.decision == Decision.ASK_USER:
                object.__setattr__(self, "action", PolicyAction.ASK_USER)
            else:
                object.__setattr__(self, "action", PolicyAction.ALLOW)

        # Harmonize predicates
        if self.argument_predicate is not None and self.when is None:
            object.__setattr__(self, "when", self.argument_predicate)
        elif self.when is not None and self.argument_predicate is None:
            object.__setattr__(self, "argument_predicate", self.when)

        # Harmonize handlers
        if self.handler is not None and self.ask_user is None:
            object.__setattr__(self, "ask_user", self.handler)
        elif self.ask_user is not None and self.handler is None:
            object.__setattr__(self, "handler", self.ask_user)

        # Harmonize name and description
        if self.description and not self.name:
            object.__setattr__(self, "name", self.description)
        elif self.name and not self.description:
            object.__setattr__(self, "description", self.name)

        # Normalize server/user/tenant collections to tuples
        if isinstance(self.mcp_server_names, (list, set)):
            object.__setattr__(self, "mcp_server_names", tuple(self.mcp_server_names))
        if isinstance(self.user_ids, (list, set)):
            object.__setattr__(self, "user_ids", tuple(self.user_ids))
        if isinstance(self.tenant_ids, (list, set)):
            object.__setattr__(self, "tenant_ids", tuple(self.tenant_ids))

    @property
    def priority_tier(self) -> int:
        """Computes priority tier 1 (highest) to 9 (lowest)."""
        tools = (
            self.tool_names if self.tool_names else ((self.tool,) if self.tool else (_WILDCARD,))
        )
        is_wildcard = any(t == _WILDCARD for t in tools) or self.tool == _WILDCARD
        is_prefix = any("*" in t and t != _WILDCARD for t in tools) or (
            "*" in self.tool and not is_wildcard
        )

        if not is_wildcard and not is_prefix:
            if self.decision == Decision.DENY:
                return 1
            if self.decision == Decision.ASK_USER:
                return 2
            if self.decision == Decision.APPROVE:
                return 3
        elif is_prefix:
            if self.decision == Decision.DENY:
                return 4
            if self.decision == Decision.ASK_USER:
                return 5
            if self.decision == Decision.APPROVE:
                return 6
        else:
            if self.decision == Decision.DENY:
                return 7
            if self.decision == Decision.ASK_USER:
                return 8
            if self.decision == Decision.APPROVE:
                return 9
        return 99

    def matches(
        self,
        tool_name: str,
        mcp_server_name: str | None = None,
        args: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Check if this policy applies to the given tool execution parameters."""
        matched = False
        tools = self.tool_names if self.tool_names else (self.tool,)
        for pattern in tools:
            if self._tool_matches(pattern, tool_name):
                matched = True
                break
        if not matched:
            return False

        if self.mcp_server_names:
            if not mcp_server_name or mcp_server_name not in self.mcp_server_names:
                return False

        context = context or {}
        if self.user_ids and str(context.get("user_id")) not in self.user_ids:
            return False
        if self.tenant_ids and str(context.get("tenant_id")) not in self.tenant_ids:
            return False

        pred = self.argument_predicate or self.when
        if pred is not None:
            try:
                res = pred(args or {})
                if not inspect.isawaitable(res) and not res:
                    return False
            except Exception:
                return False

        return True

    @staticmethod
    def _tool_matches(pattern: str, tool_name: str) -> bool:
        if pattern == _WILDCARD:
            return True
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return tool_name.startswith(f"{prefix}/") or tool_name.startswith(f"{prefix}_")
        return pattern.lower() == tool_name.lower()


# ---------------------------------------------------------------------------
# Path Sandboxing Helpers
# ---------------------------------------------------------------------------

PathOrStr = Union[str, os.PathLike[str]]


def _secure_normalize_path(path: PathOrStr) -> pathlib.Path:
    """Canonicalizes paths by resolving symlinks and relative segments."""
    return pathlib.Path(path).resolve()


@functools.lru_cache(maxsize=256)
def _is_case_insensitive(path: pathlib.Path) -> bool:
    """Checks if filesystem at path is case-insensitive."""
    try:
        if not path.exists():
            return sys.platform in ("win32", "darwin")
    except OSError:
        return sys.platform in ("win32", "darwin")

    parent = path.parent
    name = path.name
    if not name:
        return sys.platform in ("win32", "darwin")

    swapped_name = "".join(c.swapcase() for c in name)
    if swapped_name == name:
        if parent and parent != path:
            return _is_case_insensitive(parent)
        return sys.platform in ("win32", "darwin")

    try:
        return path.samefile(parent / swapped_name)
    except OSError:
        return False


def _is_path_in_workspace(target_path: PathOrStr, workspace_path: PathOrStr) -> bool:
    """Returns True if canonicalized target_path lies inside canonicalized workspace_path."""
    try:
        norm_target = _secure_normalize_path(target_path)
        norm_ws = _secure_normalize_path(workspace_path)
    except OSError:
        return False

    if _is_case_insensitive(norm_ws):
        t_parts = [p.casefold() for p in norm_target.parts]
        w_parts = [p.casefold() for p in norm_ws.parts]
    else:
        t_parts = list(norm_target.parts)
        w_parts = list(norm_ws.parts)

    if len(t_parts) < len(w_parts):
        return False

    return t_parts[: len(w_parts)] == w_parts


# ---------------------------------------------------------------------------
# Builder Functions
# ---------------------------------------------------------------------------


def _normalize_servers(
    mcp_server_names: Sequence[str] | str | None,
    mcp_server_config: Any | None,
) -> tuple[str, ...]:
    if mcp_server_config is not None and hasattr(mcp_server_config, "name"):
        return (str(mcp_server_config.name),)
    if isinstance(mcp_server_names, str):
        return (mcp_server_names,)
    if mcp_server_names is not None:
        return tuple(mcp_server_names)
    return ()


def allow(
    tool: str | Sequence[str] = _WILDCARD,
    *,
    mcp_server_names: Sequence[str] | str | None = None,
    mcp_server_config: Any | None = None,
    when: Predicate | None = None,
    argument_predicate: Predicate | None = None,
    user_ids: Sequence[str] | None = None,
    tenant_ids: Sequence[str] | None = None,
    name: str = "",
    description: str = "",
) -> Policy:
    """Creates an APPROVE/ALLOW policy for the specified tool(s) or wildcard."""
    servers = _normalize_servers(mcp_server_names, mcp_server_config)
    pred = argument_predicate or when
    desc = description or name

    if isinstance(tool, str):
        rule_name = desc or f"allow_{tool}"
        return Policy(
            tool=tool,
            decision=Decision.APPROVE,
            when=pred,
            name=rule_name,
            description=rule_name,
            mcp_server_names=servers,
            user_ids=tuple(user_ids or []),
            tenant_ids=tuple(tenant_ids or []),
        )

    tools_tuple = tuple(tool)
    rule_name = desc or f"allow_{','.join(tools_tuple) if tools_tuple else 'all'}"
    return Policy(
        tool=tools_tuple[0] if len(tools_tuple) == 1 else ",".join(tools_tuple),
        tool_names=tools_tuple,
        decision=Decision.APPROVE,
        when=pred,
        name=rule_name,
        description=rule_name,
        mcp_server_names=servers,
        user_ids=tuple(user_ids or []),
        tenant_ids=tuple(tenant_ids or []),
    )


def deny(
    tool: str | Sequence[str] = _WILDCARD,
    *,
    mcp_server_names: Sequence[str] | str | None = None,
    mcp_server_config: Any | None = None,
    when: Predicate | None = None,
    argument_predicate: Predicate | None = None,
    user_ids: Sequence[str] | None = None,
    tenant_ids: Sequence[str] | None = None,
    name: str = "",
    description: str = "",
) -> Policy:
    """Creates a DENY policy for the specified tool(s) or wildcard."""
    servers = _normalize_servers(mcp_server_names, mcp_server_config)
    pred = argument_predicate or when
    desc = description or name

    if isinstance(tool, str):
        rule_name = desc or f"deny_{tool}"
        return Policy(
            tool=tool,
            decision=Decision.DENY,
            when=pred,
            name=rule_name,
            description=rule_name,
            mcp_server_names=servers,
            user_ids=tuple(user_ids or []),
            tenant_ids=tuple(tenant_ids or []),
        )

    tools_tuple = tuple(tool)
    rule_name = desc or f"deny_{','.join(tools_tuple) if tools_tuple else 'all'}"
    return Policy(
        tool=tools_tuple[0] if len(tools_tuple) == 1 else ",".join(tools_tuple),
        tool_names=tools_tuple,
        decision=Decision.DENY,
        when=pred,
        name=rule_name,
        description=rule_name,
        mcp_server_names=servers,
        user_ids=tuple(user_ids or []),
        tenant_ids=tuple(tenant_ids or []),
    )


def ask_user(
    tool: str | Sequence[str] = _WILDCARD,
    *,
    handler: AskUserHandler | None = None,
    mcp_server_names: Sequence[str] | str | None = None,
    mcp_server_config: Any | None = None,
    when: Predicate | None = None,
    argument_predicate: Predicate | None = None,
    user_ids: Sequence[str] | None = None,
    tenant_ids: Sequence[str] | None = None,
    name: str = "",
    description: str = "",
) -> Policy:
    """Creates an ASK_USER policy for the specified tool(s) requiring confirmation."""
    servers = _normalize_servers(mcp_server_names, mcp_server_config)
    pred = argument_predicate or when
    desc = description or name

    if isinstance(tool, str):
        rule_name = desc or f"ask_user_{tool}"
        return Policy(
            tool=tool,
            decision=Decision.ASK_USER,
            when=pred,
            ask_user=handler,
            handler=handler,
            name=rule_name,
            description=rule_name,
            mcp_server_names=servers,
            user_ids=tuple(user_ids or []),
            tenant_ids=tuple(tenant_ids or []),
        )

    tools_tuple = tuple(tool)
    rule_name = desc or f"ask_user_{','.join(tools_tuple) if tools_tuple else 'all'}"
    return Policy(
        tool=tools_tuple[0] if len(tools_tuple) == 1 else ",".join(tools_tuple),
        tool_names=tools_tuple,
        decision=Decision.ASK_USER,
        when=pred,
        ask_user=handler,
        handler=handler,
        name=rule_name,
        description=rule_name,
        mcp_server_names=servers,
        user_ids=tuple(user_ids or []),
        tenant_ids=tuple(tenant_ids or []),
    )


def allow_all() -> Policy:
    """Creates a policy approving all tool calls."""
    return allow(_WILDCARD, name="allow_all", description="Allow all tools")


def deny_all() -> Policy:
    """Creates a policy denying all tool calls."""
    return deny(_WILDCARD, name="deny_all", description="Deny all tools")


def confirm_run_command(handler: AskUserHandler | None = None) -> list[Policy]:
    """Safe default policy: allows general tools while requiring confirmation for shell command execution."""
    if handler is not None:
        return [
            ask_user("shell_command", handler=handler, name="confirm_run_command"),
            ask_user("run_command", handler=handler, name="confirm_run_command"),
            allow(_WILDCARD, name="confirm_run_command_wildcard"),
        ]
    return [
        deny("shell_command", name="confirm_run_command"),
        deny("run_command", name="confirm_run_command"),
        allow(_WILDCARD, name="confirm_run_command_wildcard"),
    ]


def safe_defaults(handler: AskUserHandler) -> list[Policy]:
    """Safe defaults: allows read-only file/directory tools and requires approval for write/command tools."""
    read_only_tools = [
        "read_file",
        "view_file",
        "find_file",
        "list_directory",
        "search_web",
        "fetch",
    ]
    return [allow(t) for t in read_only_tools] + [
        ask_user(_WILDCARD, handler=handler, name="safe_defaults_fallback")
    ]


def workspace_only(workspaces: Sequence[PathOrStr]) -> list[Policy]:
    """Creates file path sandboxing policies restricting access strictly to allowed workspace directories."""
    ws_list = list(workspaces)

    file_tools = [
        "read_file",
        "view_file",
        "write_file",
        "edit_file",
        "multi_edit",
        "delete_file",
        "list_directory",
    ]

    def _workspace_predicate(args: dict[str, Any]) -> bool:
        path_arg = (
            args.get("path")
            or args.get("AbsolutePath")
            or args.get("TargetFile")
            or args.get("file_path")
            or args.get("DirectoryPath")
        )
        if not path_arg:
            return True
        return any(_is_path_in_workspace(path_arg, ws) for ws in ws_list)

    def _outside_workspace_predicate(args: dict[str, Any]) -> bool:
        path_arg = (
            args.get("path")
            or args.get("AbsolutePath")
            or args.get("TargetFile")
            or args.get("file_path")
            or args.get("DirectoryPath")
        )
        if not path_arg:
            return False
        return not any(_is_path_in_workspace(path_arg, ws) for ws in ws_list)

    policies = []
    for tool_name in file_tools:
        policies.append(
            allow(tool_name, when=_workspace_predicate, name=f"workspace_allow_{tool_name}")
        )
        policies.append(
            deny(tool_name, when=_outside_workspace_predicate, name=f"workspace_deny_{tool_name}")
        )

    return policies


async def default_ask_user_handler(tool_name: str, args: dict[str, Any]) -> bool:
    """Default handler for ask_user policy - prompts user in terminal."""
    try:
        response = input(f"Allow tool '{tool_name}' with args {args}? (y/n): ")
        return response.lower().strip() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


@dataclasses.dataclass
class ToolExecutionPolicy:
    """Execution options for tool invocation (timeouts, retries)."""

    timeout: float | None = None
    max_retries: int = 0
    retry_on_failure: bool = False


# ---------------------------------------------------------------------------
# Policy Evaluator Engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Evaluates a list of Policy rules against a tool call."""

    def __init__(
        self,
        policies: Sequence[Policy] | None = None,
        default_action: Decision | PolicyAction | None = None,
        deny_by_default: bool = False,
    ) -> None:
        self.policies: list[Policy] = sorted(policies or [], key=lambda p: p.priority_tier)
        self.default_action = default_action
        self.deny_by_default = deny_by_default

    def add_policy(self, policy: Policy) -> None:
        """Adds a policy rule and re-sorts by priority tier."""
        self.policies.append(policy)
        self.policies.sort(key=lambda p: p.priority_tier)

    async def evaluate(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        mcp_server_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[Decision, Policy | None]:
        """Evaluates policies in priority order. Returns (Decision, matching_policy)."""
        args = args or {}
        context = context or {}

        for pol in self.policies:
            if not pol.matches(
                tool_name, mcp_server_name=mcp_server_name, args=args, context=context
            ):
                continue

            pred = pol.when or pol.argument_predicate
            if pred is not None:
                try:
                    res = pred(args)
                    if inspect.isawaitable(res):
                        res = await res
                    if not res:
                        continue
                except Exception as err:
                    _logger.warning(
                        "Policy predicate for '%s' raised exception: %s. Skipping policy.",
                        pol.name,
                        err,
                    )
                    continue

            return pol.decision, pol

        # Default fallback
        if self.deny_by_default:
            return Decision.DENY, None

        if self.default_action is not None:
            if isinstance(self.default_action, Decision):
                return self.default_action, None
            if self.default_action == PolicyAction.ALLOW:
                return Decision.APPROVE, None
            if self.default_action == PolicyAction.DENY:
                return Decision.DENY, None
            return Decision.ASK_USER, None

        # Fail-closed if policies are configured, else APPROVE
        if self.policies:
            return Decision.DENY, None
        return Decision.APPROVE, None

    def evaluate_sync(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        mcp_server_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[Decision, Policy | None]:
        """Synchronous policy evaluation for non-async contexts."""
        args = args or {}
        context = context or {}

        for pol in self.policies:
            if not pol.matches(
                tool_name, mcp_server_name=mcp_server_name, args=args, context=context
            ):
                continue

            pred = pol.when or pol.argument_predicate
            if pred is not None:
                try:
                    res = pred(args)
                    if inspect.isawaitable(res):
                        res = asyncio.run(cast(Coroutine[Any, Any, Any], res))
                    if not res:
                        continue
                except Exception as err:
                    _logger.warning(
                        "Policy predicate for '%s' raised exception: %s. Skipping policy.",
                        pol.name,
                        err,
                    )
                    continue

            return pol.decision, pol

        if self.deny_by_default:
            return Decision.DENY, None

        if self.default_action is not None:
            if isinstance(self.default_action, Decision):
                return self.default_action, None
            if self.default_action == PolicyAction.ALLOW:
                return Decision.APPROVE, None
            if self.default_action == PolicyAction.DENY:
                return Decision.DENY, None
            return Decision.ASK_USER, None

        if self.policies:
            return Decision.DENY, None
        return Decision.APPROVE, None


class PolicyConfig(PolicyEngine):
    """Configuration for policy system in ToolNode (subclass of PolicyEngine for compatibility)."""

    def __init__(
        self,
        policies: Sequence[Policy] | None = None,
        default_action: PolicyAction | Decision = PolicyAction.ALLOW,
        deny_by_default: bool = False,
    ) -> None:
        super().__init__(
            policies=policies,
            default_action=default_action,
            deny_by_default=deny_by_default,
        )


__all__ = [
    "Decision",
    "Policy",
    "PolicyAction",
    "PolicyConfig",
    "PolicyEngine",
    "ToolExecutionPolicy",
    "allow",
    "allow_all",
    "ask_user",
    "confirm_run_command",
    "default_ask_user_handler",
    "deny",
    "deny_all",
    "safe_defaults",
    "workspace_only",
]
