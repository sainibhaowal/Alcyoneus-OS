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

"""Abstract Base Class for isolated sandbox execution environments."""

from __future__ import annotations

import abc
from typing import Any

from .types import ExecResult, SandboxConfig


class BaseSandbox(abc.ABC):
    """Abstract interface for all sandbox providers (Docker, E2B, Modal, Local)."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    @abc.abstractmethod
    async def start(self) -> None:
        """Initialize and spin up the sandbox container environment."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Tear down and clean up the sandbox environment."""

    @abc.abstractmethod
    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        """Execute a shell command inside the sandbox."""

    @abc.abstractmethod
    async def read_file(self, path: str) -> bytes:
        """Read file contents from the sandbox filesystem."""

    @abc.abstractmethod
    async def write_file(self, path: str, content: bytes | str) -> None:
        """Write file contents to the sandbox filesystem."""

    async def __aenter__(self) -> BaseSandbox:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()


__all__ = ["BaseSandbox"]
