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

"""Guardrail exceptions for Alcyoneus OS.

These exceptions are raised when guardrail tripwires are triggered,
immediately halting agent execution to enforce safety constraints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .input_guardrail import InputGuardrailResult
    from .output_guardrail import OutputGuardrailResult
    from .tool_guardrails import ToolInputGuardrailResult, ToolOutputGuardrailResult


class GuardrailTripwireTriggered(Exception):
    """Base exception for all guardrail tripwire violations."""

    def __init__(self, message: str = "Guardrail tripwire triggered") -> None:
        super().__init__(message)


class InputGuardrailTripwireTriggered(GuardrailTripwireTriggered):
    """Raised when an input guardrail's tripwire is triggered.

    This immediately halts the agent's execution, preventing unsafe
    input from being processed.

    Attributes:
        guardrail_result: The full result from the guardrail check that triggered.
    """

    guardrail_result: InputGuardrailResult

    def __init__(self, guardrail_result: InputGuardrailResult) -> None:
        self.guardrail_result = guardrail_result
        guardrail_name = guardrail_result.guardrail.get_name()
        super().__init__(
            f"Input guardrail tripwire triggered by '{guardrail_name}'. "
            f"Info: {guardrail_result.output.output_info}"
        )


class OutputGuardrailTripwireTriggered(GuardrailTripwireTriggered):
    """Raised when an output guardrail's tripwire is triggered.

    This halts the agent after it has produced output that fails
    validation or safety checks.

    Attributes:
        guardrail_result: The full result from the guardrail check that triggered.
    """

    guardrail_result: OutputGuardrailResult

    def __init__(self, guardrail_result: OutputGuardrailResult) -> None:
        self.guardrail_result = guardrail_result
        guardrail_name = guardrail_result.guardrail.get_name()
        super().__init__(
            f"Output guardrail tripwire triggered by '{guardrail_name}'. "
            f"Info: {guardrail_result.output.output_info}"
        )


class ToolInputGuardrailTripwireTriggered(GuardrailTripwireTriggered):
    """Raised when a tool input guardrail triggers a raise_exception behavior.

    Attributes:
        guardrail_result: The full result from the tool guardrail check.
    """

    guardrail_result: ToolInputGuardrailResult

    def __init__(self, guardrail_result: ToolInputGuardrailResult) -> None:
        self.guardrail_result = guardrail_result
        guardrail_name = guardrail_result.guardrail.get_name()
        super().__init__(
            f"Tool input guardrail tripwire triggered by '{guardrail_name}'. "
            f"Info: {guardrail_result.output.output_info}"
        )


class ToolOutputGuardrailTripwireTriggered(GuardrailTripwireTriggered):
    """Raised when a tool output guardrail triggers a raise_exception behavior.

    Attributes:
        guardrail_result: The full result from the tool guardrail check.
    """

    guardrail_result: ToolOutputGuardrailResult

    def __init__(self, guardrail_result: ToolOutputGuardrailResult) -> None:
        self.guardrail_result = guardrail_result
        guardrail_name = guardrail_result.guardrail.get_name()
        super().__init__(
            f"Tool output guardrail tripwire triggered by '{guardrail_name}'. "
            f"Info: {guardrail_result.output.output_info}"
        )


__all__ = [
    "GuardrailTripwireTriggered",
    "InputGuardrailTripwireTriggered",
    "OutputGuardrailTripwireTriggered",
    "ToolInputGuardrailTripwireTriggered",
    "ToolOutputGuardrailTripwireTriggered",
]
