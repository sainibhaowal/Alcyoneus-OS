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

"""Snapshot capability for sandbox state capture and restoration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SnapshotCapability:
    """Snapshot capability for capturing and restoring sandbox state."""

    enabled: bool = True
    auto_snapshot_interval_seconds: int = 300
    max_snapshots: int = 10
    include_filesystem: bool = True
    include_memory: bool = True
    include_processes: bool = False


@dataclass
class WorkspaceCapability:
    """Workspace capability for managing isolated project workspaces.

    Provides hydrate_workspace, persist_workspace, restore_workspace operations.
    """

    enabled: bool = True
    default_workspace_path: str = "/workspace"
    auto_hydrate_on_start: bool = True
    workspace_templates: dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxSnapshot:
    """Represents a complete sandbox snapshot."""

    snapshot_id: str
    created_at: float
    filesystem: dict[str, bytes] = field(default_factory=dict)
    memory: bytes = b""
    processes: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "SandboxSnapshot",
    "SnapshotCapability",
    "WorkspaceCapability",
]
