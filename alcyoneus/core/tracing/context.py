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

"""ContextVar-based active Trace and Span propagation for Alcyoneus OS."""

from __future__ import annotations

import contextvars
import uuid
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .spans import Span
    from .traces import Trace

_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar(
    "current_trace", default=None
)
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "current_span", default=None
)
_tracing_disabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "tracing_disabled", default=False
)


def get_current_trace() -> Trace | None:
    """Return the currently active Trace, if any."""
    return _current_trace.get()


def set_current_trace(trace: Trace | None) -> contextvars.Token:
    """Set the currently active Trace."""
    return _current_trace.set(trace)


def get_current_span() -> Span | None:
    """Return the currently active Span, if any."""
    return _current_span.get()


def set_current_span(span: Span | None) -> contextvars.Token:
    """Set the currently active Span."""
    return _current_span.set(span)


def is_tracing_disabled() -> bool:
    """Check if tracing is globally disabled for current context."""
    return _tracing_disabled.get()


def set_tracing_disabled(disabled: bool = True) -> None:
    """Globally disable or enable tracing for current context."""
    _tracing_disabled.set(disabled)


def gen_trace_id() -> str:
    """Generate a random unique trace ID string."""
    return f"tr_{uuid.uuid4().hex[:16]}"


def gen_span_id() -> str:
    """Generate a random unique span ID string."""
    return f"sp_{uuid.uuid4().hex[:12]}"


__all__ = [
    "gen_span_id",
    "gen_trace_id",
    "get_current_span",
    "get_current_trace",
    "is_tracing_disabled",
    "set_current_span",
    "set_current_trace",
    "set_tracing_disabled",
]
