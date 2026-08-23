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

"""Declarative sandbox manifest for container provisioning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxManifest:
    """Declarative specification for pre-configuring a sandbox container environment."""

    python_packages: list[str] = field(default_factory=list)
    system_packages: list[str] = field(default_factory=list)
    environment_variables: dict[str, str] = field(default_factory=dict)
    files_to_copy: dict[str, str] = field(default_factory=dict)
    setup_commands: list[str] = field(default_factory=list)

    def export(self) -> dict[str, Any]:
        """Export manifest as JSON-serializable dictionary."""
        return {
            "python_packages": self.python_packages,
            "system_packages": self.system_packages,
            "environment_variables": self.environment_variables,
            "files_to_copy": self.files_to_copy,
            "setup_commands": self.setup_commands,
        }


__all__ = ["SandboxManifest"]
