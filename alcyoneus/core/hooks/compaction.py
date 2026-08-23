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
"""Compaction hooks for alcyoneus OS.

Provides hooks for session compaction events, similar to Google Antigravity SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from alcyoneus.core.hooks.context import HookContext
from alcyoneus.core.state import AgentState


class CompactionEvent:
    """Event triggered when session compaction occurs."""

    def __init__(
        self,
        original_state: AgentState,
        compacted_state: AgentState,
        removed_messages: list[Any],
        reason: str = "context_window_exceeded",
    ):
        """Initialize compaction event.

        Args:
            original_state: State before compaction.
            compacted_state: State after compaction.
            removed_messages: Messages removed during compaction.
            reason: Reason for compaction.
        """
        self.original_state = original_state
        self.compacted_state = compacted_state
        self.removed_messages = removed_messages
        self.reason = reason


class OnCompactionHook(ABC):
    """Abstract base class for compaction hooks.

    Compaction hooks are called when the session state is compacted
    (e.g., when context window is exceeded and old messages are removed).
    """

    @abstractmethod
    async def on_compaction(self, context: HookContext, event: CompactionEvent) -> None:
        """Handle compaction event.

        Args:
            context: Hook context with session/turn info.
            event: Compaction event details.
        """


def on_compaction(func: Callable) -> OnCompactionHook:
    """Decorator to create an OnCompactionHook from an async function.

    Args:
        func: Async function with signature (context, event) -> None.

    Returns:
        OnCompactionHook instance.
    """

    class _FuncCompactionHook(OnCompactionHook):
        async def on_compaction(self, context: HookContext, event: CompactionEvent) -> None:
            await func(context, event)

    return _FuncCompactionHook()


def _estimate_token_count(messages: list[Any]) -> int:
    """Rough token estimate for a list of messages.

    Approximates tokens as one token per 4 characters of stringified content,
    falling back to a count of messages when no content is available.

    Args:
        messages: List of message-like objects or dicts.

    Returns:
        Estimated token count.
    """
    total = 0
    for msg in messages:
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                text = getattr(block, "text", None)
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                if text:
                    total += max(1, len(str(text)) // 4)
        elif content:
            total += max(1, len(str(content)) // 4)
        else:
            total += 1
    return total


class CompactionPolicy(ABC):
    """Base policy that decides when and how to compact a conversation.

    Subclasses implement :meth:`should_compact` (whether compaction is needed)
    and optionally :meth:`compact` to produce the compacted state. If
    :meth:`compact` is not overridden, a default strategy keeps the system
    prompt and the most recent messages while removing older turns.
    """

    def __init__(self, hooks: list[OnCompactionHook] | None = None):
        self.hooks: list[OnCompactionHook] = hooks or []

    @abstractmethod
    async def should_compact(
        self,
        state: AgentState,
        context: HookContext | None = None,
    ) -> bool:
        """Decide whether the conversation should be compacted.

        Args:
            state: Current agent state.
            context: Optional hook context.

        Returns:
            True if compaction should run.
        """

    async def compact(
        self,
        state: AgentState,
        context: HookContext | None = None,
    ) -> AgentState:
        """Produce a compacted state.

        Default implementation keeps the system prompt and the last
        ``keep_recent`` messages, dropping everything older.

        Args:
            state: Current agent state.
            context: Optional hook context.

        Returns:
            A new compacted agent state.
        """
        messages = list(getattr(state, "context", None) or [])
        removed = messages[: -self.keep_recent] if self.keep_recent else []
        kept = messages[-self.keep_recent :] if self.keep_recent else []
        compacted = state.model_copy(deep=True)
        compacted.context = kept

        event = CompactionEvent(
            original_state=state,
            compacted_state=compacted,
            removed_messages=removed,
            reason=self.reason,
        )
        for hook in self.hooks:
            await hook.on_compaction(context or HookContext(), event)
        return compacted

    @property
    def keep_recent(self) -> int:
        """Number of most-recent messages to keep when compacting."""
        return 10

    @property
    def reason(self) -> str:
        """Reason label used in compaction events."""
        return "context_window_exceeded"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(hooks={len(self.hooks)})"


class DynamicCompactionPolicy(CompactionPolicy):
    """Compaction policy that triggers based on estimated token or message count.

    The threshold can be static (``max_tokens`` / ``max_messages``) or adapt
    over time: pass ``adapt_to_usage=True`` to grow the token threshold by
    ``growth_rate`` each time compaction runs, mirroring how long-running
    sessions learn a comfortable context budget.

    Args:
        max_tokens: Trigger compaction when the estimated token count exceeds
            this value. Ignored when ``None``.
        max_messages: Trigger compaction when the message count exceeds this
            value. Ignored when ``None``.
        keep_recent: Number of most-recent messages to preserve.
        adapt_to_usage: Whether to grow the token threshold after each run.
        growth_rate: Multiplier applied to the token threshold when adapting.
        hooks: Compaction hooks to fire.
    """

    def __init__(
        self,
        max_tokens: int | None = None,
        max_messages: int | None = None,
        keep_recent: int = 10,
        adapt_to_usage: bool = False,
        growth_rate: float = 1.5,
        hooks: list[OnCompactionHook] | None = None,
    ):
        super().__init__(hooks=hooks)
        self.max_tokens = max_tokens
        self.max_messages = max_messages
        self._keep_recent = keep_recent
        self._adapt_to_usage = adapt_to_usage
        self._growth_rate = growth_rate

    async def should_compact(
        self,
        state: AgentState,
        context: HookContext | None = None,
    ) -> bool:
        messages = list(getattr(state, "context", None) or [])
        if self.max_messages is not None and len(messages) > self.max_messages:
            return True
        if self.max_tokens is not None:
            return _estimate_token_count(messages) > self.max_tokens
        return False

    async def compact(
        self,
        state: AgentState,
        context: HookContext | None = None,
    ) -> AgentState:
        compacted = await super().compact(state, context)
        if self._adapt_to_usage and self.max_tokens is not None:
            self.max_tokens = int(self.max_tokens * self._growth_rate)
        return compacted

    @property
    def keep_recent(self) -> int:
        return self._keep_recent

    @property
    def reason(self) -> str:
        if self.max_messages is not None:
            return "message_limit_exceeded"
        return "token_limit_exceeded"

    def __repr__(self) -> str:
        return (
            f"DynamicCompactionPolicy(max_tokens={self.max_tokens}, "
            f"max_messages={self.max_messages}, keep_recent={self._keep_recent})"
        )


class ResponsesCompactionSession:
    """Session wrapper that compacts conversation history via a policy.

    Implements the same surface as the storage sessions
    (``get_items``/``add_items``/``clear``) while transparently compacting the
    in-memory history whenever a :class:`CompactionPolicy` says it is needed.
    Useful for long-running OpenAI-Responses-style agents.

    Args:
        session_id: Identifier for the session.
        policy: Compaction policy to apply. Defaults to a
            :class:`DynamicCompactionPolicy` with a 10k token threshold.
    """

    def __init__(
        self,
        session_id: str,
        policy: CompactionPolicy | None = None,
    ):
        self.session_id = session_id
        self.policy = policy or DynamicCompactionPolicy(max_tokens=10_000)
        self._items: list[Any] = []
        self.compaction_count = 0

    async def get_items(self) -> list[Any]:
        """Return the current conversation history."""
        return list(self._items)

    async def add_items(self, items: list[Any]) -> None:
        """Append items, compacting first if the policy demands it.

        Args:
            items: Items (messages / responses) to append.
        """
        self._items.extend(items)
        state = _state_from_items(self._items)
        if await self.policy.should_compact(state):
            compacted = await self.policy.compact(state)
            self._items = list(getattr(compacted, "context", None) or self._items)
            self.compaction_count += 1

    async def clear(self) -> None:
        """Clear the conversation history."""
        self._items.clear()
        self.compaction_count = 0

    @property
    def compacted(self) -> int:
        """Number of times compaction has run."""
        return self.compaction_count


def _state_from_items(items: list[Any]) -> AgentState:
    """Build a lightweight AgentState wrapper around items.

    Args:
        items: Conversation items.

    Returns:
        An AgentState whose ``context`` are the given items.
    """
    state = AgentState(context=list(items))
    return state


__all__ = [
    "CompactionEvent",
    "CompactionPolicy",
    "DynamicCompactionPolicy",
    "OnCompactionHook",
    "ResponsesCompactionSession",
    "on_compaction",
]
