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
Realtime Events for Tool Approvals, Handoffs, and Item Streaming.

This module provides structured realtime event types for:
- Tool approval requests and responses
- Agent handoffs
- Item streaming (real-time data chunks)
- Interrupt handling and resumption

These events are designed for realtime audio/duplex sessions where
low-latency event streaming is critical.
"""

from __future__ import annotations

import asyncio
import enum
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TypeVar


T = TypeVar("T")


class RealtimeEventType(enum.StrEnum):
    """Realtime event types for live sessions."""

    # Tool approvals
    TOOL_APPROVAL_REQUEST = "tool_approval_request"
    TOOL_APPROVAL_RESPONSE = "tool_approval_response"

    # Handoffs
    HANDOFF = "handoff"

    # Item streaming
    ITEM_STREAM_START = "item_stream_start"
    ITEM_STREAM_DELTA = "item_stream_delta"
    ITEM_STREAM_END = "item_stream_end"

    # Interrupts
    INTERRUPT = "interrupt"
    INTERRUPT_RESUME = "interrupt_resume"

    # Control
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


@dataclass
class RealtimeEvent:
    """Base class for realtime events."""

    type: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = "unknown"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    def to_sse(self) -> str:
        """Convert to Server-Sent Events format."""
        return f"data: {json.dumps(self.to_dict())}\n\n"

    @classmethod
    def create(
        cls,
        event_type: str,
        session_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> RealtimeEvent:
        return cls(type=event_type, session_id=session_id, payload=payload, metadata=metadata or {})


@dataclass
class ToolApprovalRequest(RealtimeEvent):
    """Request for human approval before executing a tool."""

    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""
    reason: str = ""
    timeout: float = 300.0  # 5 minutes default

    def __post_init__(self):
        self.type = RealtimeEventType.TOOL_APPROVAL_REQUEST
        self.payload = {
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "call_id": self.call_id,
            "reason": self.reason,
            "timeout": self.timeout,
        }

    @classmethod
    def create(
        cls,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        call_id: str,
        reason: str = "",
        timeout: float = 300.0,
    ) -> ToolApprovalRequest:
        return cls(
            session_id=session_id,
            tool_name=tool_name,
            tool_args=tool_args,
            call_id=call_id,
            reason=reason,
            timeout=timeout,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "tool_name": self.tool_name,
                "tool_args": self.tool_args,
                "call_id": self.call_id,
                "reason": self.reason,
                "timeout": self.timeout,
            },
            "metadata": self.metadata,
        }


@dataclass
class ToolApprovalResponse(RealtimeEvent):
    """Response to a tool approval request."""

    call_id: str = ""
    approved: bool = False
    response_data: dict[str, Any] | None = None

    def __post_init__(self):
        self.type = RealtimeEventType.TOOL_APPROVAL_RESPONSE
        self.payload = {
            "call_id": self.call_id,
            "approved": self.approved,
            "response_data": self.response_data,
        }

    @classmethod
    def create(
        cls,
        session_id: str,
        call_id: str,
        approved: bool,
        response_data: dict[str, Any] | None = None,
    ) -> ToolApprovalResponse:
        return cls(
            session_id=session_id,
            call_id=call_id,
            approved=approved,
            response_data=response_data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "call_id": self.call_id,
                "approved": self.approved,
                "response_data": self.response_data,
            },
            "metadata": self.metadata,
        }


@dataclass
class HandoffEvent(RealtimeEvent):
    """Agent handoff event for transferring control between agents."""

    from_agent: str = ""
    to_agent: str = ""
    reason: str = ""
    transfer_state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.type = RealtimeEventType.HANDOFF
        self.payload = {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "reason": self.reason,
            "transfer_state": self.transfer_state,
        }

    @classmethod
    def create(
        cls,
        session_id: str,
        from_agent: str,
        to_agent: str,
        reason: str = "",
        transfer_state: dict[str, Any] | None = None,
    ) -> HandoffEvent:
        return cls(
            session_id=session_id,
            from_agent=from_agent,
            to_agent=to_agent,
            reason=reason,
            transfer_state=transfer_state or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "from_agent": self.from_agent,
                "to_agent": self.to_agent,
                "reason": self.reason,
                "transfer_state": self.transfer_state,
            },
            "metadata": self.metadata,
        }


@dataclass
class ItemStreamStart(RealtimeEvent):
    """Start of an item stream (real-time data chunking)."""

    stream_name: str = ""
    item_type: str = "data"
    total_items: int | None = None

    def __post_init__(self):
        self.type = RealtimeEventType.ITEM_STREAM_START
        self.payload = {
            "stream_name": self.stream_name,
            "item_type": self.item_type,
            "total_items": self.total_items,
        }

    @classmethod
    def create(
        cls,
        session_id: str,
        stream_name: str,
        item_type: str = "data",
        total_items: int | None = None,
    ) -> ItemStreamStart:
        return cls(
            session_id=session_id,
            stream_name=stream_name,
            item_type=item_type,
            total_items=total_items,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "stream_name": self.stream_name,
                "item_type": self.item_type,
                "total_items": self.total_items,
            },
            "metadata": self.metadata,
        }


@dataclass
class ItemStreamDelta(RealtimeEvent):
    """Delta update for an item stream."""

    stream_name: str = ""
    item_index: int = 0
    data: Any = None
    is_final: bool = False

    def __post_init__(self):
        self.type = RealtimeEventType.ITEM_STREAM_DELTA
        self.payload = {
            "stream_name": self.stream_name,
            "item_index": self.item_index,
            "data": self.data,
            "is_final": self.is_final,
        }

    @classmethod
    def create(
        cls, session_id: str, stream_name: str, item_index: int, data: Any, is_final: bool = False
    ) -> ItemStreamDelta:
        return cls(
            session_id=session_id,
            stream_name=stream_name,
            item_index=item_index,
            data=data,
            is_final=is_final,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "stream_name": self.stream_name,
                "item_index": self.item_index,
                "data": self.data,
                "is_final": self.is_final,
            },
            "metadata": self.metadata,
        }


@dataclass
class ItemStreamEnd(RealtimeEvent):
    """End of an item stream."""

    stream_name: str = ""
    total_items: int = 0
    duration_ms: float = 0.0

    def __post_init__(self):
        self.type = RealtimeEventType.ITEM_STREAM_END
        self.payload = {
            "stream_name": self.stream_name,
            "total_items": self.total_items,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def create(
        cls, session_id: str, stream_name: str, total_items: int, duration_ms: float = 0.0
    ) -> ItemStreamEnd:
        return cls(
            session_id=session_id,
            stream_name=stream_name,
            total_items=total_items,
            duration_ms=duration_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "stream_name": self.stream_name,
                "total_items": self.total_items,
                "duration_ms": self.duration_ms,
            },
            "metadata": self.metadata,
        }


@dataclass
class InterruptEvent(RealtimeEvent):
    """Interrupt event for pausing execution."""

    interrupt_type: str = "user"
    data: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self):
        self.type = RealtimeEventType.INTERRUPT
        self.payload = {
            "interrupt_type": self.interrupt_type,
            "data": self.data,
            "reason": self.reason,
        }

    @classmethod
    def create(
        cls,
        session_id: str,
        interrupt_type: str = "user",
        data: dict[str, Any] | None = None,
        reason: str = "",
    ) -> InterruptEvent:
        return cls(
            session_id=session_id,
            interrupt_type=interrupt_type,
            data=data or {},
            reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "interrupt_type": self.interrupt_type,
                "data": self.data,
                "reason": self.reason,
            },
            "metadata": self.metadata,
        }


@dataclass
class InterruptResume(RealtimeEvent):
    """Resume after an interrupt."""

    resume_value: Any = None

    def __post_init__(self):
        self.type = RealtimeEventType.INTERRUPT_RESUME
        self.payload = {
            "value": self.resume_value,
        }

    @classmethod
    def create(cls, session_id: str, resume_value: Any) -> InterruptResume:
        return cls(
            session_id=session_id,
            resume_value=resume_value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "payload": {
                "value": self.resume_value,
            },
            "metadata": self.metadata,
        }


class RealtimeEventQueue:
    """Thread-safe queue for realtime event streaming."""

    def __init__(self, maxsize: int = 1000):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def put(self, event: RealtimeEvent) -> None:
        """Put event in queue and broadcast to subscribers."""
        await self._queue.put(event)
        # Broadcast to subscribers
        async with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(event.to_dict())
                except asyncio.QueueFull:
                    pass

    async def get(self) -> RealtimeEvent:
        """Get next event from queue."""
        return await self._queue.get()

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to event stream."""
        q = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribe from event stream."""
        self._subscribers.discard(q)


class RealtimeEventStream:
    """Async iterator for realtime events with filtering."""

    def __init__(self, queue: RealtimeEventQueue, event_types: list[str] | None = None):
        self._queue = queue
        self._subscriber = queue.subscribe()
        self._event_types = event_types
        self._closed = False

    def __aiter__(self) -> RealtimeEventStream:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._closed:
            raise StopAsyncIteration

        try:
            event = await asyncio.wait_for(self._subscriber.get(), timeout=1.0)
        except TimeoutError:
            # Send heartbeat to keep connection alive
            return {"type": "heartbeat", "timestamp": time.time()}

        if self._event_types and event.get("type") not in self._event_types:
            return await self.__anext__()

        return event

    async def close(self) -> None:
        """Close the stream."""
        self._closed = True
        self._queue.unsubscribe(self._subscriber)


class RealtimeEventBroadcaster:
    """Broadcasts realtime events to multiple subscribers."""

    def __init__(self):
        self._streams: dict[str, RealtimeEventQueue] = {}
        self._lock = asyncio.Lock()

    def get_queue(self, session_id: str) -> RealtimeEventQueue:
        """Get or create queue for session."""
        if session_id not in self._streams:
            self._streams[session_id] = RealtimeEventQueue()
        return self._streams[session_id]

    def create_stream(
        self, session_id: str, event_types: list[str] | None = None
    ) -> RealtimeEventStream:
        """Create a filtered event stream for a session."""
        queue = self.get_queue(session_id)
        return RealtimeEventStream(queue, event_types)

    async def broadcast(self, event: RealtimeEvent, session_id: str | None = None) -> None:
        """Broadcast event to session or all sessions."""
        if session_id:
            queue = self.get_queue(session_id)
            await queue.put(event)
        else:
            # Broadcast to all sessions
            for queue in self._streams.values():
                await queue.put(event)

    def get_session_count(self) -> int:
        return len(self._streams)

    async def close_session(self, session_id: str) -> None:
        """Close and remove a session."""
        if session_id in self._streams:
            del self._streams[session_id]


# Convenience factory functions
def create_tool_approval_request(
    session_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    call_id: str,
    reason: str = "",
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Create a tool approval request event."""
    return ToolApprovalRequest.create(
        session_id=session_id,
        tool_name=tool_name,
        tool_args=tool_args,
        call_id=call_id,
        reason=reason,
    ).to_dict()


def create_tool_approval_response(
    session_id: str,
    call_id: str,
    approved: bool,
    response_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a tool approval response event."""
    return ToolApprovalResponse.create(
        session_id=session_id,
        call_id=call_id,
        approved=approved,
        response_data=response_data,
    ).to_dict()


def create_handoff(
    session_id: str,
    from_agent: str,
    to_agent: str,
    reason: str = "",
    transfer_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a handoff event."""
    return HandoffEvent.create(
        session_id=session_id,
        from_agent=from_agent,
        to_agent=to_agent,
        reason=reason,
        transfer_state=transfer_state,
    ).to_dict()


def create_item_stream_start(
    session_id: str,
    stream_name: str,
    item_type: str = "data",
    total_items: int | None = None,
) -> dict[str, Any]:
    """Create an item stream start event."""
    return ItemStreamStart.create(
        session_id=session_id,
        stream_name=stream_name,
        item_type=item_type,
        total_items=total_items,
    ).to_dict()


def create_item_stream_delta(
    session_id: str,
    stream_name: str,
    item_index: int,
    data: Any,
    is_final: bool = False,
) -> dict[str, Any]:
    """Create an item stream delta event."""
    return ItemStreamDelta.create(
        session_id=session_id,
        stream_name=stream_name,
        item_index=item_index,
        data=data,
        is_final=is_final,
    ).to_dict()


def create_item_stream_end(
    session_id: str,
    stream_name: str,
    total_items: int,
    duration_ms: float = 0.0,
) -> dict[str, Any]:
    """Create an item stream end event."""
    return ItemStreamEnd.create(
        session_id=session_id,
        stream_name=stream_name,
        total_items=total_items,
        duration_ms=duration_ms,
    ).to_dict()


def create_interrupt(
    session_id: str,
    interrupt_type: str = "user",
    data: dict[str, Any] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Create an interrupt event."""
    return InterruptEvent.create(
        session_id=session_id,
        interrupt_type=interrupt_type,
        data=data,
        reason=reason,
    ).to_dict()


def create_interrupt_resume(session_id: str, resume_value: Any) -> dict[str, Any]:
    """Create an interrupt resume event."""
    return InterruptResume.create(
        session_id=session_id,
        resume_value=resume_value,
    ).to_dict()


# Global broadcaster instance
_global_broadcaster: RealtimeEventBroadcaster | None = None
_broadcaster_lock = asyncio.Lock()


async def get_global_broadcaster() -> RealtimeEventBroadcaster:
    """Get or create the global event broadcaster."""
    global _global_broadcaster
    async with _broadcaster_lock:
        if _global_broadcaster is None:
            _global_broadcaster = RealtimeEventBroadcaster()
        return _global_broadcaster


async def broadcast_tool_approval(
    session_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    call_id: str,
    reason: str = "",
    timeout: float = 300.0,
) -> None:
    """Broadcast a tool approval request."""
    broadcaster = await get_global_broadcaster()
    event = ToolApprovalRequest.create(session_id, tool_name, tool_args, call_id, "", 300.0)
    await broadcaster.broadcast(event, session_id)


async def broadcast_handoff(
    session_id: str,
    from_agent: str,
    to_agent: str,
    reason: str = "",
    transfer_state: dict[str, Any] | None = None,
) -> None:
    """Broadcast a handoff event."""
    broadcaster = await get_global_broadcaster()
    event = HandoffEvent.create(session_id, from_agent, to_agent, reason, transfer_state)
    await broadcaster.broadcast(event, session_id)


async def broadcast_item_stream_delta(
    session_id: str,
    stream_name: str,
    item_index: int,
    data: Any,
    is_final: bool = False,
) -> None:
    """Broadcast an item stream delta."""
    broadcaster = await get_global_broadcaster()
    event = ItemStreamDelta.create(session_id, stream_name, item_index, data, is_final)
    await broadcaster.broadcast(event, session_id)


__all__ = [
    "HandoffEvent",
    "InterruptEvent",
    "InterruptResume",
    "ItemStreamDelta",
    "ItemStreamEnd",
    "ItemStreamStart",
    "RealtimeEvent",
    "RealtimeEventBroadcaster",
    "RealtimeEventQueue",
    "RealtimeEventStream",
    "RealtimeEventType",
    "ToolApprovalRequest",
    "ToolApprovalResponse",
    "broadcast_handoff",
    "broadcast_item_stream_delta",
    "broadcast_tool_approval",
    "create_handoff",
    "create_interrupt",
    "create_interrupt_resume",
    "create_item_stream_delta",
    "create_item_stream_end",
    "create_item_stream_start",
    "create_tool_approval_request",
    "create_tool_approval_response",
    "get_global_broadcaster",
]
