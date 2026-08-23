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

"""Sandbox execution event sinks for monitoring stdout, stderr, and lifecycle events."""

from __future__ import annotations

import abc
import logging


logger = logging.getLogger("alcyoneus.sandbox.sinks")


class SandboxEventSink(abc.ABC):
    """Abstract interface for receiving sandbox execution events."""

    @abc.abstractmethod
    def on_stdout(self, data: str) -> None:
        pass

    @abc.abstractmethod
    def on_stderr(self, data: str) -> None:
        pass


class ConsoleSandboxSink(SandboxEventSink):
    """Console logging sink for sandbox execution output."""

    def on_stdout(self, data: str) -> None:
        logger.info("[SANDBOX STDOUT] %s", data.strip())

    def on_stderr(self, data: str) -> None:
        logger.warning("[SANDBOX STDERR] %s", data.strip())


__all__ = [
    "ConsoleSandboxSink",
    "SandboxEventSink",
]
