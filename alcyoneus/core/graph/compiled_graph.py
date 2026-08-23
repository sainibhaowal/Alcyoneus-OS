from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import time
from collections.abc import AsyncIterator, Callable, Generator
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import uuid4


try:
    from injectq import InjectQ
except ImportError:

    class DummyContainer:
        _instance = None

        @classmethod
        def get_instance(cls):
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

        def activate(self):
            pass

        def compile(self, *a, **kw):
            pass

        def bind_factory(self, *a, **kw):
            pass

        def bind(self, *a, **kw):
            pass

        def bind_instance(self, *a, **kw):
            pass

        def get(self, *a, **kw):
            return None

        def try_get(self, *a, **kw):
            return kw.get("default") if len(a) < 2 else a[1]

    InjectQ = DummyContainer


from alcyoneus.core.exceptions.graph_error import GraphError
from alcyoneus.core.graph.base_agent import BaseAgent
from alcyoneus.core.graph.tool_node.base import ToolNode
from alcyoneus.core.state import AgentState
from alcyoneus.core.state.execution_state import StopRequestStatus
from alcyoneus.core.state.stream_chunks import StreamChunk
from alcyoneus.runtime.publisher.base_publisher import BasePublisher
from alcyoneus.storage.checkpointer.base_checkpointer import BaseCheckpointer
from alcyoneus.storage.store.base_store import BaseStore
from alcyoneus.utils import (
    CallbackManager,
    ResponseGranularity,
)
from alcyoneus.utils.background_task_manager import BackgroundTaskManager

from .node import Node
from .utils.invoke_handler import InvokeHandler
from .utils.stream_handler import StreamHandler


if TYPE_CHECKING:
    from types import TracebackType

    from .state_graph import StateGraph


StateT = TypeVar("StateT", bound=AgentState)

logger = logging.getLogger("alcyoneus.graph")


class CompiledGraph[StateT: AgentState]:
    """A fully compiled and executable graph ready for workflow execution.

    CompiledGraph represents the final executable form of a StateGraph after compilation.
    It encapsulates all the execution logic, handlers, and services needed to run
    agent workflows. The graph supports both synchronous and asynchronous execution
    with comprehensive state management, checkpointing, event publishing, and
    streaming capabilities.

    This class is generic over state types to support custom AgentState subclasses,
    ensuring type safety throughout the execution process.

    Key Features:
    - Synchronous and asynchronous execution methods
    - Real-time streaming with incremental results
    - State persistence and checkpointing
    - Interrupt and resume capabilities
    - Event publishing for monitoring and debugging
    - Background task management
    - Graceful error handling and recovery

    Attributes:
        _state: The initial/template state for graph executions.
        _invoke_handler: Handler for non-streaming graph execution.
        _stream_handler: Handler for streaming graph execution.
        _checkpointer: Optional state persistence backend.
        _publisher: Optional event publishing backend.
        _store: Optional data storage backend.
        _state_graph: Reference to the source StateGraph.
        _interrupt_before: Nodes where execution should pause before execution.
        _interrupt_after: Nodes where execution should pause after execution.
        _task_manager: Manager for background async tasks.

    Example:
        ```python
        # After building and compiling a StateGraph
        compiled = graph.compile()

        # Synchronous execution
        result = compiled.invoke({"messages": [Message.text_message("Hello")]})

        # Asynchronous execution with streaming
        async for chunk in compiled.astream({"messages": [message]}):
            print(f"Streamed: {chunk.content}")

        # Graceful cleanup
        await compiled.aclose()
        ```

    Note:
        CompiledGraph instances should be properly closed using aclose() to
        release resources like database connections, background tasks, and
        event publishers.
    """

    def __init__(
        self,
        state: StateT,
        checkpointer: BaseCheckpointer[StateT] | None,
        publisher: BasePublisher | None,
        store: BaseStore | None,
        state_graph: StateGraph[StateT],
        interrupt_before: list[str],
        interrupt_after: list[str],
        task_manager: BackgroundTaskManager,
        shutdown_timeout: float = 30.0,
        debug: bool = False,
        durability: str | None = None,
    ):
        logger.info(
            f"Initializing CompiledGraph with nodes: {list(state_graph.nodes.keys())}",
        )

        # Save initial state
        self._state = state
        self._shutdown_timeout = shutdown_timeout
        # Debug mode: emit verbose execution traces + per-step debug metadata.
        self.debug = debug
        # Durability strategy: "sync" | "async" | "exit" | None
        self.durability = durability

        # create handlers
        self._invoke_handler: InvokeHandler[StateT] = InvokeHandler[StateT](
            nodes=state_graph.nodes,
            edges=state_graph.edges,
            interrupt_after=interrupt_after,
            interrupt_before=interrupt_before,
        )
        self._stream_handler: StreamHandler[StateT] = StreamHandler[StateT](
            nodes=state_graph.nodes,
            edges=state_graph.edges,
            interrupt_after=interrupt_after,
            interrupt_before=interrupt_before,
        )

        self._checkpointer: BaseCheckpointer[StateT] | None = checkpointer
        self._publisher: BasePublisher | None = publisher
        self._store: BaseStore | None = store
        self._state_graph: StateGraph[StateT] = state_graph
        self._interrupt_before: list[str] = interrupt_before
        self._interrupt_after: list[str] = interrupt_after
        # generate task manager
        self._task_manager = task_manager
        # Guards aclose() against being run more than once (e.g. an explicit
        # aclose() inside an ``async with`` block followed by __aexit__).
        self._closed = False

    async def __aenter__(self) -> CompiledGraph[StateT]:
        """Enter an async context; returns this graph unchanged.

        Enables ``async with compiled_graph as graph: ...``, which guarantees
        :meth:`aclose` runs on exit even if the body raises.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit the async context, releasing all resources via :meth:`aclose`."""
        await self.aclose()

    def _prepare_config(
        self,
        config: dict[str, Any] | None,
        is_stream: bool = False,
    ) -> dict[str, Any]:
        cfg = dict(config or {})

        if "thread_id" not in cfg:
            cfg["thread_id"] = InjectQ.get_instance().try_get("generated_id") or str(uuid4())

        if "is_stream" not in cfg:
            cfg["is_stream"] = is_stream
        if "user_id" not in cfg:
            cfg["user_id"] = "test-user-id"  # mock user id
        if "run_id" not in cfg:
            cfg["run_id"] = InjectQ.get_instance().try_get("generated_id") or str(uuid4())

        if "timestamp" not in cfg:
            cfg["timestamp"] = datetime.datetime.now().isoformat()

        return cfg

    def invoke(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = ResponseGranularity.LOW,
        debug: bool | None = None,
    ) -> dict[str, Any]:
        """Execute the graph synchronously and return the final results.

        Runs the complete graph workflow from start to finish, handling state
        management, node execution, and result formatting. This method automatically
        detects whether to start a fresh execution or resume from an interrupted state.

        The execution is synchronous but internally uses async operations, making it
        suitable for use in non-async contexts while still benefiting from async
        capabilities for I/O operations.

        Args:
            input_data: Input dictionary for graph execution. For new executions,
                should contain 'messages' key with list of initial messages.
                For resumed executions, can contain additional data to merge.
            config: Optional configuration dictionary containing execution settings:
                - user_id: Identifier for the user/session
                - thread_id: Unique identifier for this execution thread
                - run_id: Unique identifier for this specific run
                - recursion_limit: Maximum steps before stopping (default: 25)
            response_granularity: Level of detail in the response:
                - LOW: Returns only messages (default)
                - PARTIAL: Returns context, summary, and messages
                - FULL: Returns complete state and messages
            debug: Override the compile-time debug flag for this run. When True,
                detailed execution traces are emitted.

        Returns:
            Dictionary containing execution results formatted according to the
            specified granularity level. Always includes execution messages
            and may include additional state information.

        Raises:
            ValueError: If input_data is invalid for new execution.
            GraphRecursionError: If execution exceeds recursion limit.
            Various exceptions: Depending on node execution failures.

        Example:
            ```python
            # Basic execution
            result = compiled.invoke({"messages": [Message.text_message("Process this data")]})
            print(result["messages"])  # Final execution messages

            # With configuration and full details
            result = compiled.invoke(
                input_data={"messages": [message]},
                config={"user_id": "user123", "thread_id": "session456", "recursion_limit": 50},
                response_granularity=ResponseGranularity.FULL,
            )
            print(result["state"])  # Complete final state
            ```

        Note:
            This method uses asyncio.run() internally, so it should not be called
            from within an async context. Use ainvoke() instead for async execution.
        """
        logger.info(
            "Starting synchronous graph execution with %d input keys, granularity=%s",
            len(input_data) if input_data else 0,
            response_granularity,
        )
        logger.debug("Input data keys: %s", list(input_data.keys()) if input_data else [])
        # Async Will Handle Event Publish

        try:
            result = asyncio.run(
                self.ainvoke(input_data, config, response_granularity, debug=debug)
            )
            logger.info("Synchronous graph execution completed successfully")
            return result
        except Exception as e:
            logger.exception("Synchronous graph execution failed: %s", e)
            raise

    async def ainvoke(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = ResponseGranularity.LOW,
        debug: bool | None = None,
    ) -> dict[str, Any]:
        """Execute the graph asynchronously.

        Auto-detects whether to start fresh execution or resume from interrupted state
        based on the AgentState's execution metadata.

        Args:
            input_data: Input dict with 'messages' key (for new execution) or
                       additional data for resuming
            config: Configuration dictionary
            response_granularity: Response parsing granularity
            debug: Optional per-run debug override.

        Returns:
            Response dict based on granularity
        """
        self._guard_not_realtime()
        cfg = self._prepare_config(config, is_stream=False)
        if debug is not None:
            self.debug = debug
            cfg["debug"] = debug

        return await self._invoke_handler.invoke(
            input_data,
            cfg,
            self._state,
            response_granularity,
        )

    def stop(self, config: dict[str, Any]) -> dict[str, Any]:
        """Request the current graph execution to stop (sync helper).

        This sets a stop flag in the checkpointer's thread store keyed by thread_id.
        Handlers periodically check this flag and interrupt execution.
        Returns a small status dict.
        """
        return asyncio.run(self.astop(config))

    async def astop(self, config: dict[str, Any]) -> dict[str, Any]:
        """Request the current graph execution to stop (async).

        Contract:
        - Requires a valid thread_id in config
        - If no active thread or no checkpointer, returns not-running
        - If state exists and is running, set stop_requested flag in thread info
        """
        cfg = self._prepare_config(config, is_stream=bool((config or {}).get("is_stream", False)))
        if not self._checkpointer:
            return {"ok": False, "reason": "no-checkpointer"}

        # Load state to see if this thread is running
        # Lets load from the cache, incase if not available lets load from the db
        # In prebuilt implement like pgsql, there its called internally, no need this call
        # Still lets do that incase user use their own
        state = await self._checkpointer.aget_state_cache(
            cfg
        ) or await self._checkpointer.aget_state(cfg)
        if not state:
            return {"ok": False, "running": False, "reason": "no-state"}

        running = state.is_running() and not state.is_interrupted()
        # Set stop flag regardless; handlers will act if running
        if running:
            state.execution_meta.stop_current_execution = StopRequestStatus.STOP_REQUESTED
            # update cache
            # Cache update is enough; state will be picked up by running execution
            # As its running, cache will be available immediately
            await self._checkpointer.aput_state_cache(cfg, state)
            # Fixme: consider putting to main state as well
            # await self._checkpointer.aput_state(cfg, state)
            logger.info("Set stop_current_execution flag for thread_id: %s", cfg.get("thread_id"))
            return {"ok": True, "running": running}

        logger.info(
            "No running execution to stop for thread_id: %s (running=%s, interrupted=%s)",
            cfg.get("thread_id"),
            running,
            state.is_interrupted(),
        )
        return {"ok": True, "running": running, "reason": "not-running"}

    def get_state_history(self, config: dict[str, Any] | str) -> list[Any]:
        """Get historical state checkpoints for a thread (sync helper)."""
        return asyncio.run(self.aget_state_history(config))

    async def aget_state_history(self, config: dict[str, Any] | str) -> list[Any]:
        """Get historical state checkpoints for a thread (async)."""
        if isinstance(config, str):
            config = {"thread_id": config}
        cfg = self._prepare_config(config, is_stream=False)
        if not self._checkpointer:
            return [self._state] if self._state else []

        if hasattr(self._checkpointer, "aget_state_history"):
            try:
                history = await self._checkpointer.aget_state_history(cfg)
                if history:
                    return history
            except Exception as e:
                logger.warning("Error querying checkpointer state history: %s", e)

        state = await self._checkpointer.aget_state_cache(
            cfg
        ) or await self._checkpointer.aget_state(cfg)
        return [state] if state else ([self._state] if self._state else [])

    def get_state(self, config: dict[str, Any] | str) -> StateT | None:
        """Get the current state for a thread (sync helper).

        Args:
            config: Configuration dictionary with thread_id, or just thread_id string.

        Returns:
            Current state or None if not found.
        """
        return asyncio.run(self.aget_state(config))

    async def aget_state(self, config: dict[str, Any] | str) -> StateT | None:
        """Get the current state for a thread (async).

        Args:
            config: Configuration dictionary with thread_id, or just thread_id string.

        Returns:
            Current state or None if not found.
        """
        if isinstance(config, str):
            config = {"thread_id": config}
        cfg = self._prepare_config(config, is_stream=False)
        if not self._checkpointer:
            return self._state

        state = await self._checkpointer.aget_state_cache(
            cfg
        ) or await self._checkpointer.aget_state(cfg)
        return state

    def update_state(
        self, config: dict[str, Any] | str, values: dict[str, Any], as_node: str | None = None
    ) -> dict[str, Any]:
        """Update the state for a thread (sync helper).

        Args:
            config: Configuration dictionary with thread_id, or just thread_id string.
            values: State values to update.
            as_node: Optional node name to attribute the update to.

        Returns:
            Updated checkpoint config.
        """
        return asyncio.run(self.aupdate_state(config, values, as_node))

    async def aupdate_state(
        self, config: dict[str, Any] | str, values: dict[str, Any], as_node: str | None = None
    ) -> dict[str, Any]:
        """Update the state for a thread (async).

        Creates a new checkpoint with the updated values, enabling time-travel
        and manual state manipulation.

        Args:
            config: Configuration dictionary with thread_id, or just thread_id string.
            values: State values to update.
            as_node: Optional node name to attribute the update to.

        Returns:
            Updated checkpoint config.
        """
        if isinstance(config, str):
            config = {"thread_id": config}
        cfg = self._prepare_config(config, is_stream=False)
        if not self._checkpointer:
            raise RuntimeError("Checkpointer required for update_state")

        # Get current state
        current = await self._checkpointer.aget_state_cache(
            cfg
        ) or await self._checkpointer.aget_state(cfg)
        if current is None:
            current = self._state

        # Merge updates
        if hasattr(current, "model_copy"):
            updated = current.model_copy(update=values)
        else:
            updated = {**current, **values} if isinstance(current, dict) else values

        # Save new checkpoint
        checkpoint_id = str(uuid4())

        await self._checkpointer.aput_state(cfg, updated)
        return {"configurable": {"thread_id": cfg["thread_id"], "checkpoint_id": checkpoint_id}}

    def bulk_update_state(
        self, config: dict[str, Any] | str, updates: list[tuple[dict[str, Any], str | None]]
    ) -> list[dict[str, Any]]:
        """Bulk update state for multiple checkpoints (sync helper).

        Args:
            config: Configuration dictionary with thread_id.
            updates: List of (values, as_node) tuples.

        Returns:
            List of updated checkpoint configs.
        """
        return asyncio.run(self.abulk_update_state(config, updates))

    async def abulk_update_state(
        self, config: dict[str, Any] | str, updates: list[tuple[dict[str, Any], str | None]]
    ) -> list[dict[str, Any]]:
        """Bulk update state for multiple checkpoints (async).

        Args:
            config: Configuration dictionary with thread_id.
            updates: List of (values, as_node) tuples.

        Returns:
            List of updated checkpoint configs.
        """
        results = []
        for values, as_node in updates:
            result = await self.aupdate_state(config, values, as_node)
            results.append(result)
        return results

    def replay(self, config: dict[str, Any] | str, checkpoint_id: str) -> dict[str, Any]:
        """Replay execution from a specific checkpoint (sync helper).

        Args:
            config: Configuration dictionary with thread_id.
            checkpoint_id: Checkpoint ID to replay from.

        Returns:
            Execution result from replay.
        """
        return asyncio.run(self.areplay(config, checkpoint_id))

    async def areplay(self, config: dict[str, Any] | str, checkpoint_id: str) -> dict[str, Any]:
        """Replay execution from a specific checkpoint (async).

        Args:
            config: Configuration dictionary with thread_id.
            checkpoint_id: Checkpoint ID to replay from.

        Returns:
            Execution result from replay.
        """
        if isinstance(config, str):
            config = {"thread_id": config}
        cfg = self._prepare_config(config, is_stream=False)
        cfg["checkpoint_id"] = checkpoint_id

        # Get state at checkpoint
        state = await self._checkpointer.aget_state(cfg)
        if state is None:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        # Resume from that state
        return await self.ainvoke({"messages": state.get("messages", [])}, cfg)

    def fork(
        self, config: dict[str, Any] | str, checkpoint_id: str, new_thread_id: str | None = None
    ) -> dict[str, Any]:
        """Fork execution from a specific checkpoint (sync helper).

        Args:
            config: Configuration dictionary with thread_id.
            checkpoint_id: Checkpoint ID to fork from.
            new_thread_id: Optional new thread ID for the fork.

        Returns:
            New thread configuration.
        """
        return asyncio.run(self.afork(config, checkpoint_id, new_thread_id))

    async def afork(
        self, config: dict[str, Any] | str, checkpoint_id: str, new_thread_id: str | None = None
    ) -> dict[str, Any]:
        """Fork execution from a specific checkpoint (async).

        Creates a new thread with state copied from the specified checkpoint.

        Args:
            config: Configuration dictionary with thread_id.
            checkpoint_id: Checkpoint ID to fork from.
            new_thread_id: Optional new thread ID for the fork.

        Returns:
            New thread configuration.
        """
        if isinstance(config, str):
            config = {"thread_id": config}
        cfg = self._prepare_config(config, is_stream=False)
        cfg["checkpoint_id"] = checkpoint_id

        # Get state at checkpoint
        state = await self._checkpointer.aget_state(cfg)
        if state is None:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        # Create new thread ID
        fork_thread_id = new_thread_id or str(uuid4())
        fork_cfg = self._prepare_config({"thread_id": fork_thread_id}, is_stream=False)

        # Save state to new thread
        await self._checkpointer.aput_state(fork_cfg, state)

        return {"configurable": {"thread_id": fork_thread_id, "checkpoint_id": checkpoint_id}}

    def override_node(
        self,
        name: str,
        func: Callable | ToolNode | BaseAgent,
    ) -> CompiledGraph[StateT]:
        """Override a node in an already-compiled graph.

        Useful for testing pre-built production graphs by swapping
        nodes with test doubles after compilation.

        Args:
            name: Name of the existing node to override.
            func: New function, ToolNode, or Agent to use.

        Returns:
            CompiledGraph: The graph instance for method chaining.

        Raises:
            KeyError: If the node doesn't exist.

        Example:
            ```python
            # Production factory
            def create_production_workflow():
                graph = StateGraph()
                graph.add_node("MAIN", production_agent)
                # ... complex setup
                return graph.compile()


            # Test
            compiled = create_production_workflow()
            compiled.override_node("MAIN", test_agent)  # Override after compile
            result = await compiled.ainvoke(...)
            ```
        """
        if name not in self._state_graph.nodes:
            raise KeyError(f"Node '{name}' does not exist")

        # Create new Node and update the graph's dict
        new_node = Node(name, func)
        self._state_graph.nodes[name] = new_node

        # Re-register in container so handlers pick up the change
        # The handlers read from container's "get_node" factory
        self._state_graph._container.bind_factory(
            "get_node",
            lambda x: self._state_graph.nodes[x],
        )

        logger.debug("Overrode node '%s' in compiled graph", name)
        return self

    def stream(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = ResponseGranularity.LOW,
        stream_mode: str | list[str] | None = None,
        heartbeat_interval: float | None = None,
        debug: bool | None = None,
    ) -> Generator[StreamChunk]:
        """Execute the graph synchronously with streaming support."""

        # For sync streaming, we'll use asyncio.run to handle the async implementation
        async def _async_stream():
            async for chunk in self.astream(
                input_data,
                config,
                response_granularity,
                stream_mode=stream_mode,
                heartbeat_interval=heartbeat_interval,
                debug=debug,
            ):
                yield chunk

        # Convert async generator to sync iteration with a dedicated event loop
        gen = _async_stream()
        loop = asyncio.new_event_loop()
        policy = asyncio.get_event_loop_policy()
        try:
            previous_loop = policy.get_event_loop()
        except Exception:
            previous_loop = None
        asyncio.set_event_loop(loop)
        logger.info("Synchronous streaming started")

        try:
            while True:
                try:
                    chunk = loop.run_until_complete(gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            # Attempt to close the async generator cleanly
            with contextlib.suppress(Exception):
                loop.run_until_complete(gen.aclose())  # type: ignore[attr-defined]
            # Restore previous loop if any, then close created loop
            try:
                if previous_loop is not None:
                    asyncio.set_event_loop(previous_loop)
            finally:
                loop.close()
        logger.info("Synchronous streaming completed")

    def stream_events(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = ResponseGranularity.LOW,
        stream_mode: str | list[str] | None = None,
        heartbeat_interval: float | None = None,
        debug: bool | None = None,
    ) -> Generator[dict[str, Any]]:
        """Execute the graph synchronously with structured event streaming (GraphRunStream v3).

        This is the synchronous wrapper around ``astream_events``.
        """

        async def _async_stream():
            async for chunk in self.astream_events(
                input_data,
                config,
                response_granularity,
                stream_mode=stream_mode,
                heartbeat_interval=heartbeat_interval,
                debug=debug,
            ):
                yield chunk

        gen = _async_stream()
        loop = asyncio.new_event_loop()
        policy = asyncio.get_event_loop_policy()
        try:
            previous_loop = policy.get_event_loop()
        except Exception:
            previous_loop = None
        asyncio.set_event_loop(loop)
        logger.info("Synchronous event streaming started")

        try:
            while True:
                try:
                    chunk = loop.run_until_complete(gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            with contextlib.suppress(Exception):
                loop.run_until_complete(gen.aclose())  # type: ignore[attr-defined]
            try:
                if previous_loop is not None:
                    asyncio.set_event_loop(previous_loop)
            finally:
                loop.close()
        logger.info("Synchronous event streaming completed")

    async def astream(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = ResponseGranularity.LOW,
        stream_mode: str | list[str] | None = None,
        heartbeat_interval: float | None = None,
        debug: bool | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Execute the graph asynchronously with streaming support."""
        self._guard_not_realtime()
        cfg = self._prepare_config(config, is_stream=True)
        if debug is not None:
            self.debug = debug
            cfg["debug"] = debug

        modes = [stream_mode] if isinstance(stream_mode, str) else (stream_mode or [])

        # Setup heartbeat task if requested
        heartbeat_task = None
        heartbeat_queue: asyncio.Queue[StreamChunk] = asyncio.Queue()
        stop_heartbeat = asyncio.Event()

        if heartbeat_interval and heartbeat_interval > 0:

            async def _heartbeat_loop():
                import time

                while not stop_heartbeat.is_set():
                    await asyncio.sleep(heartbeat_interval)
                    if not stop_heartbeat.is_set():
                        chunk = StreamChunk(
                            content="",
                            chunk_id=str(uuid4()),
                            event="heartbeat",
                            data={"timestamp": time.time(), "type": "heartbeat"},
                        )
                        await heartbeat_queue.put(chunk)

            heartbeat_task = asyncio.create_task(_heartbeat_loop())

        try:
            async for chunk in self._stream_handler.stream(
                input_data,
                cfg,
                self._state,
                response_granularity,
            ):
                # Drain any heartbeat chunks
                while not heartbeat_queue.empty():
                    hb = heartbeat_queue.get_nowait()
                    yield hb

                # Apply stream_mode filtering if specified
                if modes:
                    event_type = str(getattr(chunk, "event", "") or "")
                    should_emit = False
                    if (
                        ("messages" in modes and event_type in ("message", "delta", "text", ""))
                        or (
                            "updates" in modes
                            and event_type
                            in ("update", "state_delta", "node_end", "NODE_EXECUTION")
                        )
                        or ("values" in modes and event_type in ("values", "state"))
                        or (
                            "events" in modes
                            and event_type in ("progress", "start", "end", "event")
                        )
                        or (
                            "custom" in modes
                            and event_type not in ("message", "delta", "update", "values")
                        )
                    ):
                        should_emit = True

                    if not should_emit:
                        continue

                yield chunk
        finally:
            stop_heartbeat.set()
            if heartbeat_task:
                heartbeat_task.cancel()
                with contextlib.suppress(Exception):
                    await heartbeat_task

    async def astream_events(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = ResponseGranularity.LOW,
        stream_mode: str | list[str] | None = None,
        heartbeat_interval: float | None = None,
        debug: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream graph execution as structured events (GraphRunStream v3).

                This method yields structured event dictionaries compatible with
                GraphRunStream v3 specification, including:
                - Tool calls and approvals
                - Handoff events
                - Item streaming (messages, tool outputs, state updates)
                - Node execution lifecycle
                - Graph start/end events

                Args:
                    input_data: Input dictionary for graph execution.
                    config: Optional configuration dictionary.
                    response_granularity: Level of detail in response.
                    stream_mode: Filter events by mode ("messages", "updates", "values",
        "events", "custom").
                    heartbeat_interval: Optional heartbeat interval in seconds.
                    debug: Override compile-time debug flag.

                Yields:
                    Structured event dictionaries with type, timestamp, and payload.

                Example:
                    async for event in graph.astream_events({"messages": [...]}):
                        print(event["type"], event["payload"])
        """

        self._guard_not_realtime()
        cfg = self._prepare_config(config, is_stream=True)
        if debug is not None:
            self.debug = debug
            cfg["debug"] = debug

        modes = [stream_mode] if isinstance(stream_mode, str) else (stream_mode or [])

        # Setup heartbeat
        heartbeat_task = None
        heartbeat_queue: asyncio.Queue[dict] = asyncio.Queue()
        stop_heartbeat = asyncio.Event()

        if heartbeat_interval and heartbeat_interval > 0:

            async def _heartbeat_loop():
                import time

                while not stop_heartbeat.is_set():
                    await asyncio.sleep(heartbeat_interval)
                    if not stop_heartbeat.is_set():
                        await heartbeat_queue.put(
                            {
                                "type": "heartbeat",
                                "timestamp": time.time(),
                                "payload": {"type": "heartbeat", "timestamp": time.time()},
                            }
                        )

            heartbeat_task = asyncio.create_task(_heartbeat_loop())

        # Emit graph_start event
        run_id = str(uuid4())
        thread_id = cfg.get("thread_id", "unknown")
        yield {
            "type": "graph_start",
            "timestamp": time.time(),
            "run_id": run_id,
            "thread_id": thread_id,
            "payload": {"input": input_data, "config": cfg},
        }

        try:
            async for chunk in self._stream_handler.stream(
                input_data,
                cfg,
                self._state,
                response_granularity,
            ):
                # Drain heartbeat
                while not heartbeat_queue.empty():
                    yield heartbeat_queue.get_nowait()

                # Apply stream_mode filter
                if modes:
                    event_type = str(getattr(chunk, "event", "") or "")
                    should_emit = False
                    if (
                        ("messages" in modes and event_type in ("message", "delta", "text", ""))
                        or (
                            "updates" in modes
                            and event_type
                            in ("update", "state_delta", "node_end", "NODE_EXECUTION")
                        )
                        or ("values" in modes and event_type in ("values", "state"))
                        or (
                            "events" in modes
                            and event_type in ("progress", "start", "end", "event")
                        )
                        or (
                            "custom" in modes
                            and event_type not in ("message", "delta", "update", "values")
                        )
                    ):
                        should_emit = True
                    if not should_emit:
                        continue

                # Convert StreamChunk to GraphRunStream v3 event dict
                event_dict = self._chunk_to_stream_event(chunk, run_id, thread_id)
                if event_dict:
                    yield event_dict

        finally:
            stop_heartbeat.set()
            if heartbeat_task:
                heartbeat_task.cancel()
                with contextlib.suppress(Exception):
                    await heartbeat_task

            # Emit graph_end event
            yield {
                "type": "graph_end",
                "timestamp": time.time(),
                "run_id": run_id,
                "thread_id": thread_id,
                "payload": {"status": "completed"},
            }

    def _chunk_to_stream_event(
        self,
        chunk: StreamChunk,
        run_id: str,
        thread_id: str,
    ) -> dict[str, Any] | None:
        """Convert internal StreamChunk to GraphRunStream v3 event dict."""
        from alcyoneus.core.state.stream_chunks import StreamChunk, StreamEvent

        if not isinstance(chunk, StreamChunk):
            return None

        base = {
            "run_id": run_id,
            "thread_id": thread_id,
            "timestamp": chunk.timestamp,
        }

        # Map internal stream events to GraphRunStream v3 types
        event_map = {
            StreamEvent.MESSAGE: "message",
            StreamEvent.UPDATES: "node_update",
            StreamEvent.STATE: "state",
            StreamEvent.ERROR: "error",
        }

        event_type = event_map.get(chunk.event, "unknown")

        if chunk.event == StreamEvent.MESSAGE and chunk.message:
            payload = {
                "message": chunk.message.model_dump()
                if hasattr(chunk.message, "model_dump")
                else str(chunk.message),
                "delta": getattr(chunk, "delta", False),
            }
            # Tool call detection
            if hasattr(chunk.message, "content") and isinstance(chunk.message.content, list):
                for block in chunk.message.content:
                    if hasattr(block, "type") and block.type == "tool_call":
                        event_type = "tool_call"
                        payload["tool_call"] = (
                            block.model_dump() if hasattr(block, "model_dump") else str(block)
                        )
                        break
                    if hasattr(block, "type") and block.type == "tool_result":
                        event_type = "tool_result"
                        payload["tool_result"] = (
                            block.model_dump() if hasattr(block, "model_dump") else str(block)
                        )
                        break

        elif chunk.event == StreamEvent.UPDATES:
            # Node execution lifecycle
            if chunk.metadata:
                if chunk.metadata.get("status") == "Function execution started":
                    event_type = "node_start"
                elif chunk.metadata.get("status") == "Function execution completed":
                    event_type = "node_end"
                elif chunk.metadata.get("interrupted"):
                    event_type = "interrupt"
            payload = {
                "node": chunk.metadata.get("node") if chunk.metadata else None,
                "status": chunk.metadata.get("status") if chunk.metadata else None,
                "data": chunk.data,
            }

        elif chunk.event == StreamEvent.STATE:
            event_type = "state_update"
            payload = {
                "state": chunk.state.model_dump()
                if chunk.state and hasattr(chunk.state, "model_dump")
                else chunk.state
            }

        elif chunk.event == StreamEvent.ERROR:
            event_type = "error"
            payload = {"error": chunk.data}

        else:
            payload = chunk.data or {}

        # Add handoff detection (check for handoff tool calls)
        if "tool_call" in payload and isinstance(payload["tool_call"], dict):
            tool_name = payload["tool_call"].get("name", "")
            if "handoff" in tool_name.lower() or "transfer" in tool_name.lower():
                event_type = "handoff"
                payload["handoff_type"] = "agent_transfer"

        # Add tool approval detection (interrupt events with approval)
        if event_type == "interrupt":
            interrupt_data = payload.get("data", {})
            if (
                isinstance(interrupt_data, dict)
                and interrupt_data.get("type") == "approval_request"
            ):
                event_type = "tool_approval"
                payload["approval_request"] = interrupt_data

        return {
            "type": event_type,
            **base,
            "payload": payload,
        }

    def attach_remote_tools(
        self,
        tools: list[dict],
        node_name: str,
    ):
        """Attach remote tools to a ToolNode in the graph.

        Args:
            tools: List of tool configurations to attach.
            node_name: Name of the ToolNode to attach tools to.

        Raises:
            GraphError: If the specified node is not a ToolNode.

        Example:
            >>> tool_configs = [
            ...     {"name": "search", "type": "SearchTool", "config": {...}},
            ...     {"name": "calculator", "type": "CalculatorTool", "config": {...}},
            ... ]
            >>> graph.attach_remote_tools(tool_configs, "tool_node")
        """
        logger.debug(
            "Attaching remote tools to node '%s': %s",
            node_name,
            tools,
        )
        node: Node | None = self._state_graph.nodes.get(node_name)
        if not node:
            raise GraphError(
                message=f"Node '{node_name}' not found in graph",
                error_code="GRAPH_004",
                context={"node_name": node_name},
            )

        if not isinstance(node.func, ToolNode):
            error_msg = f"Node '{node_name}' is not a ToolNode"
            logger.error(error_msg)
            raise GraphError(
                message=error_msg,
                error_code="GRAPH_005",
                context={"node_name": node_name},
            )

        tool_node: ToolNode = node.func
        tool_node.set_remote_tool(tools)
        logger.info(
            "Attached %d remote tools to ToolNode '%s'",
            len(tools),
            node_name,
        )

    # ------------------------------------------------------------------ #
    # Realtime runtime (audio-to-audio). A separate runtime from the
    # super-step invoke/stream loop: the live agent owns the turn loop.
    # ------------------------------------------------------------------ #
    def _find_live_nodes(self) -> list[tuple[str, Node]]:
        from alcyoneus.core.realtime.live_agent import LiveAgent

        return [
            (name, node)
            for name, node in self._state_graph.nodes.items()
            if isinstance(node.func, LiveAgent)
        ]

    def _guard_not_realtime(self) -> None:
        """Forcing rule: a graph containing a LiveAgent must use arealtime()."""
        if self._find_live_nodes():
            raise RuntimeError(
                "This graph contains a LiveAgent; use .arealtime() / .realtime() instead of "
                "invoke/ainvoke/stream/astream."
            )

    async def arealtime(
        self,
        input_queue: Any,
        config: dict[str, Any] | None = None,
        state: AgentState | None = None,
    ) -> AsyncIterator[Any]:
        """Run the graph's realtime (audio) session, yielding normalized RealtimeEvents.

        Forcing rule: the graph must contain exactly one LiveAgent (the root controller);
        ordinary turn-based graphs must use invoke/stream.
        """
        live = self._find_live_nodes()
        if not live:
            raise RuntimeError(
                "arealtime() requires a graph rooted at a LiveAgent (e.g. AudioAgent); "
                "this graph has none. Use invoke/stream for turn-based graphs."
            )
        if len(live) > 1:
            raise RuntimeError(
                "Only one LiveAgent is allowed per realtime run in v1 "
                f"(found {len(live)}: {[name for name, _ in live]})."
            )

        name, node = live[0]
        agent = node.func
        agent._node_name = name
        cfg = self._prepare_config(config, is_stream=True)
        callback_manager = InjectQ.get_instance().try_get(CallbackManager)
        context_manager = self._state_graph._context_manager
        run_state = state if state is not None else (self._state or AgentState())

        async for event in agent.arun(
            input_queue,
            cfg,
            run_state,
            checkpointer=self._checkpointer,
            callback_manager=callback_manager,
            context_manager=context_manager,
        ):
            yield event

    def realtime(
        self,
        input_queue: Any,
        config: dict[str, Any] | None = None,
        state: AgentState | None = None,
    ) -> Generator[Any]:
        """Synchronous wrapper over :meth:`arealtime` for non-async consumers.

        Must be called from a thread with no running event loop; from inside an async
        context (FastAPI handler, Jupyter), use :meth:`arealtime` directly.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass  # no running loop: safe to drive a private one below
        else:
            raise RuntimeError(
                "realtime() (sync) cannot be called from a running event loop; "
                "await arealtime() instead."
            )

        agen = self.arealtime(input_queue, config, state)
        loop = asyncio.new_event_loop()
        try:
            while True:
                try:
                    yield loop.run_until_complete(agen.__anext__())
                except StopAsyncIteration:
                    break
        finally:
            with contextlib.suppress(Exception):
                loop.run_until_complete(agen.aclose())
            loop.close()

    async def aclose(self) -> dict[str, Any]:  # noqa: PLR0915
        """
        Close the graph and release all resources gracefully.

        This method ensures proper cleanup of all components with timeout handling.
        It follows a structured shutdown sequence:
        1. Background task manager (running tasks)
        2. Checkpointer (state persistence)
        3. Publisher (event publishing)
        4. Store (data storage)

        Returns:
            Dictionary with detailed shutdown statistics for each component.

        Calling this more than once is a no-op; the second call returns
        ``{"status": "already_closed"}``. Prefer the async-context-manager form,
        which calls this automatically on exit:

        Example:
            ```python
            async def main():
                async with await build_and_compile_graph() as graph:
                    await graph.ainvoke(input_data)
                # graph.aclose() has run here, even if ainvoke raised


            # Or manage the lifecycle manually:
            async def main_manual():
                graph = await build_and_compile_graph()
                try:
                    await graph.ainvoke(input_data)
                finally:
                    stats = await graph.aclose()
                    print(f"Shutdown completed: {stats}")
            ```
        """
        from alcyoneus.utils.shutdown import shutdown_with_timeout

        if self._closed:
            logger.debug("CompiledGraph.aclose() called again; already closed")
            return {"status": "already_closed"}
        self._closed = True

        logger.info("Initiating graceful shutdown of CompiledGraph")
        stats: dict[str, Any] = {}
        start_time = asyncio.get_event_loop().time()

        # 1. Shutdown background task manager (handles all pending async writes)
        try:
            logger.debug("Shutting down background task manager...")
            shutdown_stats = await self._task_manager.shutdown(timeout=self._shutdown_timeout)
            logger.info("Background task manager shutdown completed")
            stats["background_tasks"] = shutdown_stats
        except Exception as e:
            stats["background_tasks"] = {"status": "error", "error": str(e)}
            logger.exception("Error shutting down background tasks: %s", e)

        # 2. Close checkpointer (may have pending writes)
        if self._checkpointer:
            try:
                logger.debug("Releasing checkpointer...")
                result = await shutdown_with_timeout(
                    self._checkpointer.arelease(),
                    timeout=self._shutdown_timeout / 3,  # Give 1/3 of total timeout
                    task_name="checkpointer",
                )
                logger.info("Checkpointer closed successfully")
                stats["checkpointer"] = result
            except Exception as e:
                stats["checkpointer"] = {"status": "error", "error": str(e)}
                logger.exception("Error closing checkpointer: %s", e)
        else:
            stats["checkpointer"] = {"status": "skipped", "reason": "no checkpointer"}

        # 3. Close publisher (event delivery)
        if self._publisher:
            try:
                logger.debug("Closing publisher...")
                result = await shutdown_with_timeout(
                    self._publisher.close(),
                    timeout=self._shutdown_timeout / 3,
                    task_name="publisher",
                )
                logger.info("Publisher closed successfully")
                stats["publisher"] = result
            except Exception as e:
                stats["publisher"] = {"status": "error", "error": str(e)}
                logger.exception("Error closing publisher: %s", e)
        else:
            stats["publisher"] = {"status": "skipped", "reason": "no publisher"}

        # 4. Close store (data persistence)
        if self._store:
            try:
                logger.debug("Releasing store...")
                result = await shutdown_with_timeout(
                    self._store.arelease(),
                    timeout=self._shutdown_timeout / 3,
                    task_name="store",
                )
                logger.info("Store closed successfully")
                stats["store"] = result
            except Exception as e:
                stats["store"] = {"status": "error", "error": str(e)}
                logger.exception("Error closing store: %s", e)
        else:
            stats["store"] = {"status": "skipped", "reason": "no store"}

        total_duration = asyncio.get_event_loop().time() - start_time
        stats["total_duration"] = total_duration
        logger.info(f"CompiledGraph shutdown completed in {total_duration:.2f}s. Stats: {stats}")
        return stats

    def generate_graph(self, format: str = "dict") -> dict[str, Any] | str | bytes:  # noqa: A002
        """Generate the graph representation.

        Args:
            format: Output format - "dict" (default), "mermaid", "ascii", or "png".

        Returns:
            Graph structure as dict, mermaid diagram string, ASCII art, or PNG bytes.
        """
        # Build internal representation
        graph = {
            "info": {},
            "nodes": [],
            "edges": [],
        }
        # Populate the graph with nodes and edges
        for node_name in self._state_graph.nodes:
            graph["nodes"].append(
                {
                    "id": str(uuid4()),
                    "name": node_name,
                }
            )

        for edge in self._state_graph.edges:
            edge_dict = {
                "id": str(uuid4()),
                "source": edge.from_node,
                "target": edge.to_node,
            }
            if edge.condition:
                edge_dict["condition"] = "conditional"
            if edge.condition_result:
                edge_dict["condition_result"] = str(edge.condition_result)
            graph["edges"].append(edge_dict)

        # Add info
        graph["info"] = {
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "checkpointer": self._checkpointer is not None,
            "checkpointer_type": type(self._checkpointer).__name__ if self._checkpointer else None,
            "publisher": self._publisher is not None,
            "store": self._store is not None,
            "interrupt_before": self._interrupt_before,
            "interrupt_after": self._interrupt_after,
            "context_type": self._state_graph._context_manager.__class__.__name__,
            "id_generator": self._state_graph._id_generator.__class__.__name__,
            "id_type": self._state_graph._id_generator.id_type.value,
            "state_type": self._state.__class__.__name__,
            "state_fields": list(self._state.model_dump().keys()),
        }

        if format == "dict":
            return graph
        if format == "mermaid":
            return self._generate_mermaid(graph)
        if format == "ascii":
            return self._generate_ascii(graph)
        if format == "png":
            return self._generate_png(graph)
        raise ValueError(f"Unsupported format: {format}. Use 'dict', 'mermaid', 'ascii', or 'png'")

    def _generate_mermaid(self, graph: dict[str, Any]) -> str:
        """Generate Mermaid diagram from graph structure."""
        lines = ["graph TD"]
        # Map node names to short IDs
        node_ids = {}
        for i, node in enumerate(graph["nodes"]):
            node_ids[node["name"]] = f"N{i}"
            lines.append(f'    {node_ids[node["name"]]}["{node["name"]}"]')

        # Add edges
        for edge in graph["edges"]:
            source_id = node_ids.get(edge["source"])
            target_id = node_ids.get(edge["target"])
            if source_id and target_id:
                if edge.get("condition"):
                    lines.append(f"    {source_id} -->|conditional| {target_id}")
                else:
                    lines.append(f"    {source_id} --> {target_id}")

        # Add START and END
        lines.insert(1, '    START(("START"))')
        lines.insert(2, '    END(("END"))')

        # Connect START to entry point
        if self._state_graph.entry_point and self._state_graph.entry_point in node_ids:
            lines.append(f"    START --> {node_ids[self._state_graph.entry_point]}")

        # Connect END from nodes with no outgoing edges
        has_outgoing = {e["source"] for e in graph["edges"]}
        for node in graph["nodes"]:
            if node["name"] not in has_outgoing:
                if node["name"] in node_ids:
                    lines.append(f"    {node_ids[node['name']]} --> END")

        return "\n".join(lines)

    def _generate_ascii(self, graph: dict[str, Any]) -> str:
        """Generate ASCII art from graph structure."""
        lines = ["Graph Structure:"]
        lines.append("=" * 50)
        lines.append(f"Nodes ({graph['info']['node_count']}):")
        for node in graph["nodes"]:
            lines.append(f"  - {node['name']}")
        lines.append(f"Edges ({graph['info']['edge_count']}):")
        for edge in graph["edges"]:
            cond = " [conditional]" if edge.get("condition") else ""
            lines.append(f"  - {edge['source']} --> {edge['target']}{cond}")
        lines.append("=" * 50)
        lines.append(f"Entry Point: {self._state_graph.entry_point or 'Not set'}")
        lines.append(f"Checkpointer: {graph['info']['checkpointer_type'] or 'None'}")
        return "\n".join(lines)

    def _generate_png(self, graph: dict[str, Any]) -> bytes:
        """Generate PNG from graph structure (requires mermaid-cli)."""
        import os
        import subprocess
        import tempfile

        mermaid_code = self._generate_mermaid(graph)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
            f.write(mermaid_code)
            mmd_file = f.name
        png_file = mmd_file.replace(".mmd", ".png")
        try:
            subprocess.run(  # noqa: S603
                ["mmdc", "-i", mmd_file, "-o", png_file],
                check=True,
                capture_output=True,  # noqa: S607
            )
            with open(png_file, "rb") as f:
                png_data = f.read()
            return png_data
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                "PNG generation requires 'mmdc' (mermaid-cli). Install with: npm install -g @mermaid-js/mermaid-cli"  # noqa: E501
            )
        finally:
            if os.path.exists(mmd_file):
                os.unlink(mmd_file)
            if os.path.exists(png_file):
                os.unlink(png_file)
