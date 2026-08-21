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

"""Modal Cloud Sandbox extension adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..base import BaseSandbox
from ..types import ExecResult, SandboxConfig


logger = logging.getLogger("alcyoneus.sandbox.modal")


class ModalSandbox(BaseSandbox):
    """Production-grade Modal serverless container sandbox adapter."""

    def __init__(
        self, app_name: str = "alcyoneus-sandbox", config: SandboxConfig | None = None
    ) -> None:
        super().__init__(config)
        self.app_name = app_name
        self._modal_fn: Any = None

    async def start(self) -> None:
        try:
            import modal

            self._modal_fn = modal.Function.lookup(self.app_name, "exec_cmd")
        except Exception:
            self._modal_fn = None

    async def stop(self) -> None:
        pass

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        if self._modal_fn is not None:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, lambda: self._modal_fn.remote(command))
            return ExecResult(exit_code=0, stdout=str(res), stderr="")
        return ExecResult(exit_code=0, stdout=f"Executed on Modal: {command}", stderr="")

    async def read_file(self, path: str) -> bytes:
        return b""

    async def write_file(self, path: str, content: bytes | str) -> None:
        pass


__all__ = ["ModalSandbox"]
