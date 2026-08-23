"""
Message tombstone primitives for state manipulation.

LangGraph-style message removal sentinels. A ``RemoveMessage`` is not a real
message; it is a directive consumed by :func:`alcyoneus.core.state.add_messages`
(and other message reducers) telling it to delete a message with a specific id
from the conversation history.

Two flavours are provided:

- ``RemoveMessage(message_id=...)`` -- removes a single message by id.
- ``REMOVE_ALL_MESSAGES`` -- a singleton sentinel that removes every message.

Example:
    >>> from alcyoneus.core.state import RemoveMessage, REMOVE_ALL_MESSAGES, add_messages
    >>> msgs = [
    ...     Message.text_message("hello", message_id="a"),
    ...     Message.text_message("world", message_id="b"),
    ... ]
    >>> add_messages(msgs, [RemoveMessage(message_id="a")])
    [Message(message_id='b', ...)]
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RemoveMessage(BaseModel):
    """A tombstone directive that removes a message with the given id.

    Attributes:
        message_id (str | int): The id of the message to remove.

    Example:
        >>> RemoveMessage(message_id="abc123")
    """

    model_config = {"frozen": True}

    kind: str = "remove_message"
    message_id: str | int

    @classmethod
    def of(cls, message_id: str | int) -> RemoveMessage:
        """Create a RemoveMessage tombstone for the given message id."""
        return cls(message_id=message_id)


class _RemoveAllMessages(BaseModel):
    """Singleton sentinel that removes the entire message history."""

    model_config = {"frozen": True}

    kind: str = "remove_all_messages"
    message_id: str | int = "*"


REMOVE_ALL_MESSAGES = _RemoveAllMessages()


def is_remove_message(value: Any) -> bool:
    """Return True if *value* is a RemoveMessage tombstone.

    Args:
        value: The value to check.

    Returns:
        bool: True if the value is a RemoveMessage or REMOVE_ALL_MESSAGES.
    """
    return isinstance(value, (RemoveMessage, _RemoveAllMessages)) or (
        isinstance(value, dict) and value.get("kind") in ("remove_message", "remove_all_messages")
    )


def is_remove_all_messages(value: Any) -> bool:
    """Return True if *value* is the REMOVE_ALL_MESSAGES sentinel.

    Args:
        value: The value to check.

    Returns:
        bool: True if the value is the remove-all sentinel.
    """
    return isinstance(value, _RemoveAllMessages) or (
        isinstance(value, dict) and value.get("kind") == "remove_all_messages"
    )


def message_to_remove_id(value: Any) -> str | int | None:
    """Extract the target message id from a RemoveMessage value.

    Returns ``None`` for the remove-all sentinel or for non-tombstone values.

    Args:
        value: The value to inspect.

    Returns:
        str | int | None: The message id to remove, or None.
    """
    if isinstance(value, RemoveMessage):
        return value.message_id
    if isinstance(value, dict) and value.get("kind") == "remove_message":
        return value.get("message_id")
    return None


__all__ = [
    "REMOVE_ALL_MESSAGES",
    "RemoveMessage",
    "is_remove_all_messages",
    "is_remove_message",
    "message_to_remove_id",
]
