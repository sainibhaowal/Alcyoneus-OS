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
"""Checkpointer capabilities for conformance testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Capability(str, Enum):
    """Checkpointer capabilities."""

    PUT = "put"
    PUT_WRITES = "put_writes"
    GET_TUPLE = "get_tuple"
    LIST = "list"
    DELETE_THREAD = "delete_thread"
    DELETE_FOR_RUNS = "delete_for_runs"
    COPY_THREAD = "copy_thread"
    PRUNE = "prune"
    DELTA_CHANNEL_HISTORY = "delta_channel_history"
    MESSAGES = "messages"
    THREADS = "threads"


BASE_CAPABILITIES = [
    Capability.PUT,
    Capability.PUT_WRITES,
    Capability.GET_TUPLE,
    Capability.LIST,
    Capability.DELETE_THREAD,
]

EXTENDED_CAPABILITIES = BASE_CAPABILITIES + [
    Capability.DELETE_FOR_RUNS,
    Capability.COPY_THREAD,
    Capability.PRUNE,
    Capability.DELTA_CHANNEL_HISTORY,
    Capability.MESSAGES,
    Capability.THREADS,
]


@dataclass
class DetectedCapabilities:
    """Detected capabilities from a checkpointer instance."""

    capabilities: list[Capability] = field(default_factory=list)

    @classmethod
    def from_instance(cls, checkpointer: Any) -> DetectedCapabilities:
        """Detect capabilities from a checkpointer instance."""
        caps = []
        if hasattr(checkpointer, "aput_state"):
            caps.append(Capability.PUT)
        if hasattr(checkpointer, "aput_writes"):
            caps.append(Capability.PUT_WRITES)
        if hasattr(checkpointer, "aget_state"):
            caps.append(Capability.GET_TUPLE)
        if hasattr(checkpointer, "alist"):
            caps.append(Capability.LIST)
        if hasattr(checkpointer, "adelete_thread"):
            caps.append(Capability.DELETE_THREAD)
        if hasattr(checkpointer, "adelete_for_runs"):
            caps.append(Capability.DELETE_FOR_RUNS)
        if hasattr(checkpointer, "acopy_thread"):
            caps.append(Capability.COPY_THREAD)
        if hasattr(checkpointer, "aprune"):
            caps.append(Capability.PRUNE)
        if hasattr(checkpointer, "aget_delta_channel_history"):
            caps.append(Capability.DELTA_CHANNEL_HISTORY)
        if hasattr(checkpointer, "aput_messages"):
            caps.append(Capability.MESSAGES)
        if hasattr(checkpointer, "alist_threads"):
            caps.append(Capability.THREADS)
        return cls(capabilities=caps)


@dataclass
class CapabilityResult:
    """Result of a capability test."""

    capability: Capability
    passed: bool
    error: str | None = None


@dataclass
class CapabilityReport:
    """Full conformance report for a checkpointer."""

    checkpointer_name: str
    results: list[CapabilityResult]
    detected_capabilities: DetectedCapabilities

    @property
    def passed_all_base(self) -> bool:
        """Check if all base capabilities passed."""
        return all(r.passed for r in self.results if r.capability in BASE_CAPABILITIES)

    @property
    def passed_all(self) -> bool:
        """Check if all tested capabilities passed."""
        return all(r.passed for r in self.results)

    @property
    def conformance_level(self) -> str:
        """Get conformance level string."""
        if self.passed_all:
            return "FULL"
        if self.passed_all_base:
            return "BASE"
        return "PARTIAL"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checkpointer_name": self.checkpointer_name,
            "conformance_level": self.conformance_level,
            "passed_all_base": self.passed_all_base,
            "passed_all": self.passed_all,
            "results": [
                {
                    "capability": r.capability.value,
                    "passed": r.passed,
                    "error": r.error,
                }
                for r in self.results
            ],
            "detected_capabilities": [c.value for c in self.detected_capabilities.capabilities],
        }
