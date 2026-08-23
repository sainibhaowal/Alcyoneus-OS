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

"""Sandbox error and exception classes for Alcyoneus OS."""

from __future__ import annotations


class SandboxError(Exception):
    """Base exception for all sandbox container operations."""


class ExecTimeoutError(SandboxError):
    """Raised when command execution inside sandbox exceeds timeout."""


class ExecTransportError(SandboxError):
    """Raised when transport to sandbox container fails."""


class SandboxStartError(SandboxError):
    """Raised when sandbox fails to spin up."""


__all__ = [
    "ExecTimeoutError",
    "ExecTransportError",
    "SandboxError",
    "SandboxStartError",
]
