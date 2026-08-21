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
"""Managed values for alcyoneus OS.

Managed values provide access to internal graph execution state
(e.g., remaining steps, whether this is the last step) from within nodes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from alcyoneus.core.state.execution_state import ExecutionState


T = TypeVar("T")


class ManagedValue(ABC, Generic[T]):
    """Abstract base class for managed values.

    Managed values provide read-only access to internal execution state
    from within graph nodes. They are automatically populated by the graph
    runtime before node execution.
    """

    @staticmethod
    @abstractmethod
    def get(execution_state: ExecutionState, config: dict[str, Any] | None = None) -> T:
        """Get the managed value from the execution state.

        Args:
            execution_state: The current execution state.
            config: Optional configuration dictionary (may contain recursion_limit).

        Returns:
            The managed value.
        """
        raise NotImplementedError


class IsLastStep(ManagedValue[bool]):
    """Managed value indicating whether the current step is the last step.

    Returns True if the graph has reached the maximum number of steps
    (recursion limit) and will stop after this step.
    """

    @staticmethod
    def get(execution_state: ExecutionState, config: dict[str, Any] | None = None) -> bool:
        """Check if this is the last step.

        Args:
            execution_state: The current execution state.
            config: Optional configuration with recursion_limit.

        Returns:
            True if this is the last step, False otherwise.
        """
        max_steps = config.get("recursion_limit", 25) if config else 25
        return execution_state.step >= max_steps - 1


class RemainingSteps(ManagedValue[int]):
    """Managed value indicating the number of remaining steps.

    Returns the number of steps remaining before the graph hits the
    recursion limit and stops.
    """

    @staticmethod
    def get(execution_state: ExecutionState, config: dict[str, Any] | None = None) -> int:
        """Get the number of remaining steps.

        Args:
            execution_state: The current execution state.
            config: Optional configuration with recursion_limit.

        Returns:
            Number of remaining steps, or a large number if no limit.
        """
        max_steps = config.get("recursion_limit", 25) if config else 25
        remaining = max_steps - execution_state.step
        return max(0, remaining)


class WritableManagedValue(ManagedValue[T]):
    """Managed value that can be written to by nodes.

    Unlike regular ManagedValue which is read-only, WritableManagedValue
    allows nodes to update the value, which will be persisted in the
    execution state.
    """

    def __init__(self, key: str, default: T):
        """Initialize a writable managed value.

        Args:
            key: The key to store the value under in execution state.
            default: Default value if not set.
        """
        self._key = key
        self._default = default

    @staticmethod
    def get(execution_state: ExecutionState, config: dict[str, Any] | None = None) -> Any:
        """Not used for writable - use instance methods get_value/set_value."""
        raise NotImplementedError("Use instance methods get_value/set_value")

    def get_value(self, execution_state: ExecutionState) -> T:
        """Get the value from execution state.

        Args:
            execution_state: The current execution state.

        Returns:
            The stored value or default.
        """
        if not hasattr(execution_state, "_managed_values"):
            return self._default
        return getattr(execution_state._managed_values, self._key, self._default)

    def set_value(self, execution_state: ExecutionState, value: T) -> None:
        """Set the value in execution state.

        Args:
            execution_state: The current execution state.
            value: The value to store.
        """
        if not hasattr(execution_state, "_managed_values"):
            from types import SimpleNamespace

            execution_state._managed_values = SimpleNamespace()
        setattr(execution_state._managed_values, self._key, value)


# Predefined managed value instances
IS_LAST_STEP = IsLastStep()
REMAINING_STEPS = RemainingSteps()


def is_managed_value(obj: Any) -> bool:
    """Check if an object is a ManagedValue instance.

    Args:
        obj: Object to check.

    Returns:
        True if obj is a ManagedValue subclass or instance.
    """
    return isinstance(obj, type) and issubclass(obj, ManagedValue)


def get_managed_value(
    obj: Any, execution_state: ExecutionState, config: dict[str, Any] | None = None
) -> Any:
    """Get a managed value from an object and execution state.

    Args:
        obj: A ManagedValue class or instance.
        execution_state: The current execution state.
        config: Optional configuration dictionary.

    Returns:
        The managed value.
    """
    if isinstance(obj, type) and issubclass(obj, ManagedValue):
        return obj.get(execution_state, config)
    if isinstance(obj, ManagedValue):
        return obj.get(execution_state, config)
    raise TypeError(f"Expected ManagedValue, got {type(obj)}")


__all__ = [
    "IS_LAST_STEP",
    "REMAINING_STEPS",
    "IsLastStep",
    "ManagedValue",
    "RemainingSteps",
    "WritableManagedValue",
    "get_managed_value",
    "is_managed_value",
]
