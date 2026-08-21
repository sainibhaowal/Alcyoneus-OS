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

"""Span execution lifecycle for Alcyoneus OS tracing."""

from __future__ import annotations

import time
import uuid
from typing import Any

from .span_data import SpanData


class SpanError:
    """Error representation attached to a span."""

    __slots__ = ("exception_type", "message", "traceback")

    def __init__(
        self,
        message: str,
        exception_type: str | None = None,
        traceback: str | None = None,
    ) -> None:
        self.message = message
        self.exception_type = exception_type
        self.traceback = traceback

    def export(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "exception_type": self.exception_type,
            "traceback": self.traceback,
        }


class Span:
    """Represents an active or completed span within a trace."""

    def __init__(
        self,
        span_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        span_data: SpanData | None = None,
    ) -> None:
        self.span_id = span_id or f"span_{uuid.uuid4().hex[:12]}"
        self.trace_id = trace_id or ""
        self.parent_span_id = parent_span_id
        self.span_data = span_data
        self.start_time = time.time()
        self.end_time: float | None = None
        self.error: SpanError | None = None
        self.attributes: dict[str, Any] = {}

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a key-value attribute on the span."""
        self.attributes[key] = value

    def set_error(self, error: Exception | str) -> None:
        """Mark span with an error."""
        if isinstance(error, Exception):
            self.error = SpanError(
                message=str(error),
                exception_type=type(error).__name__,
            )
        else:
            self.error = SpanError(message=str(error))

    def finish(self) -> None:
        """End the span."""
        if self.end_time is None:
            self.end_time = time.time()

    @property
    def duration_seconds(self) -> float:
        """Return span duration in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    def export(self) -> dict[str, Any]:
        """Export span details as a JSON dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "span_data": self.span_data.export() if self.span_data else None,
            "error": self.error.export() if self.error else None,
            "attributes": self.attributes,
        }

    def __enter__(self) -> Span:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_val is not None:
            self.set_error(exc_val)
        self.finish()


__all__ = ["Span", "SpanError"]
