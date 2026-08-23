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

"""In-Memory cache implementation with TTL support."""

from __future__ import annotations

import time
from typing import Any

from .base import BaseCache


class InMemoryCache(BaseCache):
    """Production-grade In-Memory cache store with TTL expiration."""

    def __init__(self, default_ttl: int | None = None) -> None:
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[Any, float | None]] = {}

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            return None
        val, expiry = self._store[key]
        if expiry is not None and time.time() > expiry:
            del self._store[key]
            return None
        return val

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        eff_ttl = ttl if ttl is not None else self.default_ttl
        expiry = (time.time() + eff_ttl) if eff_ttl is not None else None
        self._store[key] = (value, expiry)

    def clear(self) -> None:
        self._store.clear()


__all__ = ["InMemoryCache"]
