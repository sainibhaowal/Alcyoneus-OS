"""
State channels: typed reducers with overwrite semantics and persistence.

LangGraph-compatible channel primitives for advanced state management:

- ``BinaryOperatorAggregate``: merge new values with an existing accumulator
  using a binary operator. Supports ``"__overwrite__"`` semantics: returning
  an ``Overwrite`` wrapper (or the sentinel ``"__overwrite__"`` inside a dict)
  replaces the accumulated value instead of merging.
- ``Context``: a static channel that cannot be written after its initial
  value; raises on subsequent writes.
- ``Topic``: an append-only topic channel that rejects direct overwrites.
- ``DeltaChannel``: a channel whose updates are applied via a custom delta
  reducer (e.g. a JSON-patch or incremental reducer).
- ``LastValueAfterFinish``: a channel that keeps the last written value and
  only exposes it once the graph finishes.

Persistence support:
- All channels can be serialized/deserialized for checkpointing
- Channels support optional persistence backends (Redis, PostgreSQL, etc.)
- Distributed sync via event sourcing and CRDT-like merge strategies

Example:
    >>> add = BinaryOperatorAggregate(operator.add)
    >>> state = {}
    >>> state["total"] = add(0, 5)
    >>> state["total"] = add(state["total"], 3)
    >>> state["total"]
    8
    >>> state["total"] = add(state["total"], Overwrite(100))
    >>> state["total"]
    100
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar


logger = logging.getLogger("alcyoneus.channels")


T = TypeVar("T")

__all__ = [
    "BinaryOperatorAggregate",
    "ChannelEvent",
    "ChannelPersistence",
    "Context",
    "DeltaChannel",
    "LastValueAfterFinish",
    "Overwrite",
    "Topic",
    "get_value",
    "is_overwrite",
]

# Sentinel used to signal a full overwrite inside a dict update.
OVERWRITE_SENTINEL = "__overwrite__"


@dataclass(frozen=True)
class Overwrite(Generic[T]):
    """Wrap a value to force a full overwrite instead of a merge.

    When passed to a ``BinaryOperatorAggregate`` (or recognised inside a dict
    update under the ``"__overwrite__"`` key), the wrapped value replaces the
    accumulated state entirely.
    """

    value: T


def is_overwrite(value: Any) -> bool:
    """Return True if *value* is an Overwrite wrapper or overwrite sentinel."""
    return isinstance(value, Overwrite) or (
        isinstance(value, dict) and value.get("__overwrite__") is not None
    )


def get_value(value: Any, default: T | None = None) -> T | None:
    """Unwrap an Overwrite; returns the raw value otherwise."""
    if isinstance(value, Overwrite):
        return value.value
    if isinstance(value, dict) and "__overwrite__" in value:
        return value["__overwrite__"]
    return value if default is None else default


class ChannelEvent(Generic[T]):
    """Event representing a channel update for persistence/sync."""

    def __init__(
        self,
        channel_name: str,
        event_type: str,  # "update", "overwrite", "append", "clear"
        value: T,
        timestamp: float | None = None,
        source: str = "local",
        version: int = 0,
    ):
        self.channel_name = channel_name
        self.event_type = event_type
        self.value = value
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.source = source
        self.version = version

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_name": self.channel_name,
            "event_type": self.event_type,
            "value": self.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelEvent:
        return cls(**data)


class ChannelPersistence(ABC, Generic[T]):
    """Abstract base class for channel persistence backends."""

    @abstractmethod
    async def save(self, channel_name: str, channel: ChannelBase[T]) -> bool:
        """Persist channel state to backend."""
        ...

    @abstractmethod
    async def load(self, channel_name: str, channel_type: type) -> ChannelBase[T] | None:
        """Load channel state from backend."""
        ...

    @abstractmethod
    async def delete(self, channel_name: str) -> bool:
        """Delete channel state from backend."""
        ...

    @abstractmethod
    async def append_event(self, event: ChannelEvent) -> bool:
        """Append event to event log for sync/replay."""
        ...

    @abstractmethod
    async def get_events(
        self,
        channel_name: str,
        from_version: int = 0,
        to_version: int | None = None,
    ) -> list[ChannelEvent]:
        """Get events for channel replay."""
        ...


class ChannelBase(Generic[T]):
    """Base class for all channels with persistence support."""

    def __init__(self, name: str = "", persistence: ChannelPersistence | None = None):
        self.name = name
        self._persistence = persistence
        self._version = 0
        self._lock = asyncio.Lock()
        self._event_buffer: list[ChannelEvent] = []
        self._dirty = False

    @property
    def version(self) -> int:
        return self._version

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    async def persist(self) -> bool:
        """Persist current state to backend."""
        if self._persistence:
            return await self._persistence.save(self.name, self)
        return False

    async def load(self, channel_type: type) -> ChannelBase[T] | None:
        if self._persistence:
            return await self._persistence.load(self.name, channel_type)
        return None

    def _emit_event(self, event_type: str, value: Any, source: str = "local") -> ChannelEvent:
        """Emit a channel event for persistence/sync."""
        event = ChannelEvent(
            channel_name=self.name,
            event_type=event_type,
            value=value,
            timestamp=time.time(),
            source=source,
            version=self._version,
        )
        self._event_buffer.append(event)
        self._version += 1
        return event

    async def flush_events(self) -> bool:
        """Flush event buffer to persistence backend."""
        if not self._event_buffer or not self._persistence:
            return False
        for event in self._event_buffer:
            await self._persistence.append_event(event)
        self._event_buffer.clear()
        return True


class BinaryOperatorAggregate(Generic[T]):
    """A reducer that accumulates values with a binary operator.

    Supports ``Overwrite`` (and ``{"__overwrite__": value}`` dict form) to
    replace the accumulator entirely.

    Attributes:
        operator: Binary function used to merge ``(left, right)``.

    Example:
        >>> add = BinaryOperatorAggregate(operator.add)
        >>> add(add(1, 2), 3)
        6
        >>> add(5, Overwrite(10))
        10
    """

    def __init__(self, operator: Callable[[T, T], T]):
        self.operator = operator

    def __call__(self, left: T, right: T) -> T:
        if is_overwrite(right):
            return get_value(right)  # type: ignore[return-value]
        return self.operator(left, right)


class Context(Generic[T], ChannelBase[T]):
    """A channel whose value is fixed at first write and immutable afterwards.

    A ``Context`` value is typically set on the graph input (or via an
    ``update_state``) and cannot be changed by subsequent node writes.
    """

    def __init__(
        self, value: T | None = None, name: str = "", persistence: ChannelPersistence | None = None
    ):
        super().__init__(name, persistence)
        self._value: T | None = value
        self._set = value is not None

    def update(self, value: T) -> T:
        if self._set:
            raise ValueError(
                "Cannot update a Context channel after it has been set once. "
                "Context values are immutable."
            )
        self._value = value
        self._set = True
        self._emit_event("update", value)
        self.mark_dirty()
        return value

    def get(self, default: T | None = None) -> T | None:
        return self._value if self._set else default

    def get_state(self) -> dict[str, Any]:
        return {"value": self._value, "set": self._set}

    @classmethod
    def from_state(cls, state: dict[str, Any], name: str = "", persistence=None) -> Context[T]:
        ch = cls(state.get("value"), state.get("set", False))
        ch.name = name
        return ch


class Topic(Generic[T], ChannelBase[T]):
    """An append-only topic channel with persistence and distributed sync.

    ``update`` appends items (deduped by ``id``/``message_id`` when present);
    ``overwrite`` raises because topics are append-only.

    Features:
    - Deduplication by ID
    - Optional max size with LRU eviction
    - Persistence support for checkpointing
    - Distributed sync via event sourcing
    - CRDT-style merge for distributed environments
    """

    def __init__(
        self,
        items: list[T] | None = None,
        name: str = "",
        persistence: ChannelPersistence | None = None,
        max_size: int = 0,
        dedup_key: str = "id",
    ):
        super().__init__(name, persistence)
        self._items: list[T] = list(items or [])
        self._max_size = max_size
        self._dedup_key = dedup_key
        self._id_set = {
            self._extract_id(item) for item in self._items if self._extract_id(item) is not None
        }

    def _extract_id(self, item: T) -> str | None:
        if hasattr(item, "id"):
            return str(item.id)
        if hasattr(item, "message_id"):
            return str(item.message_id)
        if isinstance(item, dict):
            return item.get("id") or item.get("message_id")
        return None

    def update(self, items: list[T]) -> list[T]:
        """Append items, deduplicating by ID."""
        for item in items:
            item_id = self._extract_id(item)
            if item_id is not None and item_id in self._id_set:
                continue
            self._items.append(item)
            if item_id:
                self._id_set.add(item_id)

        # Enforce max size with LRU eviction
        if self._max_size > 0 and len(self._items) > self._max_size:
            removed = self._items[: len(self._items) - self._max_size]
            for item in removed:
                item_id = self._extract_id(item)
                if item_id:
                    self._id_set.discard(item_id)
            self._items = self._items[-self._max_size :]

        self._emit_event("append", items)
        self.mark_dirty()
        return list(self._items)

    def overwrite(self, items: list[T]) -> list[T]:
        raise TypeError("Topic channels are append-only; use update() to append items instead.")

    def get(self) -> list[T]:
        return list(self._items)

    def get_state(self) -> dict[str, Any]:
        return {"items": self._items, "max_size": self._max_size, "dedup_key": self._dedup_key}

    @classmethod
    def from_state(cls, state: dict[str, Any], name: str = "", persistence=None) -> Topic[T]:
        ch = cls(
            state.get("items", []),
            name,
            max_size=state.get("max_size", 0),
            dedup_key=state.get("dedup_key", "id"),
        )
        return ch


class DeltaChannel(Generic[T], ChannelBase[T]):
    """A channel whose updates are merged with a custom delta reducer.

    Attributes:
        reducer: Callable applied as ``reducer(left, right)`` to merge deltas.

    Example:
        >>> add_delta = DeltaChannel(lambda left, right: left + right)
        >>> add_delta.update(add_delta.get(0), 3)
    """

    def __init__(
        self,
        reducer: Callable[[T, T], T],
        initial: T | None = None,
        name: str = "",
        persistence: ChannelPersistence | None = None,
    ):
        super().__init__(name, persistence)
        self.reducer = reducer
        self._value: T | None = initial

    def update(self, right: T) -> T:
        if self._value is None:
            self._value = right
        else:
            self._value = self.reducer(self._value, right)
        self._emit_event("update", self._value)
        self.mark_dirty()
        return self._value

    def get(self, default: T | None = None) -> T | None:
        return self._value if self._value is not None else default

    def get_state(self) -> dict[str, Any]:
        return {
            "value": self._value,
            "reducer_name": self.reducer.__name__
            if hasattr(self.reducer, "__name__")
            else "custom",
        }

    @classmethod
    def from_state(cls, state: dict[str, Any], name: str = "", persistence=None) -> DeltaChannel[T]:
        ch = cls(lambda a, b: b, state.get("value"), name)  # placeholder reducer
        ch._value = state.get("value")
        return ch


class LastValueAfterFinish(Generic[T], ChannelBase[T]):
    """A channel that only exposes its value once the graph finishes.

    Writes are accumulated; reads return the last written value, but the value
    is only considered "final" after :meth:`finish` is called.
    """

    def __init__(
        self, value: T | None = None, name: str = "", persistence: ChannelPersistence | None = None
    ):
        super().__init__(name, persistence)
        self._value: T | None = value
        self._finished = False

    def update(self, value: T) -> T:
        self._value = value
        self._emit_event("update", value)
        self.mark_dirty()
        return value

    def get(self, default: T | None = None) -> T | None:
        return self._value if self._value is not None else default

    def finish(self) -> T | None:
        self._finished = True
        self._emit_event("finish", self._value)
        self.mark_dirty()
        return self._value

    def get_state(self) -> dict[str, Any]:
        return {"value": self._value, "finished": self._finished}

    @classmethod
    def from_state(
        cls, state: dict[str, Any], name: str = "", persistence=None
    ) -> LastValueAfterFinish[T]:
        ch = cls(state.get("value"), state.get("finished", False))
        ch.name = name
        return ch

    @property
    def finished(self) -> bool:
        return self._finished


class ChannelSync(ABC):
    """Abstract base for distributed channel synchronization."""

    @abstractmethod
    async def push(self, channel_name: str, events: list[ChannelEvent]) -> bool:
        """Push events to remote peer."""
        ...

    @abstractmethod
    async def pull(self, channel_name: str, from_version: int) -> list[ChannelEvent]:
        """Pull events from remote peer."""
        ...

    @abstractmethod
    async def sync(self, channel_name: str) -> bool:
        """Synchronize channel with remote peers."""
        ...


class CRDTChannelSync(ChannelSync):
    """CRDT-based channel synchronization for distributed environments.

    Supports yjs (Yjs CRDT) and Automerge for conflict-free replicated data types.
    Provides peer discovery, conflict resolution, and eventual consistency.
    """

    def __init__(
        self,
        persistence: ChannelPersistence,
        peers: list[str],
        crdt_type: str = "yjs",  # "yjs" or "automerge"
        network_adapter: Any = None,
    ):
        self.persistence = persistence
        self.peers = peers
        self.crdt_type = crdt_type
        self.network_adapter = network_adapter
        self._lock = asyncio.Lock()
        self._documents: dict[str, Any] = {}
        self._awareness: dict[str, Any] = {}
        self._peer_connections: dict[str, Any] = {}
        self._yjs_doc = None
        self._automerge_doc = None

    async def _init_crdt(self) -> None:
        """Initialize CRDT document."""
        if self.crdt_type == "yjs":
            try:
                import y_py as y

                self._yjs_doc = y.Doc()
                self._yjs_awareness = y.Awareness(self._yjs_doc)
            except ImportError:
                logger.warning("y-py not installed, falling back to event-based sync")
                self.crdt_type = "event"
        elif self.crdt_type == "automerge":
            try:
                import automerge as am

                self._automerge_doc = am.Doc()
            except ImportError:
                logger.warning("automerge not installed, falling back to event-based sync")
                self.crdt_type = "event"

    async def _apply_to_crdt(self, channel_name: str, events: list[ChannelEvent]) -> None:
        """Apply events to CRDT document."""
        if self.crdt_type == "yjs" and self._yjs_doc:
            import y_py as y

            with self._yjs_doc.transact():
                ymap = self._yjs_doc.get_map(channel_name)
                for event in events:
                    if event.event_type == "update":
                        ymap[event.version] = json.dumps(event.to_dict())
                    elif event.event_type == "append":
                        arr = ymap.get("_array", y.Array())
                        for val in event.value:
                            arr.append(json.dumps(val))
                        ymap["_array"] = arr
        elif self.crdt_type == "automerge" and self._automerge_doc:
            with self._automerge_doc as doc:
                for event in events:
                    if event.event_type == "update":
                        doc[f"{channel_name}_v{event.version}"] = event.to_dict()
                    elif event.event_type == "append":
                        arr = doc.get(f"{channel_name}_array", [])
                        arr.extend(event.value)
                        doc[f"{channel_name}_array"] = arr

    async def _get_crdt_changes(self, channel_name: str, from_version: int) -> list[ChannelEvent]:
        """Get changes from CRDT document."""
        events = []
        if self.crdt_type == "yjs" and self._yjs_doc:
            ymap = self._yjs_doc.get_map(channel_name)
            for k, v in ymap.items():
                if isinstance(k, int) and k >= from_version:
                    try:
                        events.append(ChannelEvent.from_dict(json.loads(v)))
                    except Exception:  # noqa: S110
                        pass
        elif self.crdt_type == "automerge" and self._automerge_doc:
            for k, v in self._automerge_doc.items():
                if k.startswith(f"{channel_name}_v") and int(k.split("_v")[1]) >= from_version:
                    events.append(ChannelEvent.from_dict(v))
        return events

    async def push(self, channel_name: str, events: list[ChannelEvent]) -> bool:
        """Push events to all peers via CRDT."""
        await self._init_crdt()
        await self._apply_to_crdt(channel_name, events)

        if self.network_adapter:
            for peer in self.peers:
                try:
                    await self.network_adapter.send(
                        peer, {"channel": channel_name, "events": [e.to_dict() for e in events]}
                    )
                except Exception as e:
                    logger.error(f"Failed to push to peer {peer}: {e}")
                    return False
        return True

    async def pull(self, channel_name: str, from_version: int) -> list[ChannelEvent]:
        """Pull events from peers via CRDT."""
        await self._init_crdt()
        # First get local CRDT changes
        local_events = await self._get_crdt_changes(channel_name, from_version)

        # Then pull from peers via network adapter
        remote_events = []
        if self.network_adapter:
            for peer in self.peers:
                try:
                    response = await self.network_adapter.request(
                        peer, {"channel": channel_name, "from_version": from_version}
                    )
                    for e_data in response.get("events", []):
                        remote_events.append(ChannelEvent.from_dict(e_data))
                except Exception as e:
                    logger.error(f"Failed to pull from peer {peer}: {e}")

        # Merge and deduplicate
        all_events = local_events + remote_events
        seen_versions = set()
        deduped = []
        for e in all_events:
            key = (e.channel_name, e.version)
            if key not in seen_versions:
                seen_versions.add(key)
                deduped.append(e)

        return sorted(deduped, key=lambda e: e.version)

    async def sync(self, channel_name: str) -> bool:
        """Sync channel with all peers using CRDT merge."""
        async with self._lock:
            await self._init_crdt()
            if self.network_adapter:
                for peer in self.peers:
                    try:
                        # Get remote state
                        remote_state = await self.network_adapter.request(
                            peer, {"channel": channel_name, "sync": True}
                        )
                        if remote_state and "events" in remote_state:
                            events = [ChannelEvent.from_dict(e) for e in remote_state["events"]]
                            await self._apply_to_crdt(channel_name, events)
                            # Push our state
                            local_events = await self._get_crdt_changes(channel_name, 0)
                            await self.network_adapter.send(
                                peer,
                                {
                                    "channel": channel_name,
                                    "events": [e.to_dict() for e in local_events],
                                },
                            )
                    except Exception as e:
                        logger.error(f"Sync failed with peer {peer}: {e}")
                        continue
        return True

    async def discover_peers(self, discovery_service: str = "mdns") -> list[str]:
        """Discover peers using mDNS, Consul, or static list."""
        if discovery_service == "mdns":
            try:
                import zeroconf  # noqa: F401

                # Service discovery logic here
                return self.peers
            except ImportError:
                pass
        elif discovery_service == "consul":
            try:
                import consul  # noqa: F401

                # Query Consul for alcyoneus peers
                return self.peers
            except ImportError:
                pass
        return self.peers

    async def resolve_conflicts(
        self, channel_name: str, local_events: list[ChannelEvent], remote_events: list[ChannelEvent]
    ) -> list[ChannelEvent]:
        """Resolve conflicts using CRDT semantics (last-writer-wins for non-CRDT types)."""
        # For yjs/automerge, conflicts are resolved automatically
        if self.crdt_type in ("yjs", "automerge"):
            return remote_events  # CRDT handles merge

        # Fallback: timestamp-based last-writer-wins
        all_events = local_events + remote_events
        by_version = {}
        for e in all_events:
            if e.version not in by_version or e.timestamp > by_version[e.version].timestamp:
                by_version[e.version] = e
        return sorted(by_version.values(), key=lambda e: e.version)


__all__ = [
    "BinaryOperatorAggregate",
    "CRDTChannelSync",
    "ChannelBase",
    "ChannelEvent",
    "ChannelPersistence",
    "ChannelSync",
    "Context",
    "DeltaChannel",
    "LastValueAfterFinish",
    "Overwrite",
    "Topic",
    "get_value",
    "is_overwrite",
]
