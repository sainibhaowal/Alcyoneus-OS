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

"""Tool-level guardrails for Alcyoneus OS.

Tool guardrails run before (input) or after (output) a tool function is
invoked. They support three behaviors:

- **allow**: Let the tool execute normally (default).
- **reject_content**: Reject the tool call/output but continue execution
  with a rejection message sent back to the model.
- **raise_exception**: Halt execution immediately by raising a
  ``ToolInputGuardrailTripwireTriggered`` or
  ``ToolOutputGuardrailTripwireTriggered`` exception.

Usage::

    from alcyoneus.core.guardrails import (
        ToolInputGuardrail,
        ToolGuardrailFunctionOutput,
        tool_input_guardrail,
        tool_output_guardrail,
    )


    @tool_input_guardrail
    async def block_dangerous_args(data):
        if "rm -rf" in str(data.context.tool_input):
            return ToolGuardrailFunctionOutput.raise_exception(
                output_info={"reason": "dangerous command"}
            )
        return ToolGuardrailFunctionOutput.allow()
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar, overload

from .exceptions import (
    ToolInputGuardrailTripwireTriggered,
    ToolOutputGuardrailTripwireTriggered,
)


TContext_co = TypeVar("TContext_co", bound=Any, covariant=True)
MaybeAwaitable = Any


# ---------------------------------------------------------------------------
# Behavior types (typed dicts for behavior specification)
# ---------------------------------------------------------------------------


class AllowBehavior:
    """Allows normal tool execution to continue."""

    type: Literal["allow"] = "allow"

    def __init__(self) -> None:
        self.type = "allow"

    def __repr__(self) -> str:
        return "AllowBehavior()"


class RejectContentBehavior:
    """Rejects the tool call/output but continues execution with a message."""

    type: Literal["reject_content"] = "reject_content"

    def __init__(self, message: str) -> None:
        self.type = "reject_content"
        self.message = message

    def __repr__(self) -> str:
        return f"RejectContentBehavior(message={self.message!r})"


class RaiseExceptionBehavior:
    """Raises an exception to halt execution."""

    type: Literal["raise_exception"] = "raise_exception"

    def __init__(self) -> None:
        self.type = "raise_exception"

    def __repr__(self) -> str:
        return "RaiseExceptionBehavior()"


# Union type for behavior
GuardrailBehavior = AllowBehavior | RejectContentBehavior | RaiseExceptionBehavior


@dataclass
class ToolGuardrailFunctionOutput:
    """The output of a tool guardrail function.

    Attributes:
        output_info: Optional data about checks performed (scores, flags, etc.).
        behavior: How the system should respond — allow, reject_content, or raise_exception.
    """

    output_info: Any
    """Optional information about the guardrail's output."""

    behavior: GuardrailBehavior = field(default_factory=AllowBehavior)
    """Defines how the system responds:
    - allow: Let tool execution continue normally (default)
    - reject_content: Reject but continue execution with a message to the model
    - raise_exception: Halt execution by raising a tripwire exception
    """

    @classmethod
    def allow(cls, output_info: Any = None) -> ToolGuardrailFunctionOutput:
        """Create output that allows the tool execution to continue normally.

        Args:
            output_info: Optional data about checks performed.
        """
        return cls(output_info=output_info, behavior=AllowBehavior())

    @classmethod
    def reject_content(cls, message: str, output_info: Any = None) -> ToolGuardrailFunctionOutput:
        """Create output that rejects the tool call but continues execution.

        Args:
            message: Message to send to the model instead of the tool result.
            output_info: Optional data about checks performed.
        """
        return cls(
            output_info=output_info,
            behavior=RejectContentBehavior(message=message),
        )

    @classmethod
    def raise_exception(cls, output_info: Any = None) -> ToolGuardrailFunctionOutput:
        """Create output that raises an exception to halt execution.

        Args:
            output_info: Optional data about checks performed.
        """
        return cls(
            output_info=output_info,
            behavior=RaiseExceptionBehavior(),
        )


# ---------------------------------------------------------------------------
# Data wrappers for guardrail functions
# ---------------------------------------------------------------------------


@dataclass
class ToolInputGuardrailData:
    """Input data passed to a tool input guardrail function.

    Attributes:
        context: Tool execution context (tool name, arguments, etc.).
        agent: The agent executing the tool.
    """

    context: Any
    """The tool context containing info about the current tool execution."""

    agent: Any
    """The agent that is executing the tool."""


@dataclass
class ToolOutputGuardrailData(ToolInputGuardrailData):
    """Data passed to a tool output guardrail function.

    Extends input data with the tool's output.

    Attributes:
        output: The output produced by the tool function.
    """

    output: Any = None
    """The output produced by the tool function."""


# ---------------------------------------------------------------------------
# Result wrappers
# ---------------------------------------------------------------------------


@dataclass
class ToolInputGuardrailResult:
    """The result of a tool input guardrail run.

    Attributes:
        guardrail: The guardrail instance that was run.
        output: The guardrail function's output.
    """

    guardrail: ToolInputGuardrail[Any]
    """The guardrail that was run."""

    output: ToolGuardrailFunctionOutput
    """The output of the guardrail function."""


@dataclass
class ToolOutputGuardrailResult:
    """The result of a tool output guardrail run.

    Attributes:
        guardrail: The guardrail instance that was run.
        output: The guardrail function's output.
    """

    guardrail: ToolOutputGuardrail[Any]
    """The guardrail that was run."""

    output: ToolGuardrailFunctionOutput
    """The output of the guardrail function."""


# ---------------------------------------------------------------------------
# Guardrail classes
# ---------------------------------------------------------------------------


@dataclass
class ToolInputGuardrail(Generic[TContext_co]):
    """A guardrail that runs before a tool function is invoked.

    Validates tool input arguments and can allow, reject, or halt execution.

    Attributes:
        guardrail_function: Callable accepting ``ToolInputGuardrailData``
            and returning ``ToolGuardrailFunctionOutput``.
        name: Optional name for tracing/debugging.
    """

    guardrail_function: Callable[..., MaybeAwaitable]
    """The function that implements the guardrail logic."""

    name: str | None = None
    """Optional name. Falls back to function name."""

    def get_name(self) -> str:
        """Return the guardrail name."""
        return self.name or getattr(
            self.guardrail_function, "__name__", "unnamed_tool_input_guardrail"
        )

    async def run(self, data: ToolInputGuardrailData) -> ToolInputGuardrailResult:
        """Execute the guardrail function.

        Args:
            data: The tool input guardrail data.

        Returns:
            ToolInputGuardrailResult with the guardrail output.
        """
        if not callable(self.guardrail_function):
            raise TypeError(
                f"Guardrail function must be callable, got {type(self.guardrail_function)}"
            )

        result = self.guardrail_function(data)
        if inspect.isawaitable(result):
            result = await result

        return ToolInputGuardrailResult(guardrail=self, output=result)


@dataclass
class ToolOutputGuardrail(Generic[TContext_co]):
    """A guardrail that runs after a tool function is invoked.

    Validates tool output and can allow, reject, or halt execution.

    Attributes:
        guardrail_function: Callable accepting ``ToolOutputGuardrailData``
            and returning ``ToolGuardrailFunctionOutput``.
        name: Optional name for tracing/debugging.
    """

    guardrail_function: Callable[..., MaybeAwaitable]
    """The function that implements the guardrail logic."""

    name: str | None = None
    """Optional name. Falls back to function name."""

    def get_name(self) -> str:
        """Return the guardrail name."""
        return self.name or getattr(
            self.guardrail_function, "__name__", "unnamed_tool_output_guardrail"
        )

    async def run(self, data: ToolOutputGuardrailData) -> ToolOutputGuardrailResult:
        """Execute the guardrail function.

        Args:
            data: The tool output guardrail data.

        Returns:
            ToolOutputGuardrailResult with the guardrail output.
        """
        if not callable(self.guardrail_function):
            raise TypeError(
                f"Guardrail function must be callable, got {type(self.guardrail_function)}"
            )

        result = self.guardrail_function(data)
        if inspect.isawaitable(result):
            result = await result

        return ToolOutputGuardrailResult(guardrail=self, output=result)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

_ToolInputFuncSync = Callable[[ToolInputGuardrailData], ToolGuardrailFunctionOutput]
_ToolInputFuncAsync = Callable[[ToolInputGuardrailData], Awaitable[ToolGuardrailFunctionOutput]]


@overload
def tool_input_guardrail(func: _ToolInputFuncSync) -> ToolInputGuardrail[Any]: ...


@overload
def tool_input_guardrail(func: _ToolInputFuncAsync) -> ToolInputGuardrail[Any]: ...


@overload
def tool_input_guardrail(
    *,
    name: str | None = None,
) -> Callable[[_ToolInputFuncSync | _ToolInputFuncAsync], ToolInputGuardrail[Any]]: ...


def tool_input_guardrail(
    func: _ToolInputFuncSync | _ToolInputFuncAsync | None = None,
    *,
    name: str | None = None,
) -> (
    ToolInputGuardrail[Any]
    | Callable[[_ToolInputFuncSync | _ToolInputFuncAsync], ToolInputGuardrail[Any]]
):
    """Decorator to create a ``ToolInputGuardrail`` from a function.

    The decorated function must accept ``ToolInputGuardrailData``
    and return a ``ToolGuardrailFunctionOutput``.
    """

    def decorator(
        f: _ToolInputFuncSync | _ToolInputFuncAsync,
    ) -> ToolInputGuardrail[Any]:
        return ToolInputGuardrail(guardrail_function=f, name=name or getattr(f, "__name__", None))

    if func is not None:
        return decorator(func)
    return decorator


_ToolOutputFuncSync = Callable[[ToolOutputGuardrailData], ToolGuardrailFunctionOutput]
_ToolOutputFuncAsync = Callable[[ToolOutputGuardrailData], Awaitable[ToolGuardrailFunctionOutput]]


@overload
def tool_output_guardrail(func: _ToolOutputFuncSync) -> ToolOutputGuardrail[Any]: ...


@overload
def tool_output_guardrail(func: _ToolOutputFuncAsync) -> ToolOutputGuardrail[Any]: ...


@overload
def tool_output_guardrail(
    *,
    name: str | None = None,
) -> Callable[[_ToolOutputFuncSync | _ToolOutputFuncAsync], ToolOutputGuardrail[Any]]: ...


def tool_output_guardrail(
    func: _ToolOutputFuncSync | _ToolOutputFuncAsync | None = None,
    *,
    name: str | None = None,
) -> (
    ToolOutputGuardrail[Any]
    | Callable[[_ToolOutputFuncSync | _ToolOutputFuncAsync], ToolOutputGuardrail[Any]]
):
    """Decorator to create a ``ToolOutputGuardrail`` from a function.

    The decorated function must accept ``ToolOutputGuardrailData``
    and return a ``ToolGuardrailFunctionOutput``.
    """

    def decorator(
        f: _ToolOutputFuncSync | _ToolOutputFuncAsync,
    ) -> ToolOutputGuardrail[Any]:
        return ToolOutputGuardrail(guardrail_function=f, name=name or getattr(f, "__name__", None))

    if func is not None:
        return decorator(func)
    return decorator


__all__ = [
    "AllowBehavior",
    "GuardrailBehavior",
    "RaiseExceptionBehavior",
    "RejectContentBehavior",
    "ToolGuardrailFunctionOutput",
    "ToolInputGuardrail",
    "ToolInputGuardrailData",
    "ToolInputGuardrailResult",
    "ToolInputGuardrailTripwireTriggered",
    "ToolOutputGuardrail",
    "ToolOutputGuardrailData",
    "ToolOutputGuardrailResult",
    "ToolOutputGuardrailTripwireTriggered",
    "tool_input_guardrail",
    "tool_output_guardrail",
]
