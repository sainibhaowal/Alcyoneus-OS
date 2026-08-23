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

"""Trace collection and lifecycle for Alcyoneus OS tracing."""

from __future__ import annotations

import time
import uuid
from typing import Any

from .spans import Span


class Trace:
    """Represents a collection of spans under a single execution trace."""

    def __init__(
        self,
        trace_id: str | None = None,
        name: str = "agent_trace",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:16]}"
        self.name = name
        self.metadata = metadata or {}
        self.spans: list[Span] = []
        self.start_time = time.time()
        self.end_time: float | None = None

    def add_span(self, span: Span) -> None:
        """Add a span to this trace."""
        span.trace_id = self.trace_id
        self.spans.append(span)

    def finish(self) -> None:
        """Finish the trace and all open spans."""
        if self.end_time is None:
            self.end_time = time.time()
            for s in self.spans:
                if s.end_time is None:
                    s.finish()

    @property
    def duration_seconds(self) -> float:
        """Return total duration of the trace in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    def export(self) -> dict[str, Any]:
        """Export trace as a JSON-serializable dictionary."""
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
            "spans": [s.export() for s in self.spans],
        }

    def __enter__(self) -> Trace:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.finish()


__all__ = ["Trace"]
