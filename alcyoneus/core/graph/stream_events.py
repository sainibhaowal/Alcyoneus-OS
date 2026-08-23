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
"""
GraphRunStream v3: Structured Event Streaming for Graph Execution.

This module provides a comprehensive event streaming system for graph execution
compatible with the GraphRunStream v3 specification. It provides structured
events for:

- Graph lifecycle (start, end, heartbeat)
- Node execution lifecycle (start, end, error)
- Message streaming (user, assistant, tool messages)
- Tool calls and results
- Tool approval requests and responses
- Agent handoffs
- State updates
- Interrupts and errors
- Item streaming for real-time data

Event Structure (GraphRunStream v3):
    {
        "type": "graph_start|message|tool_call|tool_result|tool_approval|"
        "handoff|node_start|node_end|state_update|interrupt|error|graph_end|heartbeat",
        "timestamp": float,  # Unix timestamp
        "run_id": str,       # Unique run identifier
        "thread_id": str,    # Thread identifier
        "payload": {...}     # Event-specific payload
    }
"""

from __future__ import annotations

import asyncio
import enum
import json
import time
import uuid
from collections.abc import AsyncIterator, Generator
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, TypeVar

from alcyoneus.core.state import Message
from alcyoneus.core.state.stream_chunks import StreamChunk, StreamEvent


T = TypeVar("T")


class StreamEventType(enum.StrEnum):
    """GraphRunStream v3 event types."""

    # Graph lifecycle
    GRAPH_START = "graph_start"
    GRAPH_END = "graph_end"
    HEARTBEAT = "heartbeat"

    # Node execution
    NODE_START = "node_start"
    NODE_END = "node_end"

    # Messages
    MESSAGE = "message"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_END = "message_end"

    # Tool calls
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_APPROVAL_REQUEST = "tool_approval_request"
    TOOL_APPROVAL_RESPONSE = "tool_approval_response"

    # Handoffs
    HANDOFF = "handoff"

    # State
    STATE_UPDATE = "state_update"
    STATE_DELTA = "state_delta"

    # Interrupts
    INTERRUPT = "interrupt"
    INTERRUPT_RESUME = "interrupt_resume"

    # Errors
    ERROR = "error"

    # Items streaming
    ITEM_STREAM = "item_stream"
    ITEM_STREAM_DELTA = "item_stream_delta"
    ITEM_STREAM_END = "item_stream_end"


@dataclass
class GraphRunEvent:
    """Structured event for GraphRunStream v3."""

    type: StreamEventType
    timestamp: float = field(default_factory=time.time)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    thread_id: str = "unknown"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphRunStream v3 dict format."""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "thread_id": self.thread_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    def to_sse(self) -> str:
        """Convert to Server-Sent Events format."""
        return f"data: {json.dumps(self.to_dict())}\n\n"

    @classmethod
    def create_graph_start(
        cls, run_id: str, thread_id: str, input_data: dict[str, Any], config: dict[str, Any]
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.GRAPH_START,
            run_id=run_id,
            thread_id=thread_id,
            payload={"input": input_data, "config": config},
        )

    @classmethod
    def create_graph_end(
        cls, run_id: str, thread_id: str, status: str = "completed", error: str | None = None
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.GRAPH_END,
            run_id=run_id,
            thread_id=thread_id,
            payload={"status": status, "error": error},
        )

    @classmethod
    def create_node_start(
        cls, run_id: str, thread_id: str, node_name: str, input_data: dict[str, Any]
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.NODE_START,
            run_id=run_id,
            thread_id=thread_id,
            payload={"node": node_name, "input": input_data},
        )

    @classmethod
    def create_node_end(
        cls, run_id: str, thread_id: str, node_name: str, output: dict[str, Any], duration_ms: float
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.NODE_END,
            run_id=run_id,
            thread_id=thread_id,
            payload={"node": node_name, "output": output, "duration_ms": duration_ms},
        )

    @classmethod
    def create_message(
        cls, run_id: str, thread_id: str, message: Message, delta: bool = False
    ) -> GraphRunEvent:
        event_type = StreamEventType.MESSAGE_DELTA if delta else StreamEventType.MESSAGE
        return cls(
            type=event_type,
            run_id=run_id,
            thread_id=thread_id,
            payload={"message": message.model_dump()},
        )

    @classmethod
    def create_tool_call(
        cls, run_id: str, thread_id: str, tool_name: str, args: dict[str, Any], call_id: str
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.TOOL_CALL,
            run_id=run_id,
            thread_id=thread_id,
            payload={"tool": tool_name, "arguments": args, "call_id": call_id},
        )

    @classmethod
    def create_tool_result(
        cls, run_id: str, thread_id: str, call_id: str, result: Any, is_error: bool = False
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.TOOL_RESULT,
            run_id=run_id,
            thread_id=thread_id,
            payload={"call_id": call_id, "result": result, "is_error": is_error},
        )

    @classmethod
    def create_tool_approval_request(
        cls,
        run_id: str,
        thread_id: str,
        tool_name: str,
        args: dict[str, Any],
        call_id: str,
        reason: str = "",
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.TOOL_APPROVAL_REQUEST,
            run_id=run_id,
            thread_id=thread_id,
            payload={"tool": tool_name, "arguments": args, "call_id": call_id, "reason": reason},
        )

    @classmethod
    def create_tool_approval_response(
        cls,
        run_id: str,
        thread_id: str,
        call_id: str,
        approved: bool,
        response_data: dict | None = None,
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.TOOL_APPROVAL_RESPONSE,
            run_id=run_id,
            thread_id=thread_id,
            payload={"call_id": call_id, "approved": approved, "data": response_data},
        )

    @classmethod
    def create_handoff(
        cls, run_id: str, thread_id: str, from_agent: str, to_agent: str, reason: str = ""
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.HANDOFF,
            run_id=run_id,
            thread_id=thread_id,
            payload={"from": from_agent, "to": to_agent, "reason": reason},
        )

    @classmethod
    def create_state_update(
        cls, run_id: str, thread_id: str, state_delta: dict[str, Any], node: str | None = None
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.STATE_UPDATE,
            run_id=run_id,
            thread_id=thread_id,
            payload={"delta": state_delta, "node": node},
        )

    @classmethod
    def create_interrupt(
        cls, run_id: str, thread_id: str, interrupt_type: str, data: dict[str, Any]
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.INTERRUPT,
            run_id=run_id,
            thread_id=thread_id,
            payload={"type": interrupt_type, "data": data},
        )

    @classmethod
    def create_interrupt_resume(
        cls, run_id: str, thread_id: str, resume_value: Any
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.INTERRUPT_RESUME,
            run_id=run_id,
            thread_id=thread_id,
            payload={"value": resume_value},
        )

    @classmethod
    def create_error(
        cls,
        run_id: str,
        thread_id: str,
        error: str,
        node: str | None = None,
        recoverable: bool = False,
    ) -> GraphRunEvent:
        return cls(
            type=StreamEventType.ERROR,
            run_id=run_id,
            thread_id=thread_id,
            payload={"error": error, "node": node, "recoverable": recoverable},
        )

    @classmethod
    def create_heartbeat(cls, run_id: str, thread_id: str) -> GraphRunEvent:
        return cls(
            type=StreamEventType.HEARTBEAT,
            run_id=run_id,
            thread_id=thread_id,
            payload={"timestamp": time.time()},
        )

    @classmethod
    def create_item_stream(
        cls, run_id: str, thread_id: str, item: Any, delta: bool = False, final: bool = False
    ) -> GraphRunEvent:
        if final:
            event_type = StreamEventType.ITEM_STREAM_END
        elif delta:
            event_type = StreamEventType.ITEM_STREAM_DELTA
        else:
            event_type = StreamEventType.ITEM_STREAM
        return cls(
            type=event_type,
            run_id=run_id,
            thread_id=thread_id,
            payload={"item": item, "delta": delta, "final": final},
        )


class GraphRunStream:
    """GraphRunStream v3 event generator.

    Provides structured event streaming for graph execution with full
    GraphRunStream v3 compatibility.
    """

    def __init__(
        self,
        graph: Any,
        run_id: str | None = None,
        thread_id: str | None = None,
        heartbeat_interval: float = 30.0,
    ):
        self.graph = graph
        self.run_id = run_id or str(uuid.uuid4())
        self.thread_id = thread_id or str(uuid.uuid4())
        self.heartbeat_interval = heartbeat_interval
        self._heartbeat_task: asyncio.Task | None = None
        self._stop_heartbeat = asyncio.Event()

    async def astream_events(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: Any = "low",
        stream_mode: str | list[str] | None = None,
        debug: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream graph execution as structured GraphRunStream v3 events."""

        # Emit graph start
        yield GraphRunEvent.create_graph_start(
            self.run_id, self.thread_id, input_data, config or {}
        ).to_dict()

        # Start heartbeat
        self._stop_heartbeat.clear()
        heartbeat_queue: asyncio.Queue = asyncio.Queue()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(heartbeat_queue))

        try:
            async for chunk in self.graph.astream(
                input_data,
                config,
                response_granularity=response_granularity,
                stream_mode=stream_mode,
                debug=debug,
            ):
                # Drain heartbeat
                while not heartbeat_queue.empty():
                    yield heartbeat_queue.get_nowait().to_dict()

                # Convert StreamChunk to GraphRunEvent
                event = self._convert_chunk(chunk)
                if event:
                    yield event.to_dict()

        finally:
            self._stop_heartbeat.set()
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                with suppress(Exception):
                    await self._heartbeat_task

            # Emit graph end
            yield GraphRunEvent.create_graph_end(self.run_id, self.thread_id).to_dict()

    async def _heartbeat_loop(self, queue: asyncio.Queue) -> None:
        """Emit heartbeat events periodically."""
        while not self._stop_heartbeat.is_set():
            await asyncio.sleep(self.heartbeat_interval)
            if not self._stop_heartbeat.is_set():
                await queue.put(GraphRunEvent.create_heartbeat(self.run_id, self.thread_id))

    def _convert_chunk(self, chunk: StreamChunk) -> GraphRunEvent | None:
        """Convert internal StreamChunk to GraphRunEvent."""
        if chunk.event == StreamEvent.MESSAGE and chunk.message:
            return GraphRunEvent.create_message(self.run_id, self.thread_id, chunk.message)

        if chunk.event == StreamEvent.STATE and chunk.state:
            return GraphRunEvent.create_state_update(
                self.run_id, self.thread_id, chunk.state.model_dump()
            )

        if chunk.event == StreamEvent.UPDATES:
            # Node execution updates
            if chunk.metadata:
                if chunk.metadata.get("status") == "Function execution started":
                    return GraphRunEvent.create_node_start(
                        self.run_id,
                        self.thread_id,
                        chunk.metadata.get("node", "unknown"),
                        chunk.data or {},
                    )
                if chunk.metadata.get("status") == "Function execution completed":
                    return GraphRunEvent.create_node_end(
                        self.run_id,
                        self.thread_id,
                        chunk.metadata.get("node", "unknown"),
                        chunk.data or {},
                        chunk.metadata.get("duration_ms", 0),
                    )

        return None


def stream_events_sync(
    graph: Any,
    input_data: dict[str, Any],
    config: dict[str, Any] | None = None,
    response_granularity: Any = "low",
    stream_mode: str | list[str] | None = None,
    heartbeat_interval: float = 30.0,
    debug: bool | None = None,
) -> Generator[dict[str, Any]]:
    """Synchronous wrapper around astream_events."""
    run_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    stream = GraphRunStream(graph, run_id=run_id, thread_id=thread_id)

    async def _async_stream():
        async for event in stream.astream_events(input_data, config, response_granularity):
            yield event

    gen = _async_stream()
    loop = asyncio.new_event_loop()
    try:
        while True:
            try:
                yield loop.run_until_complete(gen.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


def _create_graph_run_stream(
    graph: Any,
    run_id: str | None = None,
    thread_id: str | None = None,
) -> GraphRunStream:
    """Factory function to create a GraphRunStream instance."""
    return GraphRunStream(graph, run_id=run_id, thread_id=thread_id)


__all__ = [
    "GraphRunEvent",
    "GraphRunStream",
    "StreamEventType",
    "_create_graph_run_stream",
    "stream_events_sync",
]
