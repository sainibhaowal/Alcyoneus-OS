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

"""Compaction capability for sandbox session state compaction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompactionCapability:
    """Compaction capability configuration for sandbox session state.

    Allows sandbox to compact long-running session state by removing
    old messages, compressing context, etc.
    """

    enabled: bool = True
    max_messages: int = 1000
    max_context_bytes: int = 1_000_000
    strategy: str = "keep_recent"  # keep_recent | summarize | custom
    trigger_on_threshold: float = 0.8  # trigger at 80% capacity


@dataclass
class DynamicCompactionCapability(CompactionCapability):
    """Dynamic compaction capability that adapts based on usage patterns.

    Automatically adjusts thresholds based on observed session behavior.
    """

    adaptive_threshold: bool = True
    growth_factor: float = 1.5
    min_messages: int = 50
    min_context_bytes: int = 50_000


@dataclass
class ResponsesCompactionCapability:
    """Compaction capability following OpenAI Responses API semantics.

    Matches the OpenAI Responses API session compaction behavior.
    """

    enabled: bool = True
    max_input_tokens: int = 128_000
    include_last_n_messages: int = 10
    summary_instructions: str | None = None


__all__ = [
    "CompactionCapability",
    "DynamicCompactionCapability",
    "ResponsesCompactionCapability",
]
