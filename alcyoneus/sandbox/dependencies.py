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

"""Dependency injection container for Sandboxes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxDependencies:
    """Dependency injection container mapping sandbox service dependencies."""

    services: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, service: Any) -> None:
        self.services[name] = service

    def get(self, name: str, default: Any = None) -> Any:
        return self.services.get(name, default)


__all__ = ["SandboxDependencies"]
