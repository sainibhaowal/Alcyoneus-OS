"""
Reducer utilities for merging and replacing lists and values in agent state.

This module provides generic and message-specific reducers for combining lists,
replacing values, and appending items while avoiding duplicates.

Functions:
    add_messages: Adds messages to a list, avoiding duplicates by message_id.
    replace_messages: Replaces the entire message list.
    append_items: Appends items to a list, avoiding duplicates by id.
    replace_value: Replaces a value with another.
"""

from .message import Message
from .remove_message import REMOVE_ALL_MESSAGES, RemoveMessage, is_remove_message


def _filter_tombstones(
    left: list[Message],
    right: list[Message],
    *,
    replace_all: bool = False,
) -> list[Message]:
    """Apply RemoveMessage / REMOVE_ALL_MESSAGES directives from ``right``.

    Tombstone directives in ``right`` never become part of the resulting list;
    they only instruct which messages in ``left`` (or the combined list) to drop.

    Args:
        left: Existing message list.
        right: Incoming messages/tombstones.
        replace_all: When True, tombstones operate on the combined list instead
            of only ``left``.

    Returns:
        list[Message]: Result list with the tombstone deletions applied.
    """
    if not any(is_remove_message(msg) for msg in right):
        return left

    remove_ids: set[str | int] = set()
    remove_all = False
    for msg in right:
        if is_remove_message(msg):
            if isinstance(msg, RemoveMessage):
                remove_ids.add(msg.message_id)
            elif isinstance(msg, dict):
                remove_ids.add(msg.get("message_id"))  # type: ignore[arg-type]
            else:
                remove_all = True
        if msg is REMOVE_ALL_MESSAGES or (
            isinstance(msg, dict) and msg.get("kind") == "remove_all_messages"
        ):
            remove_all = True

    if remove_all:
        return []

    if replace_all:
        return [
            m
            for m in (left + [m for m in right if not is_remove_message(m)])
            if m.message_id not in remove_ids
        ]

    return [m for m in left if m.message_id not in remove_ids]


def add_messages(left: list[Message], right: list[Message]) -> list[Message]:
    """
    Adds messages to the list, avoiding duplicates by message_id.

    Supports ``RemoveMessage`` tombstone directives: passing a
    ``RemoveMessage(message_id=...)`` removes the matching message instead of
    appending. ``REMOVE_ALL_MESSAGES`` clears the whole conversation.

    Args:
        left (list[Message]): Existing list of messages.
        right (list[Message]): New messages to add (may include tombstones).

    Returns:
        list[Message]: Combined list with unique messages.

    Example:
        >>> add_messages([msg1], [msg2, msg1])
        [msg1, msg2]
        >>> add_messages([msg1, msg2], [RemoveMessage(message_id=msg1.message_id)])
        [msg2]
    """
    # Apply tombstones against the existing list first.
    filtered_left = _filter_tombstones(left, right)

    left_ids = {msg.message_id for msg in filtered_left}
    right = [msg for msg in right if not is_remove_message(msg)]
    right = [msg for msg in right if msg.message_id not in left_ids and msg.delta is False]
    return filtered_left + right


def replace_messages(left: list[Message], right: list[Message]) -> list[Message]:
    """
    Replaces the entire message list with a new one.

    Tombstones in ``right`` are honored against the incoming list before the
    replacement is returned.

    Args:
        left (list[Message]): Existing list of messages (ignored).
        right (list[Message]): New list of messages (may include tombstones).

    Returns:
        list[Message]: The new message list.

    Example:
        >>> replace_messages([msg1], [msg2])
        [msg2]
    """
    filtered = _filter_tombstones(right, right, replace_all=True)
    return filtered


def append_items(left: list, right: list) -> list:
    """
    Appends items to a list, avoiding duplicates by item.id.

    Args:
        left (list): Existing list of items (must have .id attribute).
        right (list): New items to add.

    Returns:
        list: Combined list with unique items.

    Example:
        >>> append_items([item1], [item2, item1])
        [item1, item2]
    """
    left_ids = {item.id for item in left}
    right = [item for item in right if item.id not in left_ids]
    return left + right


def replace_value(left, right):
    """
    Replaces a value with another.

    Args:
        left: Existing value (ignored).
        right: New value to use.

    Returns:
        Any: The new value.

    Example:
        >>> replace_value(1, 2)
        2
    """
    return right


def remove_tool_messages(messages: list[Message]) -> list[Message]:
    """
    Remove COMPLETED tool interaction sequences from the message list.

    A tool sequence is only removed if it's COMPLETE:
    1. AI message with tool_calls (triggering tools)
    2. One or more tool result messages (role="tool")
    3. AI message WITHOUT tool_calls (final response using tool results)

    If a sequence is incomplete (e.g., tool call made but no final AI response yet),
    ALL messages are kept to maintain conversation continuity.

    Edge cases handled:
    - Incomplete sequences (AI called tool, waiting for results): Keep everything
    - Partial sequences (AI called tool, got results, but no final response): Keep everything
    - Multiple tool calls in one AI message: Handles correctly
    - Consecutive tool sequences: Each evaluated independently

    Args:
        messages (list[Message]): List of messages to filter.

    Returns:
        list[Message]: Filtered list with only COMPLETED tool sequences removed.

    Example:
        Complete sequence (will be cleaned):
        >>> messages = [user_msg, ai_with_tools, tool_result, ai_final]
        >>> remove_tool_messages(messages)
        [user_msg, ai_final]

        Incomplete sequence (will be kept):
        >>> messages = [user_msg, ai_with_tools]
        >>> remove_tool_messages(messages)
        [user_msg, ai_with_tools]  # Keep everything - sequence incomplete!

        Partial sequence (will be kept):
        >>> messages = [user_msg, ai_with_tools, tool_result]
        >>> remove_tool_messages(messages)
        [user_msg, ai_with_tools, tool_result]  # Keep - no final AI response!
    """
    if not messages:
        return messages

    # Step 1: Identify indices to remove by scanning for COMPLETE sequences
    indices_to_remove = set()
    i = 0

    while i < len(messages):
        msg = messages[i]

        # Look for AI message with tool calls (potential sequence start)
        if msg.role == "assistant" and msg.tools_calls:
            sequence_start = i
            i += 1

            # Collect all following tool result messages
            tool_result_indices = []
            while i < len(messages) and messages[i].role == "tool":
                tool_result_indices.append(i)
                i += 1

            # Check if there's a final AI response (without tool_calls)
            has_final_response = (
                i < len(messages)
                and messages[i].role == "assistant"
                and not messages[i].tools_calls
            )
            if has_final_response:
                # COMPLETE SEQUENCE FOUND!
                # Mark AI with tool_calls and all tool results for removal
                indices_to_remove.add(sequence_start)
                indices_to_remove.update(tool_result_indices)
                # Note: We keep the final AI response (index i)
                i += 1  # Move past the final AI response
            else:
                # INCOMPLETE SEQUENCE - keep everything
                # Don't add anything to indices_to_remove
                # i is already positioned correctly (at next message or end)
                pass
        else:
            i += 1

    # Step 2: Build filtered list excluding marked indices
    return [msg for idx, msg in enumerate(messages) if idx not in indices_to_remove]
