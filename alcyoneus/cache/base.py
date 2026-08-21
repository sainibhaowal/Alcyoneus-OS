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

"""Base cache abstract interface and @cache decorator."""

from __future__ import annotations

import abc
import functools
import hashlib
import inspect
import json
import logging
from collections.abc import Callable
from typing import Any


logger = logging.getLogger("alcyoneus.cache")


def key_from_args(func_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Generate a deterministic SHA256 cache key from function arguments."""
    try:
        serialized = json.dumps(
            {"func": func_name, "args": args, "kwargs": kwargs}, default=str, sort_keys=True
        )
    except Exception:
        serialized = f"{func_name}:{args}:{kwargs}"
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class BaseCache(abc.ABC):
    """Abstract Base Class for execution caching stores."""

    @abc.abstractmethod
    def get(self, key: str) -> Any | None:
        """Get cached value by key."""

    @abc.abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set cached value with optional TTL seconds."""

    @abc.abstractmethod
    def clear(self) -> None:
        """Clear all cached entries."""


_global_cache_store: BaseCache | None = None


def set_global_cache(cache: BaseCache) -> None:
    """Set the global cache store instance."""
    global _global_cache_store
    _global_cache_store = cache


def get_global_cache() -> BaseCache | None:
    """Get the active global cache store instance."""
    return _global_cache_store


def cache(store: BaseCache | None = None, ttl: int | None = None) -> Callable[..., Any]:
    """Decorator to cache sync or async function execution outputs.

    Example:
        ```python
        @cache(ttl=3600)
        def expensive_computation(x: int) -> int:
            return x * 42
        ```
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            c = store or _global_cache_store
            if c is None:
                return func(*args, **kwargs)

            ckey = key_from_args(func.__name__, args, kwargs)
            cached_val = c.get(ckey)
            if cached_val is not None:
                logger.debug("Cache hit for '%s' (key=%s)", func.__name__, ckey)
                return cached_val

            res = func(*args, **kwargs)
            c.set(ckey, res, ttl=ttl)
            return res

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            c = store or _global_cache_store
            if c is None:
                return await func(*args, **kwargs)

            ckey = key_from_args(func.__name__, args, kwargs)
            cached_val = c.get(ckey)
            if cached_val is not None:
                logger.debug("Async cache hit for '%s' (key=%s)", func.__name__, ckey)
                return cached_val

            res = await func(*args, **kwargs)
            c.set(ckey, res, ttl=ttl)
            return res

        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

    return decorator


__all__ = [
    "BaseCache",
    "cache",
    "get_global_cache",
    "key_from_args",
    "set_global_cache",
]
