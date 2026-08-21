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

Provides a priority-based tool authorization policy framework (APPROVE, DENY, ASK_USER)
with 9 evaluation priority buckets, workspace path sandboxing (workspace_only),
and fail-closed default execution guardrails.

Priority Hierarchy:
  Specific Deny > Specific Ask > Specific Allow >
  Prefix Deny   > Prefix Ask   > Prefix Allow   >
  Global Deny   > Global Ask   > Global Allow
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import inspect
import logging
import os
import pathlib
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Union


_logger = logging.getLogger(__name__)

Predicate = Callable[..., bool | Awaitable[bool]]
AskUserHandler = Callable[[str, dict[str, Any]], bool | Awaitable[bool]]

_WILDCARD = "*"


class Decision(enum.Enum):
    """Outcome a policy rule can produce."""

    APPROVE = "APPROVE"
    DENY = "DENY"
    ASK_USER = "ASK_USER"


@dataclasses.dataclass(frozen=True)
class Policy:
    """A single tool authorization policy rule.

    Attributes:
        tool: Tool name targeted, or "*" for wildcard all tools.
        decision: The decision when this rule matches (APPROVE, DENY, ASK_USER).
        when: Optional predicate callable evaluated on the tool call argument dict.
        ask_user: Optional handler invoked when decision is ASK_USER.
        name: Human-readable policy rule name.
    """

    tool: str
    decision: Decision
    when: Predicate | None = None
    ask_user: AskUserHandler | None = None
    name: str = ""

    @property
    def priority_tier(self) -> int:
        """Computes priority tier 1 (highest) to 9 (lowest)."""
        is_wildcard = self.tool == _WILDCARD
        is_prefix = "*" in self.tool and not is_wildcard

        if not is_wildcard and not is_prefix:
            # Specific tool rule
            if self.decision == Decision.DENY:
                return 1
            if self.decision == Decision.ASK_USER:
                return 2
            if self.decision == Decision.APPROVE:
                return 3
        elif is_prefix:
            # Prefix wildcard rule (e.g. "mcp_server/*")
            if self.decision == Decision.DENY:
                return 4
            if self.decision == Decision.ASK_USER:
                return 5
            if self.decision == Decision.APPROVE:
                return 6
        else:
            # Global wildcard rule ("*")
            if self.decision == Decision.DENY:
                return 7
            if self.decision == Decision.ASK_USER:
                return 8
            if self.decision == Decision.APPROVE:
                return 9
        return 99


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


def allow(tool: str, *, when: Predicate | None = None, name: str = "") -> Policy:
    """Creates an APPROVE policy for the specified tool or wildcard."""
    return Policy(tool=tool, decision=Decision.APPROVE, when=when, name=name or f"allow_{tool}")


def deny(tool: str, *, when: Predicate | None = None, name: str = "") -> Policy:
    """Creates a DENY policy for the specified tool or wildcard."""
    return Policy(tool=tool, decision=Decision.DENY, when=when, name=name or f"deny_{tool}")


def ask_user(
    tool: str, *, handler: AskUserHandler, when: Predicate | None = None, name: str = ""
) -> Policy:
    """Creates an ASK_USER policy for the specified tool requiring user confirmation."""
    return Policy(
        tool=tool,
        decision=Decision.ASK_USER,
        when=when,
        ask_user=handler,
        name=name or f"ask_user_{tool}",
    )


def allow_all() -> Policy:
    """Creates a policy approving all tool calls."""
    return allow(_WILDCARD, name="allow_all")


def deny_all() -> Policy:
    """Creates a policy denying all tool calls."""
    return deny(_WILDCARD, name="deny_all")


def confirm_run_command(handler: AskUserHandler | None = None) -> list[Policy]:
    """Safe default policy: allows all read/general tools while requiring confirmation for shell command execution."""  # noqa: E501
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
    """Safe defaults: allows read-only file/directory tools and requires approval for write/command tools."""  # noqa: E501
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
    """Creates file path sandboxing policies restricting access strictly to allowed workspace directories."""  # noqa: E501
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
        # Allow if path is inside any workspace
        policies.append(
            allow(tool_name, when=_workspace_predicate, name=f"workspace_allow_{tool_name}")
        )
        # Deny if path is outside workspace
        policies.append(
            deny(tool_name, when=_outside_workspace_predicate, name=f"workspace_deny_{tool_name}")
        )

    return policies


# ---------------------------------------------------------------------------
# Policy Evaluator Engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Evaluates a list of Policy rules against a tool call."""

    def __init__(self, policies: Sequence[Policy] | None = None) -> None:
        self.policies = sorted(policies or [], key=lambda p: p.priority_tier)

    def add_policy(self, policy: Policy) -> None:
        """Adds a policy rule and re-sorts by priority tier."""
        self.policies.append(policy)
        self.policies.sort(key=lambda p: p.priority_tier)

    async def evaluate(
        self, tool_name: str, args: dict[str, Any]
    ) -> tuple[Decision, Policy | None]:
        """Evaluates policies in priority order. Returns (Decision, matching_policy)."""
        for pol in self.policies:
            if not self._tool_matches(pol.tool, tool_name):
                continue

            if pol.when is not None:
                try:
                    res = pol.when(args)
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

        # Default fail-closed if policies are configured, else APPROVE
        if self.policies:
            return Decision.DENY, None
        return Decision.APPROVE, None

    @staticmethod
    def _tool_matches(pattern: str, tool_name: str) -> bool:
        if pattern == _WILDCARD:
            return True
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return tool_name.startswith(f"{prefix}/") or tool_name.startswith(f"{prefix}_")
        return pattern.lower() == tool_name.lower()


__all__ = [
    "Decision",
    "Policy",
    "PolicyEngine",
    "allow",
    "allow_all",
    "ask_user",
    "confirm_run_command",
    "deny",
    "deny_all",
    "safe_defaults",
    "workspace_only",
]
