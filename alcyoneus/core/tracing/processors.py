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

"""Tracing processor interface and registry for export pipeline."""

from __future__ import annotations

import abc
import logging

from .spans import Span
from .traces import Trace


logger = logging.getLogger("alcyoneus.tracing")


class TracingProcessor(abc.ABC):
    """Interface for trace/span export processors."""

    @abc.abstractmethod
    def on_span_start(self, span: Span) -> None:
        """Called when a span starts."""

    @abc.abstractmethod
    def on_span_end(self, span: Span) -> None:
        """Called when a span ends."""

    @abc.abstractmethod
    def on_trace_end(self, trace: Trace) -> None:
        """Called when a full trace finishes."""


class ConsoleTracingProcessor(TracingProcessor):
    """Processor that prints trace/span events to console logging."""

    def on_span_start(self, span: Span) -> None:
        span_type = span.span_data.type if span.span_data else "generic"
        logger.debug("[TRACE START] Span %s (%s)", span.span_id, span_type)

    def on_span_end(self, span: Span) -> None:
        span_type = span.span_data.type if span.span_data else "generic"
        logger.debug(
            "[TRACE END] Span %s (%s) in %.3fs", span.span_id, span_type, span.duration_seconds
        )

    def on_trace_end(self, trace: Trace) -> None:
        logger.info(
            "[TRACE COMPLETE] Trace %s '%s' finished with %d spans in %.3fs",
            trace.trace_id,
            trace.name,
            len(trace.spans),
            trace.duration_seconds,
        )


_global_processors: list[TracingProcessor] = [ConsoleTracingProcessor()]


def get_trace_processors() -> list[TracingProcessor]:
    """Get all registered trace processors."""
    return list(_global_processors)


def add_trace_processor(processor: TracingProcessor) -> None:
    """Add a trace processor to global pipeline."""
    _global_processors.append(processor)


def set_trace_processors(processors: list[TracingProcessor]) -> None:
    """Replace global trace processors list."""
    global _global_processors
    _global_processors = list(processors)


def flush_traces() -> None:
    """Flush any pending spans/traces across processors."""


__all__ = [
    "ConsoleTracingProcessor",
    "TracingProcessor",
    "add_trace_processor",
    "flush_traces",
    "get_trace_processors",
    "set_trace_processors",
]
