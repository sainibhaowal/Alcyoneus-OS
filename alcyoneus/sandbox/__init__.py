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

"""Container Sandboxing and Code Isolation System for Alcyoneus OS."""

from .base import BaseSandbox
from .capabilities import (
    CompactionCapability,
    DynamicCompactionCapability,
    FilesystemCapability,
    MemoryCapability,
    ResponsesCompactionCapability,
    SandboxSnapshot,
    ShellCapability,
    SkillsCapability,
    SnapshotCapability,
    WorkspaceCapability,
)
from .dependencies import SandboxDependencies
from .docker import DockerSandbox
from .errors import (
    ExecTimeoutError,
    ExecTransportError,
    SandboxError,
    SandboxStartError,
)
from .extensions.blaxel import BlaxelSandbox
from .extensions.cloudflare import CloudflareSandbox
from .extensions.daytona import DaytonaSandbox
from .extensions.e2b import E2BSandbox
from .extensions.modal import ModalSandbox
from .extensions.runloop import RunloopSandbox
from .extensions.vercel import VercelSandbox
from .firecracker_sandbox import FirecrackerSandbox
from .k8s_sandbox import K8sSandbox
from .local import LocalSandbox
from .manifest import SandboxManifest
from .mounts import AzureBlobMount, BoxMount, GCSMount, R2Mount, S3Mount, StorageMount
from .pty_sandbox import UnixPTYSandbox
from .remote_file_sync import RemoteFileSync, SyncOptions
from .sinks import ConsoleSandboxSink, SandboxEventSink
from .snapshot import (
    LocalSnapshot,
    RemoteSnapshot,
    SnapshotManager,
    SnapshotSpec,
    resolve_snapshot,
)
from .types import Capability, ExecResult, SandboxConfig


__all__ = [
    "AzureBlobMount",
    "BaseSandbox",
    "BlaxelSandbox",
    "BoxMount",
    "Capability",
    "CloudflareSandbox",
    "CompactionCapability",
    "ConsoleSandboxSink",
    "DaytonaSandbox",
    "DockerSandbox",
    "DynamicCompactionCapability",
    "E2BSandbox",
    "ExecResult",
    "ExecTimeoutError",
    "ExecTransportError",
    "FilesystemCapability",
    "FirecrackerSandbox",
    "GCSMount",
    "K8sSandbox",
    "LocalSandbox",
    "LocalSnapshot",
    "MemoryCapability",
    "ModalSandbox",
    "R2Mount",
    "RemoteFileSync",
    "RemoteSnapshot",
    "ResponsesCompactionCapability",
    "RunloopSandbox",
    "S3Mount",
    "SandboxConfig",
    "SandboxDependencies",
    "SandboxError",
    "SandboxEventSink",
    "SandboxManifest",
    "SandboxSnapshot",
    "SandboxStartError",
    "ShellCapability",
    "SkillsCapability",
    "SnapshotCapability",
    "SnapshotManager",
    "SnapshotSpec",
    "StorageMount",
    "SyncOptions",
    "UnixPTYSandbox",
    "VercelSandbox",
    "WorkspaceCapability",
    "resolve_snapshot",
]
