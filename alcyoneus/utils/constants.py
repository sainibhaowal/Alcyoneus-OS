"""
Constants and enums for TAF agent graph execution and messaging.

This module defines special node names, message storage levels, execution states,
and response granularity options for agent workflows.
"""

from enum import Enum
from typing import Literal


# Special node names for graph execution flow
START: Literal["__start__"] = "__start__"
END: Literal["__end__"] = "__end__"


class ExecutionState(str, Enum):
    """
    Graph execution states for agent workflows.

    Values:
        RUNNING: Execution is in progress.
        PAUSED: Execution is paused.
        COMPLETED: Execution completed successfully.
        ERROR: Execution encountered an error.
        INTERRUPTED: Execution was interrupted.
        ABORTED: Execution was aborted.
        IDLE: Execution is idle.
    """

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    ABORTED = "aborted"
    IDLE = "idle"


class ResponseGranularity(str, Enum):
    """
    Response granularity options for agent graph outputs.

    Values:
        FULL: State, latest messages.
        PARTIAL: Context, summary, latest messages.
        LOW: Only latest messages.
    """

    FULL = "full"
    PARTIAL = "partial"
    LOW = "low"
