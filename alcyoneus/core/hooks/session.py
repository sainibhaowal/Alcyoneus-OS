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

"""AgentSession context manager for automated session lifecycle scoping."""

from __future__ import annotations

import enum
from typing import Any


class SessionContinuationMode(str, enum.Enum):
    """Session continuation behavior mode."""

    NEW = "new"
    CONTINUE = "continue"
    RESUME = "resume"


class AgentSession:
    """Context manager controlling session lifecycle and state continuation."""

    def __init__(
        self,
        session_id: str,
        mode: SessionContinuationMode = SessionContinuationMode.CONTINUE,
    ) -> None:
        self.session_id = session_id
        self.mode = mode

    async def __aenter__(self) -> AgentSession:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


def agent_session(
    session_id: str,
    mode: SessionContinuationMode = SessionContinuationMode.CONTINUE,
) -> AgentSession:
    """Helper factory constructing an AgentSession instance."""
    return AgentSession(session_id=session_id, mode=mode)


__all__ = [
    "AgentSession",
    "SessionContinuationMode",
    "agent_session",
]
