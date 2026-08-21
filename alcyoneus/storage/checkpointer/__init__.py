"""
Checkpointer adapters for agent state persistence in alcyoneus.

This module exposes unified checkpointing interfaces for agent graphs, supporting
in-memory, SQLite, and Postgres-backed persistence.

Exports:
    BaseCheckpointer: Abstract base class for checkpointing implementations.
    InMemoryCheckpointer: In-memory checkpointing for development/testing.
    SqliteCheckpointer: SQLite checkpointing (built-in, no extra deps).
    PgCheckpointer: Postgres+Redis checkpointing (optional, requires extras).

Usage:
    SqliteCheckpointer: Included by default.
    PgCheckpointer requires: pip install alcyoneus[pg_checkpoint]
"""

from .base_checkpointer import BaseCheckpointer
from .in_memory_checkpointer import InMemoryCheckpointer
from .pg_checkpointer import PgCheckpointer
from .session_modes import (
    SessionContinuationMode,
    handle_session_continuation,
    validate_session_continuation,
)
from .sqlite_checkpointer import SqliteCheckpointer


__all__ = [
    "BaseCheckpointer",
    "InMemoryCheckpointer",
    "PgCheckpointer",
    "SessionContinuationMode",
    "SqliteCheckpointer",
    "handle_session_continuation",
    "validate_session_continuation",
]
