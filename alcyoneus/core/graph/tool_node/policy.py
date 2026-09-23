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

"""Alcyoneus OS Tool Node Policy Module.

Re-exports unified policy engine components for ToolNode execution safety,
backward-compatible with earlier tool_node.policy imports.
"""

from __future__ import annotations

import logging

from alcyoneus.core.policy.engine import (
    Decision,
    Policy,
    PolicyAction,
    PolicyConfig,
    PolicyEngine,
    ToolExecutionPolicy,
    allow,
    allow_all,
    ask_user,
    confirm_run_command,
    default_ask_user_handler,
    deny,
    deny_all,
    safe_defaults,
    workspace_only,
)


logger = logging.getLogger("alcyoneus.graph.tool_node.policy")


__all__ = [
    "Decision",
    "Policy",
    "PolicyAction",
    "PolicyConfig",
    "PolicyEngine",
    "ToolExecutionPolicy",
    "allow",
    "allow_all",
    "ask_user",
    "confirm_run_command",
    "default_ask_user_handler",
    "deny",
    "deny_all",
    "safe_defaults",
    "workspace_only",
]
