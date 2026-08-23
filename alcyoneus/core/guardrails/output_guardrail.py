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

"""Output guardrails for Alcyoneus OS.

Output guardrails validate the final output of an agent after execution.
When a tripwire is triggered, they raise ``OutputGuardrailTripwireTriggered``
to prevent unsafe or invalid output from being returned.

Usage::

    from alcyoneus.core.guardrails import (
        OutputGuardrail,
        GuardrailFunctionOutput,
        output_guardrail,
    )


    @output_guardrail
    async def check_pii(context, agent, agent_output):
        has_pii = detect_pii(agent_output)
        return GuardrailFunctionOutput(
            output_info={"pii_found": has_pii},
            tripwire_triggered=has_pii,
        )
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, overload

from .exceptions import OutputGuardrailTripwireTriggered
from .input_guardrail import GuardrailFunctionOutput


TContext = TypeVar("TContext")
TContext_co = TypeVar("TContext_co", bound=Any, covariant=True)
MaybeAwaitable = Any


@dataclass
class OutputGuardrailResult:
    """The result of running an output guardrail.

    Attributes:
        guardrail: The guardrail instance that was run.
        agent: The agent whose output was checked.
        agent_output: The raw output from the agent.
        output: The guardrail function's output (scores, flags, etc.).
    """

    guardrail: OutputGuardrail[Any]
    """The guardrail that was run."""

    agent: Any
    """The agent that produced the output."""

    agent_output: Any
    """The agent's raw output that was checked."""

    output: GuardrailFunctionOutput
    """The output of the guardrail function."""


@dataclass
class OutputGuardrail(Generic[TContext]):
    """Output guardrails validate agent output after execution.

    When ``tripwire_triggered`` is True in the output, an
    ``OutputGuardrailTripwireTriggered`` exception is raised.

    Attributes:
        guardrail_function: A callable receiving ``(context, agent, agent_output)``
            and returning a ``GuardrailFunctionOutput``. Can be sync or async.
        name: Optional human-readable name for tracing/debugging.
    """

    guardrail_function: Callable[..., MaybeAwaitable]
    """Function receiving (context, agent, agent_output) → GuardrailFunctionOutput."""

    name: str | None = None
    """Human-readable name for tracing. Falls back to function name."""

    def get_name(self) -> str:
        """Return the guardrail name, falling back to function name."""
        if self.name:
            return self.name
        return getattr(self.guardrail_function, "__name__", "unnamed_guardrail")

    async def run(
        self,
        context: Any,
        agent: Any,
        agent_output: Any,
    ) -> OutputGuardrailResult:
        """Execute the guardrail function against agent output.

        Args:
            context: The run context.
            agent: The agent whose output is being validated.
            agent_output: The agent's output to validate.

        Returns:
            OutputGuardrailResult containing the guardrail output.

        Raises:
            TypeError: If guardrail_function is not callable.
        """
        if not callable(self.guardrail_function):
            raise TypeError(
                f"Guardrail function must be callable, got {type(self.guardrail_function)}"
            )

        output = self.guardrail_function(context, agent, agent_output)
        if inspect.isawaitable(output):
            output = await output

        return OutputGuardrailResult(
            guardrail=self,
            agent=agent,
            agent_output=agent_output,
            output=output,
        )


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

_OutputGuardrailFuncSync = Callable[..., GuardrailFunctionOutput]
_OutputGuardrailFuncAsync = Callable[..., Awaitable[GuardrailFunctionOutput]]


@overload
def output_guardrail(func: _OutputGuardrailFuncSync) -> OutputGuardrail[Any]: ...


@overload
def output_guardrail(func: _OutputGuardrailFuncAsync) -> OutputGuardrail[Any]: ...


@overload
def output_guardrail(
    *,
    name: str | None = None,
) -> Callable[[_OutputGuardrailFuncSync | _OutputGuardrailFuncAsync], OutputGuardrail[Any]]: ...


def output_guardrail(
    func: _OutputGuardrailFuncSync | _OutputGuardrailFuncAsync | None = None,
    *,
    name: str | None = None,
) -> (
    OutputGuardrail[Any]
    | Callable[[_OutputGuardrailFuncSync | _OutputGuardrailFuncAsync], OutputGuardrail[Any]]
):
    """Decorator to create an ``OutputGuardrail`` from a function.

    Can be used bare (``@output_guardrail``) or with arguments
    (``@output_guardrail(name="pii_check")``).

    The decorated function must accept ``(context, agent, agent_output)``
    and return a ``GuardrailFunctionOutput``.
    """

    def decorator(
        f: _OutputGuardrailFuncSync | _OutputGuardrailFuncAsync,
    ) -> OutputGuardrail[Any]:
        return OutputGuardrail(
            guardrail_function=f,
            name=name or getattr(f, "__name__", None),
        )

    if func is not None:
        return decorator(func)
    return decorator


__all__ = [
    "OutputGuardrail",
    "OutputGuardrailResult",
    "OutputGuardrailTripwireTriggered",
    "output_guardrail",
]
