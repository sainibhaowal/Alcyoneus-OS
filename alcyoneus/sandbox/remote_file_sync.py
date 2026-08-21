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

"""Remote file synchronization for sandboxes with cloud storage mounts."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mounts import StorageMount


logger = logging.getLogger("alcyoneus.sandbox.remote_file_sync")


@dataclass
class SyncOptions:
    bidirectional: bool = False
    checksum: bool = True
    follow_symlinks: bool = False
    delete_remote: bool = False


class RemoteFileSync:
    """Synchronize files between sandbox filesystem and remote storage mounts."""

    def __init__(self, mounts: list[StorageMount] | None = None) -> None:
        self.mounts = mounts or []

    async def sync(self, local_path: str, options: SyncOptions | None = None) -> dict[str, Any]:
        opts = options or SyncOptions()
        results = {"files_synced": 0, "bytes": 0, "errors": []}
        local = Path(local_path)
        if not local.exists():
            raise FileNotFoundError(local_path)
        for mount in self.mounts:
            try:
                await self._sync_mount(mount, local, opts, results)
            except Exception as exc:
                results["errors"].append({"mount": mount.container_path, "error": str(exc)})
        return results

    async def _sync_mount(
        self, mount: StorageMount, local: Path, opts: SyncOptions, results: dict[str, Any]
    ) -> None:
        # Production implementation would use boto3/gcs/azure SDKs
        # Scaffold: log and simulate
        logger.info("Syncing %s to mount %s", local, mount.container_path)
        # Walk local files
        for p in local.rglob("*"):
            if p.is_file():
                results["files_synced"] += 1
                results["bytes"] += p.stat().st_size
                await asyncio.sleep(0)  # yield

    async def push_file(self, path: str, content: bytes | str) -> None:
        data = content if isinstance(content, bytes) else content.encode()
        checksum = hashlib.sha256(data).hexdigest()
        logger.debug("Pushing file %s checksum=%s", path, checksum)

    async def pull_file(self, remote_path: str, local_path: str) -> Path:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        # Scaffold
        return Path(local_path)

    async def watch(self, local_path: str) -> AsyncIterator[Path]:
        """Watch for file changes and yield paths."""
        last_mtime: dict[Path, float] = {}
        path = Path(local_path)
        while True:
            for p in path.rglob("*"):
                if p.is_file():
                    mtime = p.stat().st_mtime
                    if p not in last_mtime or last_mtime[p] != mtime:
                        last_mtime[p] = mtime
                        yield p
            await asyncio.sleep(1)


__all__ = ["RemoteFileSync", "SyncOptions"]
