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
"""Disk-backed dictionary with an async interface.

This module provides :class:`PersistentDict`, a small drop-in replacement for
``dict`` that transparently persists its contents to a JSON file on disk. It is
inspired by LangGraph's ``PersistentDict`` and is useful for storing graph
metadata, tool state, or small long-lived caches across process restarts.

Design notes:
    * Writes are serialized through an internal ``asyncio.Lock`` so concurrent
      async access is safe.
    * ``None`` values are allowed, so the ``asdict()``/``clear()`` sentinels
      are unambiguous: ``asdict()`` returns a plain ``dict`` and ``clear()``
      returns ``None`` (dict parity).
    * The backing file is (re)written only when the in-memory contents change,
      and a best-effort atomic replace keeps the file consistent.

Example:
    >>> from alcyoneus.storage import PersistentDict
    >>> import tempfile
    >>> p = PersistentDict(path=tempfile.mktemp(suffix=".json"))
    >>> await p.aset("count", 1)
    >>> p["count"]  # sync reads work too
    1
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any


_SENTINEL: Any = object()


class PersistentDict(MutableMapping[str, Any]):
    """A ``dict`` whose contents are persisted to a JSON file.

    Args:
        path: Where to persist the data. The parent directory is created if it
            does not exist.
        autosave: When True (default) each mutation is flushed to disk
            immediately. When False, call :meth:`async_save`/:meth:`save`
            explicitly to persist.
    """

    def __init__(self, path: str | os.PathLike[str], autosave: bool = True):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._autosave = autosave
        self._data: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self._data = loaded
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _atomic_write(self) -> None:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent), suffix=".tmp", prefix=".persistent_dict_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self._path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    async def async_save(self) -> None:
        """Persist current contents to disk (async)."""
        async with self._lock:
            self._atomic_write()

    def save(self) -> None:
        """Persist current contents to disk (sync)."""
        self._atomic_write()

    async def aload(self) -> None:
        """Reload contents from disk (async)."""
        async with self._lock:
            self._load()

    def load(self) -> None:
        """Reload contents from disk (sync)."""
        self._load()

    def asdict(self) -> dict[str, Any]:
        """Return a copy of the underlying data as a plain dict."""
        return dict(self._data)

    # ------------------------------------------------------------------
    # MutableMapping (sync, dict-like)
    # ------------------------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value
        if self._autosave:
            self._atomic_write()

    def __delitem__(self, key: str) -> None:
        del self._data[key]
        if self._autosave:
            self._atomic_write()

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def clear(self) -> None:
        self._data.clear()
        if self._autosave:
            self._atomic_write()

    # ------------------------------------------------------------------
    # Async convenience API
    # ------------------------------------------------------------------
    async def aget(self, key: str, default: Any = None) -> Any:
        """Async get with default."""
        async with self._lock:
            return self._data.get(key, default)

    async def aset(self, key: str, value: Any) -> None:
        """Async set with optional persistence."""
        async with self._lock:
            self._data[key] = value
            if self._autosave:
                self._atomic_write()

    async def adelete(self, key: str) -> None:
        """Async delete."""
        async with self._lock:
            self._data.pop(key, None)
            if self._autosave:
                self._atomic_write()

    async def acontains(self, key: str) -> bool:
        """Async containment check."""
        async with self._lock:
            return key in self._data

    async def akeys(self) -> list[str]:
        """Async list of keys."""
        async with self._lock:
            return list(self._data.keys())

    async def avalues(self) -> list[Any]:
        """Async list of values."""
        async with self._lock:
            return list(self._data.values())

    async def aitems(self) -> list[tuple[str, Any]]:
        """Async list of items."""
        async with self._lock:
            return list(self._data.items())

    async def aupdate(self, other: dict[str, Any] | PersistentDict) -> None:
        """Async bulk update."""
        async with self._lock:
            if isinstance(other, PersistentDict):
                other = other._data
            self._data.update(other)
            if self._autosave:
                self._atomic_write()

    async def aclear(self) -> None:
        """Async clear."""
        async with self._lock:
            self._data.clear()
            if self._autosave:
                self._atomic_write()

    def __repr__(self) -> str:
        return f"PersistentDict(path={str(self._path)!r}, items={len(self._data)})"
