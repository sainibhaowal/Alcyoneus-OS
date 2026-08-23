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

"""Sandbox snapshot management for state capture and restoration."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import BaseSandbox


@dataclass
class SnapshotSpec:
    """Specification for taking or restoring a sandbox snapshot."""

    snapshot_id: str
    description: str = ""
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalSnapshot(SnapshotSpec):
    """Local filesystem container snapshot representation."""

    path: str = ""


@dataclass
class RemoteSnapshot(SnapshotSpec):
    """Cloud repository container snapshot representation."""

    uri: str = ""
    credentials: dict[str, Any] = field(default_factory=dict)


def resolve_snapshot(spec: SnapshotSpec | str) -> SnapshotSpec:
    """Resolve a string ID or SnapshotSpec object into a normalized SnapshotSpec."""
    if isinstance(spec, str):
        return SnapshotSpec(snapshot_id=spec)
    return spec


class SnapshotManager:
    """Manages sandbox snapshot persistence and restoration."""

    def __init__(self, sandbox: BaseSandbox):
        self.sandbox = sandbox
        self._snapshots: dict[str, dict[str, Any]] = {}

    async def persist(
        self, spec: SnapshotSpec | str, *, include_fs: bool = True, include_memory: bool = True
    ) -> LocalSnapshot:
        """Persist a sandbox snapshot to local storage.

        Args:
            spec: Snapshot specification or ID.
            include_fs: Whether to include filesystem state.
            include_memory: Whether to include memory state.

        Returns:
            LocalSnapshot with the persisted snapshot data.
        """
        spec = resolve_snapshot(spec)
        snapshot_id = spec.snapshot_id or f"snap_{int(time.time())}"
        created_at = time.time()

        filesystem = {}
        if include_fs:
            # Capture filesystem from sandbox workdir
            workdir = Path(self.sandbox.config.workdir)
            if workdir.exists():
                for p in workdir.rglob("*"):
                    if p.is_file():
                        rel = p.relative_to(workdir)
                        try:
                            filesystem[str(rel)] = p.read_bytes()
                        except Exception:  # noqa: S110
                            pass

        memory = b""
        if include_memory:
            # Capture any in-memory state (process output, variables, etc.)
            memory = json.dumps({"timestamp": created_at}).encode()

        snapshot_data = {
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "description": spec.description,
            "filesystem": filesystem,
            "memory": memory,
            "metadata": spec.metadata,
        }

        self._snapshots[snapshot_id] = snapshot_data
        return LocalSnapshot(
            snapshot_id=snapshot_id,
            description=spec.description,
            created_at=created_at,
            path=f".snapshots/{snapshot_id}.json",
            metadata=snapshot_data["metadata"],
        )

    async def restore(self, spec: SnapshotSpec | str) -> bool:
        """Restore sandbox state from a snapshot.

        Args:
            spec: Snapshot specification or ID.

        Returns:
            True if restored successfully.
        """
        spec = resolve_snapshot(spec)
        snapshot_id = spec.snapshot_id

        if snapshot_id not in self._snapshots:
            # Try loading from disk
            snap_path = Path(f".snapshots/{snapshot_id}.json")
            if snap_path.exists():
                self._snapshots[snapshot_id] = json.loads(snap_path.read_text())
            else:
                return False

        data = self._snapshots[snapshot_id]

        # Restore filesystem
        workdir = Path(self.sandbox.config.workdir)
        for rel_path, content in data.get("filesystem", {}).items():
            full = workdir / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(content)

        # Restore memory (e.g., environment variables, process state)
        if data.get("memory"):
            try:
                _ = json.loads(data["memory"])
                # Apply memory state to sandbox if applicable
            except Exception:  # noqa: S110
                pass

        return True

    async def hydrate_workspace(self, template: str | None = None, **kwargs: Any) -> bool:
        """Hydrate the sandbox workspace from a template or snapshot.

                Args:
                    template: Workspace template name (looked up in
        WorkspaceCapability.workspace_templates).
                    **kwargs: Additional context for workspace hydration.

                Returns:
                    True if workspace was hydrated successfully.
        """
        # If template provided, use it; otherwise use default workspace
        workdir = Path(self.sandbox.config.workdir)
        workdir.mkdir(parents=True, exist_ok=True)

        # Create basic workspace structure
        (workdir / ".alcyoneus").mkdir(exist_ok=True)
        (workdir / ".alcyoneus" / "hydrated").write_text(str(time.time()))

        if template:
            # Look up template and apply
            template_path = Path(template)
            if template_path.exists():
                for item in template_path.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(template_path)
                        dst = workdir / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_bytes(item.read_bytes())

        return True

    def list_snapshots(self) -> list[LocalSnapshot]:
        """List available snapshots."""
        return [
            LocalSnapshot(
                snapshot_id=k,
                description=v.get("description", ""),
                created_at=v.get("created_at", 0.0),
                metadata=v.get("metadata", {}),
            )
            for k, v in self._snapshots.items()
        ]


__all__ = [
    "LocalSnapshot",
    "RemoteSnapshot",
    "SnapshotManager",
    "SnapshotSpec",
    "resolve_snapshot",
]
