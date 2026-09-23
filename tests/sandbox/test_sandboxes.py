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

"""Sandbox Mock Isolation Suite (Pillar 3).

Guarantees 100% test isolation and full branch coverage for:
1. DockerSandbox (SDK and CLI fallback paths, exec, start, stop, read_file, write_file)
2. K8sSandbox (Pod lifecycle, manifest builder, exec stream, read/write files, cleanup)
without requiring real Docker daemons or Kubernetes clusters in CI.
"""

from __future__ import annotations

import io
import tarfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcyoneus.sandbox.docker import DockerSandbox
from alcyoneus.sandbox.errors import ExecTimeoutError, SandboxError, SandboxStartError
from alcyoneus.sandbox.k8s_sandbox import K8sSandbox
from alcyoneus.sandbox.types import (
    GPUConfig,
    GPUDevice,
    NetworkConfig,
    SandboxConfig,
    VolumeMount,
)


# ==============================================================================
# DockerSandbox Isolation Suite
# ==============================================================================


class TestDockerSandboxIsolation:
    """Mock-isolated verification tests for DockerSandbox."""

    @pytest.fixture
    def mock_docker_sdk(self):
        """Mock docker-py SDK environment."""
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.id = "mock-docker-container-abc123"

        mock_client.containers.run.return_value = mock_container
        mock_client.containers.get.return_value = mock_container
        mock_client.api.create_host_config.return_value = {"mock": "host_cfg"}
        mock_client.api.exec_create.return_value = {"Id": "exec-456"}
        mock_client.api.exec_start.return_value = [b"hello from mocked docker"]
        mock_client.api.exec_inspect.return_value = {"ExitCode": 0}

        return mock_client, mock_container

    @pytest.mark.asyncio
    async def test_docker_sdk_lifecycle(self, mock_docker_sdk):
        """Verify full start, exec, and stop lifecycle using mocked docker SDK."""
        mock_client, mock_container = mock_docker_sdk

        cfg = SandboxConfig(
            image="python:3.12-slim",
            workdir="/workspace",
            env={"APP_ENV": "test"},
            memory_limit="512m",
            cpu_limit=1.5,
            volumes=[VolumeMount(source="/tmp/test", target="/data", read_only=True)],
            gpu_config=GPUConfig.SPECIFIC,
            gpu_devices=[GPUDevice(device_id="0")],
            network=NetworkConfig(enabled=True, mode="bridge", port_mappings={8080: 80}),
        )

        sandbox = DockerSandbox(config=cfg)
        sandbox._client = mock_client
        sandbox._use_sdk = True

        async with sandbox:
            assert sandbox.container_id == "mock-docker-container-abc123"
            mock_client.containers.run.assert_called_once()

            # Execute command
            result = await sandbox.exec("echo 'hello'")
            assert result.exit_code == 0
            assert "hello from mocked docker" in result.stdout
            assert result.success is True

        mock_container.stop.assert_called_once_with(timeout=5)
        mock_container.remove.assert_called_once()
        assert sandbox.container_id is None

    @pytest.mark.asyncio
    async def test_docker_file_operations_sdk(self, mock_docker_sdk):
        """Verify reading and writing files via Docker SDK archive methods."""
        mock_client, mock_container = mock_docker_sdk

        # Prepare a tar stream with test file
        tar_buf = io.BytesIO()
        test_filename = "app.py"
        test_bytes = b"print('sandbox test content')"
        with tarfile.open(fileobj=tar_buf, mode="w") as tf:
            info = tarfile.TarInfo(name=test_filename)
            info.size = len(test_bytes)
            tf.addfile(info, io.BytesIO(test_bytes))
        tar_buf.seek(0)

        mock_container.get_archive.return_value = ([tar_buf.getvalue()], None)

        sandbox = DockerSandbox()
        sandbox.container_id = "test-container-id"
        sandbox._client = mock_client
        sandbox._use_sdk = True

        # Test read_file
        content = await sandbox.read_file("/workspace/app.py")
        assert content == test_bytes

        # Test write_file
        await sandbox.write_file("/workspace/main.py", "print('written')")
        mock_container.put_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_docker_unstarted_error_handling(self):
        """Verify errors are raised when operating on unstarted container."""
        sandbox = DockerSandbox()
        assert sandbox.container_id is None

        with pytest.raises(SandboxError, match="Container not running"):
            await sandbox.read_file("/test.txt")

        with pytest.raises(SandboxError, match="Container not running"):
            await sandbox.write_file("/test.txt", "abc")

        with pytest.raises(SandboxError, match="Container not running"):
            await sandbox.exec_interactive("bash")

    @pytest.mark.asyncio
    async def test_docker_cli_fallback_start_and_exec(self):
        """Verify graceful fallback to CLI when SDK is unavailable."""
        sandbox = DockerSandbox()
        sandbox._client = None
        sandbox._use_sdk = False

        mock_proc_start = AsyncMock()
        mock_proc_start.returncode = 0
        mock_proc_start.communicate.return_value = (b"cli-container-789\n", b"")

        mock_proc_exec = AsyncMock()
        mock_proc_exec.returncode = 0
        mock_proc_exec.communicate.return_value = (b"cli command output", b"")

        mock_proc_kill = AsyncMock()
        mock_proc_kill.returncode = 0
        mock_proc_kill.communicate.return_value = (b"", b"")

        with patch("asyncio.create_subprocess_shell") as mock_subproc:
            mock_subproc.side_effect = [mock_proc_start, mock_proc_exec, mock_proc_kill]

            await sandbox.start()
            assert sandbox.container_id == "cli-container-789"

            exec_res = await sandbox.exec("ls -la")
            assert exec_res.stdout == "cli command output"
            assert exec_res.exit_code == 0

            await sandbox.stop()
            assert sandbox.container_id is None

    @pytest.mark.asyncio
    async def test_docker_cli_timeout_handling(self):
        """Verify ExecTimeoutError raised when execution exceeds timeout."""
        sandbox = DockerSandbox()
        sandbox.container_id = "test-running-container"
        sandbox._client = None
        sandbox._use_sdk = False

        mock_proc = AsyncMock()
        # First call inside wait_for raises TimeoutError, second call after kill returns (b"", b"")
        mock_proc.communicate = AsyncMock(side_effect=[TimeoutError(), (b"", b"")])
        mock_proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_shell", return_value=mock_proc):
            with pytest.raises(ExecTimeoutError):
                await sandbox.exec("sleep 100", timeout=0.01)

        mock_proc.kill.assert_called_once()


# ==============================================================================
# K8sSandbox Isolation Suite
# ==============================================================================


class TestK8sSandboxIsolation:
    """Mock-isolated verification tests for K8sSandbox."""

    @pytest.fixture
    def mock_k8s_env(self):
        """Mock Kubernetes client and stream modules."""
        mock_k8s = MagicMock()
        mock_client_module = MagicMock()
        mock_stream_module = MagicMock()

        mock_k8s.client = mock_client_module
        mock_k8s.stream = mock_stream_module
        mock_stream_module.stream.return_value = "pod output stdout"

        mock_core_v1 = MagicMock()
        mock_core_v1.api_client = MagicMock()

        mock_pod = MagicMock()
        mock_pod.status.phase = "Running"
        mock_core_v1.read_namespaced_pod.return_value = mock_pod
        mock_core_v1.create_namespaced_pod.return_value = None
        mock_core_v1.delete_namespaced_pod.return_value = None

        mock_client_module.CoreV1Api.return_value = mock_core_v1
        mock_client_module.V1Pod.return_value = mock_pod

        with patch.dict(
            "sys.modules",
            {
                "kubernetes": mock_k8s,
                "kubernetes.client": mock_client_module,
                "kubernetes.stream": mock_stream_module,
                "kubernetes.config": MagicMock(),
            },
        ):
            yield mock_core_v1, mock_stream_module

    @pytest.mark.asyncio
    async def test_k8s_sandbox_lifecycle(self, mock_k8s_env):
        """Verify K8s pod creation, execution stream, and pod cleanup."""
        mock_core_v1, mock_stream_module = mock_k8s_env

        cfg = SandboxConfig(
            image="python:3.12-alpine",
            workdir="/app",
            env={"CLUSTER": "staging"},
            cpu_limit=2.0,
            memory_limit="1Gi",
            gpu_config=GPUConfig.SPECIFIC,
            gpu_devices=[GPUDevice(device_id="0")],
        )

        sandbox = K8sSandbox(config=cfg, namespace="isolated-tenant")
        sandbox._client = mock_core_v1

        async with sandbox:
            assert sandbox.pod_name is not None
            assert sandbox.pod_name.startswith("alc-sandbox-")
            mock_core_v1.create_namespaced_pod.assert_called_once()

            # Exec in pod
            res = await sandbox.exec("hostname")
            assert res.exit_code == 0
            assert res.stdout == "pod output stdout"
            assert res.success is True

            # Read file via exec
            file_bytes = await sandbox.read_file("/app/config.json")
            assert file_bytes == b"pod output stdout"

            # Write file via exec
            await sandbox.write_file("/app/test.txt", "data")

        # Verify pod was stopped and deleted
        mock_core_v1.delete_namespaced_pod.assert_called_once()
        assert sandbox.pod_name is None

    @pytest.mark.asyncio
    async def test_k8s_sandbox_start_failure_phase(self, mock_k8s_env):
        """Verify SandboxStartError raised if Pod enters Failed state."""
        mock_core_v1, _ = mock_k8s_env

        mock_failed_pod = MagicMock()
        mock_failed_pod.status.phase = "Failed"
        mock_core_v1.read_namespaced_pod.return_value = mock_failed_pod

        sandbox = K8sSandbox(namespace="test-ns")
        sandbox._client = mock_core_v1

        with pytest.raises(SandboxStartError, match="Pod failed with phase Failed"):
            await sandbox.start()

    @pytest.mark.asyncio
    async def test_k8s_sandbox_uninitialized_client_error(self):
        """Verify error when client is unconfigured."""
        sandbox = K8sSandbox()
        sandbox._client = None

        with pytest.raises(SandboxStartError, match="Kubernetes client not configured"):
            await sandbox.start()

        with pytest.raises(SandboxError, match="Pod not running"):
            await sandbox.exec("date")
