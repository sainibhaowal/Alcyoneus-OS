"""Router Agent for Alcyoneus OS.

A flexible router agent that routes execution to different nodes based on
a router function's output. Supports conditional routing, tool nodes, and
custom route mappings.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from alcyoneus.core.graph import CompiledGraph, StateGraph, ToolNode
from alcyoneus.core.state.agent_state import AgentState
from alcyoneus.utils.constants import END


TState = TypeVar("TState", bound=AgentState)


class RouterAgent(Generic[TState]):
    """
    A router agent that routes execution based on a router function.

    The router function determines which route to take based on the current state.
    Routes can be:
    - Regular functions that process state and return updated state
    - Tool nodes for tool execution
    - Other compiled graphs

    Example:
        >>> def router(state):
        ...     return state  # router just inspects state
        >>> def search(state):
        ...     return state
        >>> agent = RouterAgent[AgentState]()
        >>> compiled = agent.compile(
        ...     router_node=router,
        ...     routes={"search": search},
        ... )
    """

    def __init__(
        self,
        state: TState | None = None,
        router_node: Callable[[TState], TState] | None = None,
        routes: dict[str, Callable[[TState], TState] | ToolNode] | None = None,
        condition: Callable[[TState], str] | None = None,
        checkpointer: Any = None,
        store: Any = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
    ):
        """
        Initialize RouterAgent.

        Args:
            state: Optional initial state. If not provided, a new AgentState is created.
            router_node: Optional router function. If provided with routes, compiles immediately.
            routes: Optional route handlers. If provided with router_node, compiles immediately.
            condition: Optional condition function for routing.
            checkpointer: Optional checkpointer for persistence.
            store: Optional store for long-term memory.
            interrupt_before: Nodes to interrupt before.
            interrupt_after: Nodes to interrupt after.
        """
        self.state = state or AgentState()
        self._graph: CompiledGraph | None = None

        # Compile immediately if router_node and routes provided
        if router_node is not None and routes is not None:
            self._graph = self.compile(
                router_node=router_node,
                routes=routes,
                condition=condition,
                checkpointer=checkpointer,
                store=store,
                interrupt_before=interrupt_before,
                interrupt_after=interrupt_after,
            )
        else:
            # Compile a minimal default graph
            self._graph = self._compile_default()

    def _compile_default(self) -> CompiledGraph:
        """Compile a default pass-through graph."""
        graph = StateGraph(self.state.__class__ if self.state else AgentState)

        def passthrough(state: TState) -> TState:
            return state

        graph.add_node("passthrough", passthrough)
        graph.set_entry_point("passthrough")
        graph.add_edge("passthrough", END)

        return graph.compile()

    def compile(
        self,
        router_node: Callable[[TState], TState] | tuple[Callable[[TState], TState], str],
        routes: dict[
            str,
            Callable[[TState], TState]
            | ToolNode
            | tuple[Callable[[TState], TState] | ToolNode, str],
        ],
        condition: Callable[[TState], str] | None = None,
        checkpointer: Any = None,
        store: Any = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        path_map: dict[str, str] | None = None,
    ) -> CompiledGraph:
        """
        Compile the router agent into an executable graph.

        Args:
            router_node: Function that processes state and determines routing.
                Can be a callable or a tuple of (callable, node_name).
                Should return the updated state.
            routes: Dictionary mapping route names to handler functions, ToolNodes,
                or tuples of (callable/ToolNode, node_name).
            condition: Optional function that extracts route name from state.
                If not provided, looks for 'route' key in state.context.
            checkpointer: Optional checkpointer for persistence.
            store: Optional store for long-term memory.
            interrupt_before: Nodes to interrupt before.
            interrupt_after: Nodes to interrupt after.
            path_map: Optional mapping from condition results to node names.
                If not provided, uses route names directly.

        Returns:
            CompiledGraph ready for execution.
        """
        # Validate routes
        if not routes:
            raise ValueError("routes must be a non-empty dict")

        # Multiple routes require a condition
        if len(routes) > 1 and condition is None:
            raise ValueError("condition must be provided when multiple routes are defined")

        # Validate router_node
        if isinstance(router_node, tuple):
            if len(router_node) != 2 or not callable(router_node[0]):
                raise ValueError("router_node[0] must be callable")
            router_callable, router_name = router_node
        else:
            if not callable(router_node):
                raise ValueError("router_node must be callable")
            router_callable = router_node
            router_name = "ROUTER"

        # Validate routes
        for route_key, handler in routes.items():
            if isinstance(handler, tuple):
                if len(handler) != 2 or not (
                    callable(handler[0]) or isinstance(handler[0], ToolNode)
                ):
                    raise ValueError(f"Route '{route_key}'[0] must be callable or ToolNode")
            elif not (callable(handler) or isinstance(handler, ToolNode)):
                raise ValueError(f"Route '{route_key}' must be callable or ToolNode")

        graph = StateGraph(self.state.__class__ if self.state else AgentState)

        graph.add_node(router_name, router_callable)

        # Process routes - handle both callable and tuple formats
        route_names = []
        for route_key, handler in routes.items():
            if isinstance(handler, tuple):
                handler_callable, handler_name = handler
                graph.add_node(handler_name, handler_callable)
                route_names.append(handler_name)
            else:
                graph.add_node(route_key, handler)
                route_names.append(route_key)

        # Set entry point
        graph.set_entry_point(router_name)

        # Add conditional edges from router to routes
        if condition is None:
            # Default condition: look for 'route' in context
            def default_condition(state: TState) -> str:
                if hasattr(state, "context") and state.context:
                    for msg in state.context:
                        if hasattr(msg, "content") and isinstance(msg.content, dict):
                            if "route" in msg.content:
                                return msg.content["route"]
                return END

            condition = default_condition

        # Build path_map for conditional edges
        if path_map is None:
            path_map = {name: name for name in route_names}
            path_map[END] = END

        # Add conditional edges
        graph.add_conditional_edges(router_name, condition, path_map)

        # Add edges from routes back to router (for multi-turn)
        for name in route_names:
            graph.add_edge(name, router_name)

        # Compile
        self._graph = graph.compile(
            checkpointer=checkpointer,
            store=store,
            interrupt_before=interrupt_before,
            interrupt_after=interrupt_after,
        )

        return self._graph

    @property
    def graph(self) -> CompiledGraph | None:
        """Get the compiled graph."""
        return self._graph


# Convenience function for simple routing
def create_router_agent(
    router_fn: Callable[[TState], TState],
    routes: dict[str, Callable[[TState], TState] | ToolNode],
    **compile_kwargs,
) -> CompiledGraph:
    """
    Create and compile a router agent in one call.

    Args:
        router_fn: Router function
        routes: Route handlers
        **compile_kwargs: Additional arguments passed to compile()

    Returns:
        Compiled graph
    """
    agent = RouterAgent()
    return agent.compile(router_fn, routes, **compile_kwargs)


__all__ = ["RouterAgent", "create_router_agent"]
