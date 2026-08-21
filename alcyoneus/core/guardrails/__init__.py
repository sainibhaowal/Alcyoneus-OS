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

"""Guardrails system for Alcyoneus OS.

Provides input, output, and tool-level guardrails that validate agent behaviour
at every stage of execution. Guardrails can halt execution immediately via
tripwire mechanisms when safety constraints are violated.

Three levels of guardrails:

- **Input guardrails**: Validate input before/during agent processing.
- **Output guardrails**: Validate agent output after execution.
- **Tool guardrails**: Validate tool arguments (input) and results (output).
"""

from .exceptions import (
    GuardrailTripwireTriggered,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    ToolInputGuardrailTripwireTriggered,
    ToolOutputGuardrailTripwireTriggered,
)
from .input_guardrail import (
    GuardrailFunctionOutput,
    InputGuardrail,
    InputGuardrailResult,
    input_guardrail,
)
from .output_guardrail import (
    OutputGuardrail,
    OutputGuardrailResult,
    output_guardrail,
)
from .tool_guardrails import (
    AllowBehavior,
    GuardrailBehavior,
    RaiseExceptionBehavior,
    RejectContentBehavior,
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
    ToolInputGuardrailResult,
    ToolOutputGuardrail,
    ToolOutputGuardrailData,
    ToolOutputGuardrailResult,
    tool_input_guardrail,
    tool_output_guardrail,
)


__all__ = [
    # Exceptions
    "GuardrailTripwireTriggered",
    "InputGuardrailTripwireTriggered",
    "OutputGuardrailTripwireTriggered",
    "ToolInputGuardrailTripwireTriggered",
    "ToolOutputGuardrailTripwireTriggered",
    # Input guardrails
    "GuardrailFunctionOutput",
    "InputGuardrail",
    "InputGuardrailResult",
    "input_guardrail",
    # Output guardrails
    "OutputGuardrail",
    "OutputGuardrailResult",
    "output_guardrail",
    # Tool guardrails
    "AllowBehavior",
    "GuardrailBehavior",
    "RaiseExceptionBehavior",
    "RejectContentBehavior",
    "ToolGuardrailFunctionOutput",
    "ToolInputGuardrail",
    "ToolInputGuardrailData",
    "ToolInputGuardrailResult",
    "ToolOutputGuardrail",
    "ToolOutputGuardrailData",
    "ToolOutputGuardrailResult",
    "tool_input_guardrail",
    "tool_output_guardrail",
]
