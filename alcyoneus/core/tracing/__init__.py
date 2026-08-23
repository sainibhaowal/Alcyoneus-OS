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

"""Observability and Tracing System for Alcyoneus OS.

Provides native span and trace tracking for Agent execution, LLM generations,
tool calls, guardrails, handoffs, and custom spans with pluggable processors.
"""

from .context import (
    gen_span_id,
    gen_trace_id,
    get_current_span,
    get_current_trace,
    is_tracing_disabled,
    set_current_span,
    set_current_trace,
    set_tracing_disabled,
)
from .decorators import (
    agent_span,
    custom_span,
    function_span,
    generation_span,
    guardrail_span,
    handoff_span,
    span,
    task_span,
    trace,
    turn_span,
)
from .processors import (
    ConsoleTracingProcessor,
    TracingProcessor,
    add_trace_processor,
    flush_traces,
    get_trace_processors,
    set_trace_processors,
)
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
from .spans import Span, SpanError
from .traces import Trace


__all__ = [
    # Data classes
    "AgentSpanData",
    "ConsoleTracingProcessor",
    "CustomSpanData",
    "FunctionSpanData",
    "GenerationSpanData",
    "GuardrailSpanData",
    "HandoffSpanData",
    # Main classes
    "Span",
    "SpanData",
    "SpanError",
    "TaskSpanData",
    "Trace",
    "TracingProcessor",
    "TurnSpanData",
    # Functions and Decorators
    "add_trace_processor",
    "agent_span",
    "custom_span",
    "flush_traces",
    "function_span",
    "gen_span_id",
    "gen_trace_id",
    "generation_span",
    "get_current_span",
    "get_current_trace",
    "get_trace_processors",
    "guardrail_span",
    "handoff_span",
    "is_tracing_disabled",
    "set_current_span",
    "set_current_trace",
    "set_trace_processors",
    "set_tracing_disabled",
    "span",
    "task_span",
    "trace",
    "turn_span",
]
