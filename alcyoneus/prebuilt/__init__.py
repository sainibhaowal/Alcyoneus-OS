"""Prebuilt tools and agent packages for Alcyoneus OS.

Import concrete agent implementations from ``alcyoneus.prebuilt.agent`` and
tool helpers from ``alcyoneus.prebuilt.tools``.
"""

from __future__ import annotations

# Context managers
from alcyoneus.core.state.message_context_manager import MessageContextManager
from alcyoneus.core.state.summary_context_manager import SummaryContextManager

# Agents
from .agent import (
    BaseReranker,
    CohereReranker,
    CrossEncoderReranker,
    PlanActReflectAgent,
    RAGAgent,
    ReactAgent,
    StructuredOutputAgent,
    SupervisorTeamAgent,
    SwarmAgent,
    SwarmMemberConfig,
    WorkerConfig,
)

# Tools
from .tools import (
    create_handoff_tool,
    fetch_url,
    file_read,
    file_search,
    file_write,
    google_web_search,
    is_handoff_tool,
    make_agent_memory_tool,
    make_user_memory_tool,
    memory_tool,
    safe_calculator,
    vertex_ai_search,
)


__all__ = [
    # Agents
    "BaseReranker",
    "CohereReranker",
    "CrossEncoderReranker",
    # Context managers
    "MessageContextManager",
    "PlanActReflectAgent",
    "RAGAgent",
    "ReactAgent",
    "StructuredOutputAgent",
    "SummaryContextManager",
    "SupervisorTeamAgent",
    "SwarmAgent",
    "SwarmMemberConfig",
    "WorkerConfig",
    # Tools
    "create_handoff_tool",
    "fetch_url",
    "file_read",
    "file_search",
    "file_write",
    "google_web_search",
    "is_handoff_tool",
    "make_agent_memory_tool",
    "make_user_memory_tool",
    "memory_tool",
    "safe_calculator",
    "vertex_ai_search",
]
