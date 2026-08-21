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
"""Stream transformers for alcyoneus OS.

Provides stream transformers for processing graph execution events,
including ToolCallTransformer for streaming tool call events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from alcyoneus.core.state.message_block import ToolCallBlock, ToolResultBlock
from alcyoneus.core.state.stream_chunks import StreamChunk, StreamEvent


class StreamTransformer(ABC):
    """Abstract base class for stream transformers.

    Stream transformers process raw stream chunks and emit transformed
    events. They can be chained together to build complex streaming pipelines.
    """

    # Class attributes for transformer configuration
    requires_async: bool = True
    supports_sync: bool = False
    required_stream_modes: list[str] = []
    before_builtins: bool = False

    @abstractmethod
    async def init(self, config: dict[str, Any]) -> None:
        """Initialize the transformer with configuration.

        Args:
            config: Configuration dictionary.
        """

    @abstractmethod
    async def process(self, chunk: StreamChunk) -> list[StreamChunk]:
        """Process a stream chunk.

        Args:
            chunk: Input stream chunk.

        Returns:
            List of output stream chunks (may be empty).
        """

    @abstractmethod
    async def finalize(self) -> list[StreamChunk]:
        """Finalize the transformer and emit any remaining chunks.

        Returns:
            List of final output chunks.
        """

    async def fail(self, error: Exception) -> list[StreamChunk]:
        """Handle an error during streaming.

        Args:
            error: The error that occurred.

        Returns:
            List of error chunks to emit.
        """
        return []

    def schedule(self) -> bool:
        """Whether this transformer should be scheduled for processing.

        Returns:
            True if the transformer should be scheduled.
        """
        return True


class ToolCallTransformer(StreamTransformer):
    """Transforms tool execution events into structured tool call/result chunks.

    This transformer intercepts TOOL_EXECUTION events and emits separate
    TOOL_CALL and TOOL_RESULT chunks for each tool, enabling real-time
    streaming of tool execution progress.
    """

    def __init__(self):
        super().__init__()
        self._tool_calls: dict[str, dict[str, Any]] = {}
        self._pending_results: dict[str, list[Any]] = {}

    async def init(self, config: dict[str, Any]) -> None:
        """Initialize the transformer."""
        self._tool_calls.clear()
        self._pending_results.clear()

    async def process(self, chunk: StreamChunk) -> list[StreamChunk]:
        """Process a stream chunk and emit tool call/result events."""
        output = []

        if chunk.event == StreamEvent.TOOL_EXECUTION:
            # Parse tool execution data
            data = chunk.data
            tool_name = data.get("tool_name")
            tool_call_id = data.get("tool_call_id")
            status = data.get("status")  # "start", "progress", "complete", "error"

            if status == "start":
                # Emit tool call start
                tool_call = ToolCallBlock(
                    tool_name=tool_name,
                    arguments=data.get("arguments", {}),
                    tool_call_id=tool_call_id or str(id(data)),
                )
                output_chunk = StreamChunk(
                    event=StreamEvent.TOOL_CALL,
                    data=tool_call.model_dump(),
                    content=f"Calling tool: {tool_name}",
                )
                output.append(output_chunk)

            elif status == "progress":
                # Emit progress update
                progress_chunk = StreamChunk(
                    event=StreamEvent.TOOL_PROGRESS,
                    data={"tool_name": tool_name, "progress": data.get("progress", 0)},
                    content=f"Tool {tool_name} progress: {data.get('progress', 0)}%",
                )
                output.append(progress_chunk)

            elif status in ("complete", "error"):
                # Emit tool result
                tool_result = ToolResultBlock(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id or str(id(data)),
                    result=data.get("result") if status == "complete" else None,
                    error=data.get("error") if status == "error" else None,
                )
                result_chunk = StreamChunk(
                    event=StreamEvent.TOOL_RESULT,
                    data=tool_result.model_dump(),
                    content=f"Tool {tool_name} {'completed' if status == 'complete' else 'failed'}",
                )
                output.append(result_chunk)

        else:
            # Pass through non-tool events
            output.append(chunk)

        return output

    async def finalize(self) -> list[StreamChunk]:
        """Finalize - emit any pending tool results."""
        return []


class MessagesTransformer(StreamTransformer):
    """Extracts message chunks from the stream."""

    async def init(self, config: dict[str, Any]) -> None:
        pass

    async def process(self, chunk: StreamChunk) -> list[StreamChunk]:
        """Extract message-related chunks."""
        if chunk.event in (StreamEvent.MESSAGE, StreamEvent.MESSAGE_DELTA):
            return [chunk]
        return []

    async def finalize(self) -> list[StreamChunk]:
        return []


class ValuesTransformer(StreamTransformer):
    """Emits full state values at each step."""

    def __init__(self):
        super().__init__()
        self._latest_state = None

    async def init(self, config: dict[str, Any]) -> None:
        self._latest_state = None

    async def process(self, chunk: StreamChunk) -> list[StreamChunk]:
        if chunk.event == StreamEvent.STATE_UPDATE and chunk.data:
            self._latest_state = chunk.data
            return [
                StreamChunk(
                    event=StreamEvent.VALUES,
                    data=self._latest_state,
                    content="State values updated",
                )
            ]
        return []

    async def finalize(self) -> list[StreamChunk]:
        if self._latest_state:
            return [
                StreamChunk(
                    event=StreamEvent.VALUES,
                    data=self._latest_state,
                    content="Final state values",
                )
            ]
        return []


class UpdatesTransformer(StreamTransformer):
    """Emits state updates (deltas) at each step."""

    async def init(self, config: dict[str, Any]) -> None:
        pass

    async def process(self, chunk: StreamChunk) -> list[StreamChunk]:
        if chunk.event == StreamEvent.STATE_DELTA:
            return [chunk]
        return []

    async def finalize(self) -> list[StreamChunk]:
        return []


# Built-in transformers registry
BUILTIN_TRANSFORMERS = {
    "tool_calls": ToolCallTransformer,
    "messages": MessagesTransformer,
    "values": ValuesTransformer,
    "updates": UpdatesTransformer,
}


def get_builtin_transformer(name: str) -> type[StreamTransformer]:
    """Get a built-in transformer class by name.

    Args:
        name: Transformer name ("tool_calls", "messages", "values", "updates").

    Returns:
        Transformer class.

    Raises:
        ValueError: If transformer name not found.
    """
    if name not in BUILTIN_TRANSFORMERS:
        raise ValueError(
            f"Unknown built-in transformer: {name}. Available: {list(BUILTIN_TRANSFORMERS.keys())}"
        )
    return BUILTIN_TRANSFORMERS[name]


__all__ = [
    "BUILTIN_TRANSFORMERS",
    "MessagesTransformer",
    "StreamTransformer",
    "ToolCallTransformer",
    "UpdatesTransformer",
    "ValuesTransformer",
    "get_builtin_transformer",
]
