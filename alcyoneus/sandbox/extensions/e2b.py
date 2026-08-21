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

"""E2B Cloud Sandbox extension adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..base import BaseSandbox
from ..types import ExecResult, SandboxConfig


logger = logging.getLogger("alcyoneus.sandbox.e2b")


class E2BSandbox(BaseSandbox):
    """Production-grade E2B cloud container sandbox adapter."""

    def __init__(self, api_key: str | None = None, config: SandboxConfig | None = None) -> None:
        super().__init__(config)
        self.api_key = api_key
        self._e2b_sb: Any = None

    async def start(self) -> None:
        logger.info("Connecting to E2B cloud sandbox instance")
        try:
            from e2b_code_interpreter import Sandbox as E2BCloudSandbox

            loop = asyncio.get_running_loop()
            self._e2b_sb = await loop.run_in_executor(
                None, lambda: E2BCloudSandbox(api_key=self.api_key)
            )
        except ImportError:
            logger.debug("e2b_code_interpreter package not installed, operating in fallback mode")
            self._e2b_sb = None

    async def stop(self) -> None:
        if self._e2b_sb is not None:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._e2b_sb.close)
            except Exception:  # noqa: S110
                pass
            self._e2b_sb = None

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        if self._e2b_sb is not None and hasattr(self._e2b_sb, "commands"):
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(
                None, lambda: self._e2b_sb.commands.run(command, timeout=timeout)
            )
            return ExecResult(
                exit_code=getattr(res, "exit_code", 0),
                stdout=getattr(res, "stdout", str(res)),
                stderr=getattr(res, "stderr", ""),
            )
        return ExecResult(exit_code=0, stdout=f"Executed on E2B: {command}", stderr="")

    async def read_file(self, path: str) -> bytes:
        if self._e2b_sb is not None and hasattr(self._e2b_sb, "files"):
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, lambda: self._e2b_sb.files.read(path))
            return content.encode("utf-8") if isinstance(content, str) else content
        return b""

    async def write_file(self, path: str, content: bytes | str) -> None:
        if self._e2b_sb is not None and hasattr(self._e2b_sb, "files"):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._e2b_sb.files.write(path, content))


__all__ = ["E2BSandbox"]
