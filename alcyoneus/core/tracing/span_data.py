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

"""Span data classes for Alcyoneus OS tracing.

Defines typed span payload data structures for each component in an agent execution:
Agent spans, Task spans, Turn spans, Function spans, Generation spans,
Guardrail spans, Handoff spans, and Custom spans.
"""

from __future__ import annotations

import abc
from typing import Any


class SpanData(abc.ABC):
    """Abstract base class for all tracing span data objects."""

    @property
    @abc.abstractmethod
    def type(self) -> str:
        """Return the string identifier for this span type."""

    @abc.abstractmethod
    def export(self) -> dict[str, Any]:
        """Export the span data as a JSON-serializable dictionary."""


class AgentSpanData(SpanData):
    """Data for an agent execution span."""

    __slots__ = ("handoffs", "metadata", "name", "output_type", "tools")

    def __init__(
        self,
        name: str,
        handoffs: list[str] | None = None,
        tools: list[str] | None = None,
        output_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.handoffs = handoffs
        self.tools = tools
        self.output_type = output_type
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "agent"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "handoffs": self.handoffs,
            "tools": self.tools,
            "output_type": self.output_type,
            "metadata": self.metadata,
        }


class TaskSpanData(SpanData):
    """Data for a top-level task/runner execution span."""

    __slots__ = ("metadata", "name", "usage")

    def __init__(
        self,
        name: str,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.usage = usage or {}
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "task"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "usage": self.usage,
            "metadata": self.metadata,
        }


class TurnSpanData(SpanData):
    """Data for a single turn in an agent conversation."""

    __slots__ = ("agent_name", "metadata", "turn_index")

    def __init__(
        self,
        turn_index: int,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.turn_index = turn_index
        self.agent_name = agent_name
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "turn"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "turn_index": self.turn_index,
            "agent_name": self.agent_name,
            "metadata": self.metadata,
        }


class FunctionSpanData(SpanData):
    """Data for a tool function call span."""

    __slots__ = ("error", "inputs", "metadata", "name", "output")

    def __init__(
        self,
        name: str,
        inputs: dict[str, Any] | None = None,
        output: Any = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.inputs = inputs or {}
        self.output = output
        self.error = error
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "function"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "inputs": self.inputs,
            "output": str(self.output) if self.output is not None else None,
            "error": self.error,
            "metadata": self.metadata,
        }


class GenerationSpanData(SpanData):
    """Data for an LLM model generation span."""

    __slots__ = ("completion", "metadata", "model", "prompt", "provider", "usage")

    def __init__(
        self,
        model: str,
        provider: str | None = None,
        prompt: Any = None,
        completion: Any = None,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.prompt = prompt
        self.completion = completion
        self.usage = usage or {}
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "generation"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "metadata": self.metadata,
        }


class GuardrailSpanData(SpanData):
    """Data for a guardrail validation check span."""

    __slots__ = ("guardrail_name", "guardrail_type", "info", "metadata", "triggered")

    def __init__(
        self,
        guardrail_name: str,
        guardrail_type: str = "input",
        triggered: bool = False,
        info: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.guardrail_name = guardrail_name
        self.guardrail_type = guardrail_type
        self.triggered = triggered
        self.info = info
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "guardrail"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "guardrail_name": self.guardrail_name,
            "guardrail_type": self.guardrail_type,
            "triggered": self.triggered,
            "info": self.info,
            "metadata": self.metadata,
        }


class HandoffSpanData(SpanData):
    """Data for an agent-to-agent handoff span."""

    __slots__ = ("from_agent", "metadata", "reason", "to_agent")

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.reason = reason
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "handoff"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "reason": self.reason,
            "metadata": self.metadata,
        }


class CustomSpanData(SpanData):
    """Data for a user-defined custom span."""

    __slots__ = ("data", "metadata", "name")

    def __init__(
        self,
        name: str,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.data = data or {}
        self.metadata = metadata or {}

    @property
    def type(self) -> str:
        return "custom"

    def export(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "data": self.data,
            "metadata": self.metadata,
        }


__all__ = [
    "AgentSpanData",
    "CustomSpanData",
    "FunctionSpanData",
    "GenerationSpanData",
    "GuardrailSpanData",
    "HandoffSpanData",
    "SpanData",
    "TaskSpanData",
    "TurnSpanData",
]
