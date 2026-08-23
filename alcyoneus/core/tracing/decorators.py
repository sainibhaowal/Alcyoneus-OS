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

"""Decorators and context managers for Alcyoneus OS tracing."""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import Any

from .context import (
    gen_span_id,
    gen_trace_id,
    get_current_span,
    get_current_trace,
    is_tracing_disabled,
    set_current_span,
    set_current_trace,
)
from .processors import get_trace_processors
from .span_data import (
    AgentSpanData,
    CustomSpanData,
    FunctionSpanData,
    GenerationSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    SpanData,
    TaskSpanData,
    TurnSpanData,
)
from .spans import Span
from .traces import Trace


@contextlib.contextmanager
def trace(name: str = "agent_trace", metadata: dict[str, Any] | None = None) -> Generator[Trace]:
    """Context manager to start and finish a Trace."""
    if is_tracing_disabled():
        t = Trace(name=name, metadata=metadata)
        yield t
        return

    t = Trace(name=name, metadata=metadata)
    _token = set_current_trace(t)
    try:
        yield t
    finally:
        t.finish()
        for p in get_trace_processors():
            try:
                p.on_trace_end(t)
            except Exception:  # noqa: S110
                pass
        set_current_trace(None)


@contextlib.contextmanager
def span(span_data: SpanData) -> Generator[Span]:
    """Context manager to open and close a Span within the current Trace."""
    if is_tracing_disabled():
        s = Span(span_data=span_data)
        yield s
        return

    curr_trace = get_current_trace()
    parent_span = get_current_span()
    s = Span(
        span_id=gen_span_id(),
        trace_id=curr_trace.trace_id if curr_trace else gen_trace_id(),
        parent_span_id=parent_span.span_id if parent_span else None,
        span_data=span_data,
    )
    if curr_trace:
        curr_trace.add_span(s)

    for p in get_trace_processors():
        try:
            p.on_span_start(s)
        except Exception:  # noqa: S110
            pass

    _token = set_current_span(s)
    try:
        yield s
    except Exception as exc:
        s.set_error(exc)
        raise
    finally:
        s.finish()
        for p in get_trace_processors():
            try:
                p.on_span_end(s)
            except Exception:  # noqa: S110
                pass
        set_current_span(parent_span)


def agent_span(name: str, **kwargs: Any) -> contextlib._GeneratorContextManager:
    """Span context manager for an agent execution."""
    return span(AgentSpanData(name=name, **kwargs))


def task_span(name: str, **kwargs: Any) -> contextlib._GeneratorContextManager:
    """Span context manager for a top-level task execution."""
    return span(TaskSpanData(name=name, **kwargs))


def turn_span(turn_index: int, **kwargs: Any) -> contextlib._GeneratorContextManager:
    """Span context manager for a conversation turn."""
    return span(TurnSpanData(turn_index=turn_index, **kwargs))


def function_span(name: str, **kwargs: Any) -> contextlib._GeneratorContextManager:
    """Span context manager for a tool function call."""
    return span(FunctionSpanData(name=name, **kwargs))


def generation_span(model: str, **kwargs: Any) -> contextlib._GeneratorContextManager:
    """Span context manager for an LLM generation call."""
    return span(GenerationSpanData(model=model, **kwargs))


def guardrail_span(guardrail_name: str, **kwargs: Any) -> contextlib._GeneratorContextManager:
    """Span context manager for a guardrail check."""
    return span(GuardrailSpanData(guardrail_name=guardrail_name, **kwargs))


def handoff_span(
    from_agent: str, to_agent: str, **kwargs: Any
) -> contextlib._GeneratorContextManager:
    """Span context manager for an agent handoff."""
    return span(HandoffSpanData(from_agent=from_agent, to_agent=to_agent, **kwargs))


def custom_span(name: str, **kwargs: Any) -> contextlib._GeneratorContextManager:
    """Span context manager for a custom user span."""
    return span(CustomSpanData(name=name, **kwargs))


__all__ = [
    "agent_span",
    "custom_span",
    "function_span",
    "generation_span",
    "guardrail_span",
    "handoff_span",
    "span",
    "task_span",
    "trace",
    "turn_span",
]
