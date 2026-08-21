"""Per-node execution policies: retry, cache, error handling, and timeout.

These policies attach to individual nodes via ``StateGraph.add_node(..., retry_policy=...,
cache_policy=..., error_handler=..., timeout=...)`` and are honoured by the node
execution handlers.

Attributes:
    retry_policy (RetryPolicy | None): How many times to retry on failure.
    cache_policy (CachePolicy | None): Whether to cache node outputs by input
        signature and reuse them across runs.
    error_handler (NodeErrorHandler | None): Optional async callback invoked
        when the node raises; may return a partial state update.
    timeout (float | None): Maximum seconds the node may run before being
        cancelled with a TimeoutError.

Example:
    >>> from alcyoneus.core.graph import StateGraph
    >>> def flaky(state, config):
    ...     raise RuntimeError("boom")
    >>> async def on_error(state, config, exc):
    ...     return {"status": "failed"}
    >>> graph = StateGraph()
    >>> graph.add_node(
    ...     "flaky",
    ...     flaky,
    ...     retry_policy=RetryPolicy(max_retries=2),
    ...     error_handler=on_error,
    ...     timeout=5.0,
    ... )
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeAlias


logger = logging.getLogger("alcyoneus.graph")


@dataclass(frozen=True)
class RetryPolicy:
    """Retry configuration for a single node.

    Attributes:
        max_retries: Number of retry attempts after the first failure (default 0).
        initial_delay: Base delay before the first retry (seconds).
        max_delay: Upper bound on the back-off delay (seconds).
        backoff_factor: Multiplier applied to the delay after each retry.
        retryable_exceptions: Tuple of exception types that are retryable. When
            empty, all exceptions are retried.
    """

    max_retries: int = 0
    initial_delay: float = 0.1
    max_delay: float = 10.0
    backoff_factor: float = 2.0
    retryable_exceptions: tuple[type[BaseException], ...] = ()

    def should_retry(self, exc: BaseException) -> bool:
        """Return True if *exc* should be retried under this policy."""
        if self.retryable_exceptions and not isinstance(exc, self.retryable_exceptions):
            return False
        return True


@dataclass(frozen=True)
class CachePolicy:
    """Caching policy for node outputs.

    When enabled, the node output for a given (state-signature, config) pair is
    memoized and reused on subsequent invocations. Use for expensive,
    deterministic nodes.

    Attributes:
        enabled: Master switch (default True).
        key_fn: Optional callable ``(state, config) -> str`` producing a cache
            key. Defaults to a hash of serialized state + node name.
        ttl: Optional time-to-live in seconds; cached entries expire after this.
    """

    enabled: bool = True
    key_fn: Callable[[Any, dict[str, Any]], str] | None = None
    ttl: float | None = None


NodeErrorHandler: TypeAlias = Callable[
    [Any, dict[str, Any], BaseException],
    dict[str, Any] | Awaitable[dict[str, Any]],
]


@dataclass
class NodeExecutionPolicy:
    """Aggregated execution policies for a single node.

    Attributes:
        retry_policy (RetryPolicy | None): Retry behavior.
        cache_policy (CachePolicy | None): Output memoization.
        error_handler (NodeErrorHandler | None): Error recovery callback.
        timeout (float | None): Wall-clock timeout in seconds.
    """

    retry_policy: RetryPolicy | None = None
    cache_policy: CachePolicy | None = None
    error_handler: NodeErrorHandler | None = None
    timeout: float | None = None

    @property
    def has_any(self) -> bool:
        return (
            self.retry_policy is not None
            or self.cache_policy is not None
            or self.error_handler is not None
            or self.timeout is not None
        )


async def execute_with_policy(
    coro_factory: Callable[[], Awaitable[Any]],
    policy: NodeExecutionPolicy | None,
    *,
    node_name: str,
    state: Any,
    config: dict[str, Any],
) -> Any:
    """Run a node's coroutine factory honouring the node execution policy.

    The policy applies, in order:
    1. output memoization (cache_policy)
    2. wall-clock timeout (timeout)
    3. retries with exponential back-off (retry_policy)
    4. error recovery (error_handler)

    Args:
        coro_factory: Zero-arg async callable returning the node coroutine.
        policy: The node's execution policy (or None for no policy).
        node_name: Name of the node (used in logs/cache keys).
        state: The input state (used for cache key derivation).
        config: The run configuration.

    Returns:
        The node's return value (raw, or the error_handler's partial update).

    Raises:
        Any exception raised by the node when no error_handler is configured,
        after retries are exhausted.
    """
    if policy is None or not policy.has_any:
        return await coro_factory()

    retry_policy = policy.retry_policy
    error_handler = policy.error_handler

    def _make_task() -> Awaitable[Any]:
        coro = coro_factory()
        if policy.timeout and policy.timeout > 0:
            return asyncio.wait_for(coro, timeout=policy.timeout)
        return coro

    async def _attempt() -> Any:
        return await _make_task()

    cache = policy.cache_policy
    if cache and cache.enabled:
        key_fn = cache.key_fn or default_node_cache_key
        cache_key = key_fn(state, config) if key_fn else f"{node_name}:{id(state)}"
        cache_storage = _get_node_cache(node_name)
        cached = cache_storage.get(cache_key, cache.ttl)
        if cached is not _CACHE_MISS:
            logger.debug("Node '%s' cache hit for key %s", node_name, cache_key)
            return cached

        try:
            result = await _run_with_retries(_attempt, retry_policy, node_name)
            cache_storage.set(cache_key, result, cache.ttl)
            return result
        except Exception as exc:
            return await _handle_node_error(exc, error_handler, node_name, state, config)

    try:
        return await _run_with_retries(_attempt, retry_policy, node_name)
    except Exception as exc:
        return await _handle_node_error(exc, error_handler, node_name, state, config)


async def _run_with_retries(
    attempt: Callable[[], Awaitable[Any]],
    retry_policy: RetryPolicy | None,
    node_name: str,
) -> Any:
    if retry_policy is None or retry_policy.max_retries <= 0:
        return await attempt()

    delay = retry_policy.initial_delay
    last_exc: BaseException | None = None
    for attempt_number in range(retry_policy.max_retries + 1):
        try:
            return await attempt()
        except Exception as exc:
            last_exc = exc
            if attempt_number >= retry_policy.max_retries or not retry_policy.should_retry(exc):
                raise
            wait = min(delay, retry_policy.max_delay)
            logger.warning(
                "Node '%s' attempt %d failed (%s); retrying in %.2fs",
                node_name,
                attempt_number + 1,
                type(exc).__name__,
                wait,
            )
            await asyncio.sleep(wait)
            delay *= retry_policy.backoff_factor
    raise last_exc  # type: ignore[misc]


async def _handle_node_error(
    exc: BaseException,
    error_handler: NodeErrorHandler | None,
    node_name: str,
    state: Any,
    config: dict[str, Any],
) -> Any:
    if error_handler is None:
        raise exc
    logger.warning(
        "Node '%s' failed with %s; invoking error_handler",
        node_name,
        type(exc).__name__,
    )
    result = error_handler(state, config, exc)
    if inspect.isawaitable(result):
        result = await result
    return result


# --- Simple in-process node cache (LRU-ish, time-aware) ---------------------- #

_CACHE_MISS = object()


class _NodeCache:
    def __init__(self, max_entries: int = 128) -> None:
        self._store: dict[str, tuple[float | None, Any]] = {}
        self._max_entries = max_entries

    def get(self, key: str, ttl: float | None) -> Any:
        entry = self._store.get(key)
        if entry is None:
            return _CACHE_MISS
        expires_at, value = entry
        if expires_at is not None and expires_at < asyncio.get_event_loop().time():
            self._store.pop(key, None)
            return _CACHE_MISS
        return value

    def set(self, key: str, value: Any, ttl: float | None) -> None:
        expires_at = asyncio.get_event_loop().time() + ttl if ttl is not None else None
        if len(self._store) >= self._max_entries:
            # evict oldest (approx: first key)
            self._store.pop(next(iter(self._store)), None)
        self._store[key] = (expires_at, value)

    def clear(self) -> None:
        self._store.clear()


_NODE_CACHES: dict[str, _NodeCache] = {}


def _get_node_cache(node_name: str) -> _NodeCache:
    if node_name not in _NODE_CACHES:
        _NODE_CACHES[node_name] = _NodeCache()
    return _NODE_CACHES[node_name]


def clear_node_cache(node_name: str | None = None) -> None:
    """Clear cached node outputs (optionally for a single node)."""
    if node_name is None:
        _NODE_CACHES.clear()
    else:
        cache = _NODE_CACHES.pop(node_name, None)
        if cache is not None:
            cache.clear()


def default_node_cache_key(state: Any, config: dict[str, Any]) -> str:
    """Default deterministic cache key from serialized state + config."""
    import hashlib

    state_data = state.model_dump_json() if hasattr(state, "model_dump_json") else str(state)
    thread_id = config.get("thread_id", "")
    raw = f"{state_data}|{thread_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "CachePolicy",
    "NodeErrorHandler",
    "NodeExecutionPolicy",
    "RetryPolicy",
    "clear_node_cache",
    "default_node_cache_key",
    "execute_with_policy",
]
