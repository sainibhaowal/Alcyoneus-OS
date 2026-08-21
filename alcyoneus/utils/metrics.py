"""Lightweight metrics instrumentation utilities.

Design goals:
 - Zero dependency by default.
 - Cheap no-op when disabled.
 - Pluggable exporter (e.g., Prometheus scrape formatting) later.

Usage:
    from alcyoneus.utils.metrics import counter, timer
    counter('messages_written_total').inc()
    with timer('db_write_latency_ms'):
        ...
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


_LOCK = threading.RLock()
_COUNTERS: dict[str, Counter] = {}
_TIMERS: dict[str, TimerMetric] = {}

_ENABLED = True  # could be toggled by env in future


def enable_metrics(value: bool) -> None:  # simple toggle; acceptable global
    # Intentionally keeps a module-level switch—call sites cheap check.
    globals()["_ENABLED"] = value


@dataclass
class Counter:
    name: str
    value: int = 0

    def inc(self, amount: int = 1) -> None:
        if not _ENABLED:
            return
        with _LOCK:
            self.value += amount


@dataclass
class TimerMetric:
    name: str
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def observe(self, duration_ms: float) -> None:
        if not _ENABLED:
            return
        with _LOCK:
            self.count += 1
            self.total_ms += duration_ms
            self.max_ms = max(self.max_ms, duration_ms)

    @property
    def avg_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_ms / self.count


def counter(name: str) -> Counter:
    with _LOCK:
        c = _COUNTERS.get(name)
        if c is None:
            c = Counter(name)
            _COUNTERS[name] = c
        return c


def timer(name: str) -> _TimerCtx:  # convenience factory
    metric = _TIMERS.get(name)
    if metric is None:
        with _LOCK:
            metric = _TIMERS.get(name)
            if metric is None:
                metric = TimerMetric(name)
                _TIMERS[name] = metric
    return _TimerCtx(metric)


class _TimerCtx:
    def __init__(self, metric: TimerMetric):
        self.metric = metric
        self._start = None  # type: float | None

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._start is not None:
            elapsed_ms = (time.perf_counter() - self._start) * 1000.0
            self.metric.observe(elapsed_ms)
        # Do not suppress exceptions
        return False


def snapshot() -> dict:
    """Return a point-in-time snapshot of metrics (thread-safe copy)."""
    with _LOCK:
        return {
            "counters": {k: v.value for k, v in _COUNTERS.items()},
            "timers": {
                k: {
                    "count": t.count,
                    "avg_ms": t.avg_ms,
                    "max_ms": t.max_ms,
                }
                for k, t in _TIMERS.items()
            },
        }
