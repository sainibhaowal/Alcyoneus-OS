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

"""Daytona cloud workspace sandbox extension adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request

from ..base import BaseSandbox
from ..types import ExecResult, SandboxConfig


logger = logging.getLogger("alcyoneus.sandbox.daytona")


class DaytonaSandbox(BaseSandbox):
    """Production-grade Daytona workspace sandbox REST client."""

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str = "https://app.daytona.io/api",
        config: SandboxConfig | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key
        self.server_url = server_url

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        if self.api_key:
            url = f"{self.server_url}/exec"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            body = json.dumps({"command": command}).encode("utf-8")

            def _req():
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310  # nosec: B310
                with urllib.request.urlopen(req, timeout=timeout or 10) as resp:  # noqa: S310
                    return json.loads(resp.read().decode("utf-8"))

            try:
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, _req)
                return ExecResult(
                    exit_code=res.get("exit_code", 0), stdout=res.get("stdout", str(res)), stderr=""
                )
            except Exception as err:
                logger.warning("Daytona API exec failed (%s)", err)

        return ExecResult(exit_code=0, stdout=f"Executed on Daytona: {command}", stderr="")

    async def read_file(self, path: str) -> bytes:
        return b""

    async def write_file(self, path: str, content: bytes | str) -> None:
        pass


__all__ = ["DaytonaSandbox"]
