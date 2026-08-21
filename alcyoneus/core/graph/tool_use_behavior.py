"""
Tool use behavior controls for agents.

Defines the ``ToolUseBehavior`` enum and ``StopAtTools`` wrapper that determine
how an agent loop should behave after the model emits tool calls:

- ``run_llm_again`` (default): execute the requested tools, append the results,
  and call the LLM again so it can continue the conversation.
- ``stop_on_first_tool``: execute exactly one tool call then stop, returning
  control to the graph loop (useful for human-in-the-loop tool approval flows
  or map-reduce where each tool call is handled independently).
- ``StopAtTools``: execute tool calls until a designated list of tools is
  reached, then stop.

These mirror OpenAI Agents SDK / LangGraph semantics while staying native to
Alcyoneus OS.

Example:
    >>> from alcyoneus.core.graph import Agent, ToolUseBehavior
    >>> agent = Agent(model="gpt-4o", tool_use_behavior=ToolUseBehavior.STOP_ON_FIRST_TOOL)
"""

from __future__ import annotations

import enum
from typing import Any


class ToolUseBehavior(str, enum.Enum):
    """How the agent loop proceeds after a tool call."""

    RUN_LLM_AGAIN = "run_llm_again"
    STOP_ON_FIRST_TOOL = "stop_on_first_tool"

    def __str__(self) -> str:
        return self.value


class StopAtTools:
    """Wrapper carrying a list of tool names to stop at after execution.

    When the agent loop encounters a tool whose name is in ``tools`` it runs
    that tool and then stops (does not call the LLM again), handing control
    back to the graph.

    Attributes:
        tools (set[str]): Names of tools to stop after executing.

    Example:
        >>> from alcyoneus.core.graph import StopAtTools
        >>> behavior = StopAtTools(tools={"human_approval", "billing_api"})
    """

    def __init__(self, tools: list[str] | set[str] | tuple[str, ...] | None = None):
        self.tools: set[str] = set(tools or [])

    def should_stop(self, tool_name: str) -> bool:
        """Return True if execution should stop after *tool_name* runs."""
        return tool_name in self.tools

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, StopAtTools):
            return self.tools == other.tools
        return NotImplemented

    def __repr__(self) -> str:
        return f"StopAtTools(tools={sorted(self.tools)!r})"


def normalize_tool_use_behavior(
    behavior: str | ToolUseBehavior | StopAtTools | None,
) -> ToolUseBehavior | StopAtTools:
    """Normalize a tool_use_behavior value into a canonical form.

    Accepts ``None`` (defaults to ``RUN_LLM_AGAIN``), a ``ToolUseBehavior``
    member, a string of the enum value, or a ``StopAtTools`` wrapper.

    Args:
        behavior: The raw tool_use_behavior value.

    Returns:
        ToolUseBehavior | StopAtTools: The normalized behavior.

    Raises:
        ValueError: If the value cannot be parsed.
    """
    if behavior is None:
        return ToolUseBehavior.RUN_LLM_AGAIN
    if isinstance(behavior, (ToolUseBehavior, StopAtTools)):
        return behavior
    if isinstance(behavior, str):
        try:
            return ToolUseBehavior(behavior)
        except ValueError:
            raise ValueError(
                f"Invalid tool_use_behavior: {behavior!r}. "
                f"Expected one of {[m.value for m in ToolUseBehavior]} or a StopAtTools instance."
            ) from None
    raise TypeError(
        f"tool_use_behavior must be a ToolUseBehavior, StopAtTools, string, or None; "
        f"got {type(behavior).__name__}."
    )


__all__ = [
    "StopAtTools",
    "ToolUseBehavior",
    "normalize_tool_use_behavior",
]
