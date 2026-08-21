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

"""Data structures and types for Alcyoneus OS sandboxes."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Capability(str, enum.Enum):
    """Sandbox capability flags."""

    SHELL = "shell"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    MEMORY = "memory"


@dataclass
class ExecResult:
    """Result of command execution inside sandbox."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class GPUConfig(str, enum.Enum):
    """GPU passthrough configuration."""

    NONE = "none"
    ALL = "all"
    SPECIFIC = "specific"
    VIRTUAL = "virtual"


class ResourceLimits(str, enum.Enum):
    """Resource limit enforcement modes."""

    SOFT = "soft"  # cgroup v2 soft limits
    HARD = "hard"  # cgroup v2 hard limits
    NONE = "none"  # no enforcement


@dataclass
class GPUDevice:
    """GPU device specification for passthrough."""

    device_id: str = "0"
    vendor: str = "nvidia"  # nvidia, amd, intel
    memory_mb: int | None = None
    compute_capability: str | None = None


@dataclass
class NetworkConfig:
    """Advanced network configuration for sandbox."""

    enabled: bool = True
    mode: str = "bridge"  # bridge, host, none, custom
    port_mappings: dict[int, int] = field(default_factory=dict)  # host_port -> container_port
    dns_servers: list[str] = field(default_factory=list)
    extra_hosts: dict[str, str] = field(default_factory=dict)  # hostname -> ip


@dataclass
class VolumeMount:
    """Volume mount specification."""

    source: str  # host path or volume name
    target: str  # container path
    read_only: bool = False
    type: str = "bind"  # bind, volume, tmpfs


@dataclass
class SandboxConfig:
    """Configuration settings for container sandbox."""

    image: str = "python:3.11-slim"
    workdir: str = "/workspace"
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 300.0
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    network_enabled: bool = True
    capabilities: list[Capability] = field(
        default_factory=lambda: [Capability.SHELL, Capability.FILESYSTEM]
    )

    # GPU passthrough
    gpu_config: GPUConfig = GPUConfig.NONE
    gpu_devices: list[GPUDevice] = field(default_factory=list)

    # Resource limits
    resource_limits: ResourceLimits = ResourceLimits.SOFT
    memory_swap_limit: str | None = None
    pids_limit: int | None = None
    ulimits: dict[str, tuple[int, int]] = field(default_factory=dict)

    # Network configuration
    network: NetworkConfig = field(default_factory=NetworkConfig)

    # Volume mounts
    volumes: list[VolumeMount] = field(default_factory=list)

    # Security
    privileged: bool = False
    read_only_rootfs: bool = False
    security_opt: list[str] = field(default_factory=list)
    capabilities_add: list[str] = field(default_factory=list)
    capabilities_drop: list[str] = field(default_factory=list)
    seccomp_profile: str | None = None
    apparmor_profile: str | None = None

    # Runtime
    runtime: str | None = None  # runc, kata-runtime, crun, etc.
    init: bool = False  # run with --init

    # PTY/Interactive
    tty: bool = False
    stdin_open: bool = False

    # Health checks
    health_check_cmd: str | None = None
    health_check_interval: int = 30
    health_check_timeout: int = 10
    health_check_retries: int = 3


__all__ = [
    "Capability",
    "ExecResult",
    "SandboxConfig",
]
