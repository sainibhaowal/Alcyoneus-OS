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
import pathlib
import pty
import select
import threading
import time

from .base import BaseSandbox
from .errors import ExecTimeoutError
from .types import ExecResult


class UnixPTYSandbox(BaseSandbox):
    """Unix PTY pseudo-terminal local sandbox for interactive command execution."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        timeout_sec = timeout or self.config.timeout_seconds
        start_t = time.time()
        master_fd, slave_fd = pty.openpty()
        output = bytearray()
        reader_added = False
        loop = asyncio.get_running_loop()
        stop_event = threading.Event()
        fallback_thread: threading.Thread | None = None

        def _on_readable() -> None:
            try:
                data = os.read(master_fd, 4096)
                if data:
                    output.extend(data)
                else:
                    loop.remove_reader(master_fd)
            except OSError:
                loop.remove_reader(master_fd)

        def _thread_reader() -> None:
            while not stop_event.is_set():
                r, _, _ = select.select([master_fd], [], [], 0.05)
                if master_fd in r:
                    try:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        output.extend(data)
                    except OSError:
                        break

        try:
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
            finally:
                os.close(slave_fd)

            try:
                loop.add_reader(master_fd, _on_readable)
                reader_added = True
            except (NotImplementedError, AttributeError):
                fallback_thread = threading.Thread(target=_thread_reader, daemon=True)
                fallback_thread.start()

            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
            except TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    # Process already exited before kill
                    pass
                await proc.wait()
                raise ExecTimeoutError(f"Command '{command}' timed out after {timeout_sec}s")

            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout=output.decode(errors="replace"),
                stderr="",
                duration_seconds=time.time() - start_t,
            )
        finally:
            if reader_added:
                loop.remove_reader(master_fd)
            if fallback_thread is not None:
                stop_event.set()
                fallback_thread.join(timeout=0.5)

            # Drain any remaining bytes in non-blocking mode
            try:
                os.set_blocking(master_fd, False)
                while True:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    output.extend(data)
            except OSError:
                # Non-blocking buffer drained or file descriptor already closed
                pass

            try:
                os.close(master_fd)
            except OSError:
                # File descriptor may already be closed by OS
                pass

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


__all__ = ["UnixPTYSandbox"]
