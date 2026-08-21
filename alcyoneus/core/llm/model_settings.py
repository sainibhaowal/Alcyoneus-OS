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

"""ModelSettings dataclass controlling temperature, top_p, reasoning, tool_choice, and truncation."""  # noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ToolChoice = Literal["auto", "required", "none"] | dict[str, Any]
TruncationStrategy = Literal["auto", "disabled", "drop_oldest"]


@dataclass
class ModelSettings:
    """Detailed model settings for generation calls."""

    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    max_tokens: int | None = None
    tool_choice: ToolChoice = "auto"
    truncation: TruncationStrategy = "auto"
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)

    def export(self) -> dict[str, Any]:
        """Export settings as a dictionary for LLM callers."""
        d: dict[str, Any] = {}
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.top_p is not None:
            d["top_p"] = self.top_p
        if self.frequency_penalty is not None:
            d["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            d["presence_penalty"] = self.presence_penalty
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        if self.tool_choice:
            d["tool_choice"] = self.tool_choice
        if self.reasoning_effort:
            d["reasoning_effort"] = self.reasoning_effort
        return {**d, **self.extra_body}


__all__ = [
    "ModelSettings",
    "ToolChoice",
    "TruncationStrategy",
]
