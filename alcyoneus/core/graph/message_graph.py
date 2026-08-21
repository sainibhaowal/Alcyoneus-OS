"""MessageGraph: a graph whose state is a bare message list.

LangGraph-compatible convenience graph. Instead of a structured ``AgentState``,
the state is a plain list of ``Message`` objects. Nodes may return:

- a ``dict`` with ``{"messages": [...]}``
- a list of ``Message`` (implicitly merged into the conversation)
- a ``Command`` (goto/update/resume)
- ``RemoveMessage`` tombstones / ``REMOVE_ALL_MESSAGES`` to delete history

Example:
    >>> from alcyoneus.core.graph import MessageGraph, Message
    >>> from alcyoneus.utils import START, END
    >>> graph = MessageGraph()
    >>> graph.add_node("echo", lambda state: [Message.text_message("echo: " + state[-1].text())])
    >>> graph.add_edge(START, "echo")
    >>> graph.add_edge("echo", END)
    >>> compiled = graph.compile()
    >>> result = compiled.invoke({"messages": [Message.text_message("hello")]})
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from alcyoneus.core.state import AgentState, Message
from alcyoneus.core.state.remove_message import is_remove_message
from alcyoneus.utils import END, START

from .state_graph import StateGraph


logger = logging.getLogger("alcyoneus.graph")


class MessageGraphState(AgentState):
    """Minimal AgentState that only carries the ``messages`` channel.

    The ``context`` list from :class:`AgentState` acts as the message channel;
    ``add_messages`` reducer semantics (including ``RemoveMessage`` tombstones)
    are inherited.
    """


class MessageGraph(StateGraph):
    """A StateGraph whose state is a plain message list.

    Provides a thin convenience layer over :class:`StateGraph`:

    - Entry points accept either ``{"messages": [...]}`` dicts or bare message lists.
    - Node outputs of type ``list[Message]`` (or ``Message``) are automatically
      merged into the conversation with ``add_messages``.
    - ``RemoveMessage`` tombstones and ``REMOVE_ALL_MESSAGES`` are honored.
    """

    def __init__(
        self,
        publisher: Any | None = None,
        id_generator: Any | None = None,
        container: Any | None = None,
    ):
        super().__init__(
            state=MessageGraphState(),
            publisher=publisher,
            id_generator=id_generator,
            container=container,
        )

    def add_node(
        self,
        name_or_func: str | Callable,
        func: Callable | Any | None = None,
        **kwargs: Any,
    ) -> MessageGraph:
        """Add a node to the message graph.

        Wraps the raw node function so message-list outputs are normalized into
        ``{"messages": [...]}`` updates.
        """
        if callable(name_or_func) and func is None:
            name = name_or_func.__name__
            raw_func: Callable = name_or_func
        elif isinstance(name_or_func, str) and callable(func):
            name = name_or_func
            raw_func = func
        else:
            raise ValueError("Invalid arguments for MessageGraph.add_node")

        def wrapper(
            state: MessageGraphState, config: dict[str, Any], **deps: Any
        ) -> dict[str, Any]:
            result = raw_func(state, config, **deps)
            return self._normalize_output(result)

        return super().add_node(name, wrapper, **kwargs)

    def _normalize_output(self, result: Any) -> dict[str, Any]:
        """Normalize node output into a state update dict."""
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        if isinstance(result, Message):
            return {"messages": [result]}
        if isinstance(result, list):
            if result and all(isinstance(m, (Message,)) or is_remove_message(m) for m in result):
                return {"messages": result}
            return {"messages": result}
        raise TypeError(
            f"MessageGraph nodes must return a dict, Message, or list of Messages; "
            f"got {type(result).__name__}."
        )

    def set_entry_point(self, node_name: str) -> MessageGraph:
        """Set the entry point for the message graph."""
        self.entry_point = node_name
        self.add_edge(START, node_name)
        return self

    def set_sequence(self, sequence: list[str], **kwargs: Any) -> MessageGraph:
        """Set a linear chain of message-graph nodes."""
        super().set_sequence(sequence, **kwargs)
        return self

    def set_conditional_entry_point(
        self,
        condition: Callable,
        path_map: dict[str, str] | None = None,
    ) -> MessageGraph:
        """Set a runtime-chosen conditional entry point."""
        super().set_conditional_entry_point(condition, path_map)
        return self

    def set_finish_point(self, node_name: str) -> MessageGraph:
        """Set the finish point for the message graph."""
        super().set_finish_point(node_name)
        return self

    def add_edge(self, from_node: str, to_node: str) -> MessageGraph:
        """Add a static edge."""
        super().add_edge(from_node, to_node)
        return self

    def add_conditional_edges(
        self,
        from_node: str,
        condition: Callable,
        path_map: dict[str, str] | None = None,
    ) -> MessageGraph:
        """Add conditional routing."""
        super().add_conditional_edges(from_node, condition, path_map)
        return self

    @property
    def end(self) -> str:
        """Convenience accessor for the END node name."""
        return END


__all__ = [
    "MessageGraph",
    "MessageGraphState",
]
