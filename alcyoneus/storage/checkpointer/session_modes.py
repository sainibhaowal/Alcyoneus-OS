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
"""Session continuation modes for alcyoneus OS checkpointers.

Provides session continuation modes similar to Google Antigravity SDK.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class SessionContinuationMode(str, Enum):
    """Session continuation mode for checkpointers.

    - RESUME: Resume existing session, fail if not found.
    - CREATE_OR_RESUME: Create new session if not found, otherwise resume.
    - CREATE_ONLY: Create new session, fail if already exists.
    """

    RESUME = "resume"
    CREATE_OR_RESUME = "create_or_resume"
    CREATE_ONLY = "create_only"


def validate_session_continuation(
    mode: SessionContinuationMode, conversation_id: str | None
) -> bool:
    """Validate session continuation mode against conversation ID.

    Args:
        mode: The session continuation mode.
        conversation_id: Optional conversation/thread ID.

    Returns:
        True if valid combination.

    Raises:
        ValueError: If mode requires conversation_id but none provided.
    """
    if mode == SessionContinuationMode.RESUME and not conversation_id:
        raise ValueError("RESUME mode requires conversation_id")
    return True


async def handle_session_continuation(
    checkpointer: Any,
    config: dict[str, Any],
    mode: SessionContinuationMode = SessionContinuationMode.CREATE_OR_RESUME,
) -> tuple[dict[str, Any], bool]:
    """Handle session continuation logic.

    Args:
        checkpointer: Checkpointer instance.
        config: Configuration with thread_id.
        mode: Session continuation mode.

    Returns:
        Tuple of (updated_config, is_new_session).
    """
    thread_id = config.get("thread_id")
    if not thread_id:
        raise ValueError("thread_id required in config")

    validate_session_continuation(mode, thread_id)

    # Check if session exists
    state = await checkpointer.aget_state(config)

    if mode == SessionContinuationMode.RESUME:
        if state is None:
            raise ValueError(f"Session {thread_id} not found for RESUME mode")
        return config, False

    if mode == SessionContinuationMode.CREATE_ONLY:
        if state is not None:
            raise ValueError(f"Session {thread_id} already exists for CREATE_ONLY mode")
        return config, True

    if mode == SessionContinuationMode.CREATE_OR_RESUME:
        if state is None:
            return config, True
        return config, False

    return config, state is None


__all__ = [
    "SessionContinuationMode",
    "handle_session_continuation",
    "validate_session_continuation",
]
