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

"""Modular Filesystem capability for sandboxes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FilesystemCapability:
    """Filesystem access capability configuration."""

    enabled: bool = True
    read_only: bool = False
    max_file_size_mb: int = 100
    allowed_directories: list[str] | None = None


__all__ = ["FilesystemCapability"]
