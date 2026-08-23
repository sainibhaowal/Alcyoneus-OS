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

"""Local subprocess sandbox implementation for non-isolated development testing."""

from __future__ import annotations

import asyncio
import os
import pathlib
import time

from .base import BaseSandbox
from .errors import ExecTimeoutError
from .types import ExecResult


class LocalSandbox(BaseSandbox):
    """Local subprocess sandbox executing commands directly on host system.

    Mainly used for rapid local development and testing.
    """

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        timeout_sec = timeout or self.config.timeout_seconds
        start_t = time.time()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.workdir if os.path.exists(self.config.workdir) else None,
                env={**os.environ, **self.config.env},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            dur = time.time() - start_t
            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                duration_seconds=dur,
            )
        except TimeoutError:
            raise ExecTimeoutError(f"Command '{command}' timed out after {timeout_sec}s")

    async def read_file(self, path: str) -> bytes:
        p = pathlib.Path(self.config.workdir) / path
        return p.read_bytes()

    async def write_file(self, path: str, content: bytes | str) -> None:
        p = pathlib.Path(self.config.workdir) / path
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)


__all__ = ["LocalSandbox"]
