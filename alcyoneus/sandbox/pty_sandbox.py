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

"""Unix PTY pseudo-terminal local sandbox execution environment."""

from __future__ import annotations

import asyncio
import os
import pty
import select
import time

from .base import BaseSandbox
from .types import ExecResult


class UnixPTYSandbox(BaseSandbox):
    """Unix PTY pseudo-terminal local sandbox for interactive command execution."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        start_t = time.time()
        master_fd, slave_fd = pty.openpty()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.config.workdir if os.path.exists(self.config.workdir) else None,
                env={**os.environ, **self.config.env},
                close_fds=True,
            )
            os.close(slave_fd)
            output = bytearray()

            async def _read_pty():
                nonlocal output
                while True:
                    r, _, _ = select.select([master_fd], [], [], 0.05)
                    if master_fd in r:
                        try:
                            data = os.read(master_fd, 1024)
                            if not data:
                                break
                            output.extend(data)
                        except OSError:
                            break
                    if proc.returncode is not None:
                        break

            await asyncio.wait_for(_read_pty(), timeout=timeout or self.config.timeout_seconds)
            await proc.wait()
            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout=output.decode(errors="replace"),
                stderr="",
                duration_seconds=time.time() - start_t,
            )
        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass


__all__ = ["UnixPTYSandbox"]
