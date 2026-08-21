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

"""Input guardrails for Alcyoneus OS.

Input guardrails are checks that run in parallel with the agent or before it
starts. They validate input messages and can halt execution immediately when
a tripwire condition is detected (e.g., off-topic input, prompt injection,
unsafe content).

Usage::

    from alcyoneus.core.guardrails import (
        InputGuardrail,
        GuardrailFunctionOutput,
        input_guardrail,
    )


    # Decorator style
    @input_guardrail
    async def check_off_topic(context, agent, input_data):
        is_off_topic = await classify(input_data)
        return GuardrailFunctionOutput(
            output_info={"off_topic": is_off_topic},
            tripwire_triggered=is_off_topic,
        )


    # Manual style
    guardrail = InputGuardrail(
        guardrail_function=my_check_fn,
        name="content_safety",
        run_in_parallel=True,
    )
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, overload

from .exceptions import InputGuardrailTripwireTriggered


# Type variable for the context type (mirrors the graph state or run context)
TContext = TypeVar("TContext")
TContext_co = TypeVar("TContext_co", bound=Any, covariant=True)

# MaybeAwaitable helper
MaybeAwaitable = Any  # Union[T, Awaitable[T]] — simplified for broad compat


@dataclass
class GuardrailFunctionOutput:
    """The output of a guardrail function.

    Attributes:
        output_info: Optional data about the checks performed. For example,
            the guardrail could include info about each check and granular
            results for debugging.
        tripwire_triggered: Whether the tripwire was triggered. If True,
            the agent's execution will be halted immediately with an
            ``InputGuardrailTripwireTriggered`` or
            ``OutputGuardrailTripwireTriggered`` exception.
    """

    output_info: Any
    """Optional information about the guardrail's output (scores, flags, etc.)."""

    tripwire_triggered: bool
    """If True, the agent's execution is halted immediately."""


@dataclass
class InputGuardrailResult:
    """The result of running an input guardrail.

    Attributes:
        guardrail: The guardrail instance that was run.
        output: The output from the guardrail function.
    """

    guardrail: InputGuardrail[Any]
    """The guardrail that was run."""

    output: GuardrailFunctionOutput
    """The output of the guardrail function."""


@dataclass
class InputGuardrail(Generic[TContext]):
    """Input guardrails validate agent input before or during processing.

    They can run in parallel with the agent (default) or sequentially before
    the agent starts. When ``tripwire_triggered`` is True in the output,
    an ``InputGuardrailTripwireTriggered`` exception is raised immediately.

    Attributes:
        guardrail_function: A callable that receives ``(context, agent, input)``
            and returns a ``GuardrailFunctionOutput``. Can be sync or async.
        name: Optional human-readable name for tracing/debugging.
        run_in_parallel: If True (default), runs concurrently with the agent.
            If False, runs before the agent starts.
    """

    guardrail_function: Callable[..., MaybeAwaitable]
    """Function receiving (context, agent, input) → GuardrailFunctionOutput."""

    name: str | None = None
    """Human-readable name for tracing. Falls back to function name."""

    run_in_parallel: bool = True
    """Whether to run concurrently with the agent (True) or before it (False)."""

    def get_name(self) -> str:
        """Return the guardrail name, falling back to function name."""
        if self.name:
            return self.name
        return getattr(self.guardrail_function, "__name__", "unnamed_guardrail")

    async def run(
        self,
        agent: Any,
        input_data: Any,
        context: Any = None,
    ) -> InputGuardrailResult:
        """Execute the guardrail function.

        Args:
            agent: The agent being guarded.
            input_data: The input messages/data to validate.
            context: Optional run context.

        Returns:
            InputGuardrailResult containing the guardrail output.

        Raises:
            TypeError: If guardrail_function is not callable.
        """
        if not callable(self.guardrail_function):
            raise TypeError(
                f"Guardrail function must be callable, got {type(self.guardrail_function)}"
            )

        output = self.guardrail_function(context, agent, input_data)
        if inspect.isawaitable(output):
            output = await output

        return InputGuardrailResult(guardrail=self, output=output)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

_InputGuardrailFuncSync = Callable[..., GuardrailFunctionOutput]
_InputGuardrailFuncAsync = Callable[..., Awaitable[GuardrailFunctionOutput]]


@overload
def input_guardrail(func: _InputGuardrailFuncSync) -> InputGuardrail[Any]: ...


@overload
def input_guardrail(func: _InputGuardrailFuncAsync) -> InputGuardrail[Any]: ...


@overload
def input_guardrail(
    *,
    name: str | None = None,
    run_in_parallel: bool = True,
) -> Callable[[_InputGuardrailFuncSync | _InputGuardrailFuncAsync], InputGuardrail[Any]]: ...


def input_guardrail(
    func: _InputGuardrailFuncSync | _InputGuardrailFuncAsync | None = None,
    *,
    name: str | None = None,
    run_in_parallel: bool = True,
) -> (
    InputGuardrail[Any]
    | Callable[[_InputGuardrailFuncSync | _InputGuardrailFuncAsync], InputGuardrail[Any]]
):
    """Decorator to create an ``InputGuardrail`` from a function.

    Can be used bare (``@input_guardrail``) or with arguments
    (``@input_guardrail(name="safety", run_in_parallel=False)``).

    The decorated function must accept ``(context, agent, input)``
    and return a ``GuardrailFunctionOutput``.
    """

    def decorator(
        f: _InputGuardrailFuncSync | _InputGuardrailFuncAsync,
    ) -> InputGuardrail[Any]:
        return InputGuardrail(
            guardrail_function=f,
            name=name or getattr(f, "__name__", None),
            run_in_parallel=run_in_parallel,
        )

    if func is not None:
        return decorator(func)
    return decorator


__all__ = [
    "GuardrailFunctionOutput",
    "InputGuardrail",
    "InputGuardrailResult",
    "InputGuardrailTripwireTriggered",
    "input_guardrail",
]
