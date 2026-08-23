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

"""Lifecycle Hooks and Context Hierarchy System for Alcyoneus OS."""

from .compaction import (
    CompactionEvent,
    CompactionPolicy,
    DynamicCompactionPolicy,
    OnCompactionHook,
    ResponsesCompactionSession,
    on_compaction,
)
from .context import (
    HookContext,
    OperationContext,
    SessionContext,
    StateStore,
    TurnContext,
)
from .interaction import (
    InteractionResult,
    InteractionSpec,
    OnInteractionHook,
    on_interaction,
)
from .lifecycle import AgentHooks, RunHooks
from .session import (
    AgentSession,
    SessionContinuationMode,
    agent_session,
)


__all__ = [
    "AgentHooks",
    "AgentSession",
    "CompactionEvent",
    "CompactionPolicy",
    "DynamicCompactionPolicy",
    "HookContext",
    "InteractionResult",
    "InteractionSpec",
    "OnCompactionHook",
    "OnInteractionHook",
    "OperationContext",
    "ResponsesCompactionSession",
    "RunHooks",
    "SessionContext",
    "SessionContinuationMode",
    "StateStore",
    "TurnContext",
    "agent_session",
    "on_compaction",
    "on_interaction",
]
