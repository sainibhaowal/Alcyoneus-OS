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
"""Interrupt primitive for alcyoneus OS.

Provides the interrupt() function for pausing graph execution and
waiting for human input, similar to LangGraph's interrupt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Interrupt:
    """Represents an interrupt event in the graph.

    When interrupt(value) is called, the graph pauses execution and
    stores this interrupt object. The graph can later be resumed with
    a resume value.
    """

    value: Any
    id: str = field(default_factory=lambda: __import__("uuid").uuid4().hex[:8])
    node: str | None = None

    def __repr__(self) -> str:
        return f"Interrupt(id={self.id}, value={self.value!r})"


class GraphInterrupt(Exception):
    """Exception raised when interrupt() is called.

    This exception is caught by the graph execution engine to pause
    execution. It carries the interrupt value for later resumption.
    """

    def __init__(self, value: Any, interrupt_id: str | None = None):
        self.value = value
        self.interrupt_id = interrupt_id or __import__("uuid").uuid4().hex[:8]
        super().__init__(f"Graph interrupted: {value}")

    def __repr__(self) -> str:
        return f"GraphInterrupt(value={self.value!r}, id={self.interrupt_id})"


def interrupt(value: Any) -> Any:
    """Pause graph execution and wait for human input.

    This function raises a GraphInterrupt exception that is caught by
    the graph execution engine. The graph pauses and can later be
    resumed with a resume value.

    Args:
        value: The value to pass to the interrupt handler. This can be
            any serializable object (string, dict, list, etc.) that
            provides context for the interrupt.

    Returns:
        The resume value when the graph is resumed.

    Raises:
        GraphInterrupt: Always raised to pause execution. The graph
            engine catches this and handles the pause/resume logic.

    Example:
        ```python
        def human_approval_node(state):
            if not state.get("approved"):
                # Pause and wait for human approval
                resume_value = interrupt(
                    {
                        "type": "approval_request",
                        "message": "Please approve this action",
                        "action": state.get("pending_action"),
                    }
                )
                # When resumed, resume_value contains the user's response
                if not resume_value.get("approved"):
                    return {"status": "rejected"}
            return {"status": "approved"}
        ```
    """
    # This function is a runtime primitive - the actual interrupt logic
    # is handled by the graph execution engine in handler_utils.py
    # The engine catches GraphInterrupt and handles pause/resume
    raise GraphInterrupt(value)


# For backward compatibility
def is_interrupt(exception: Exception) -> bool:
    """Check if an exception is a GraphInterrupt."""
    return isinstance(exception, GraphInterrupt)


def get_interrupt_value(exception: Exception) -> Any:
    """Extract the interrupt value from a GraphInterrupt exception."""
    if isinstance(exception, GraphInterrupt):
        return exception.value
    return None


__all__ = [
    "GraphInterrupt",
    "Interrupt",
    "get_interrupt_value",
    "interrupt",
    "is_interrupt",
]
