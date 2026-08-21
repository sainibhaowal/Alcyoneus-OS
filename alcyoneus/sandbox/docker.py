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

"""Docker container sandbox implementation for hardware-isolated code execution."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from .base import BaseSandbox
from .errors import ExecTimeoutError, SandboxError, SandboxStartError
from .types import (
    ExecResult,
    GPUConfig,
    SandboxConfig,
)


logger = logging.getLogger("alcyoneus.sandbox.docker")


class DockerSandbox(BaseSandbox):
    """Isolated sandbox running inside a local/remote Docker container.

    Uses `docker-py` SDK if available, or falls back gracefully to `docker` CLI.
    Supports GPU passthrough, resource limits, volume mounts, network config, PTY.
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        super().__init__(config)
        self.container_id: str | None = None
        self._client: Any | None = None
        self._use_sdk: bool = False

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            import docker

            self._client = docker.from_env()
            self._use_sdk = True
        except Exception as exc:
            logger.debug("docker-py not available: %s", exc)
            self._client = None
            self._use_sdk = False
        return self._client

    def _build_host_config(self) -> dict[str, Any]:
        cfg = self.config
        host_config: dict[str, Any] = {
            "network_mode": cfg.network.mode if cfg.network.enabled else "none",
            "mem_limit": cfg.memory_limit,
            "cpu_quota": int(cfg.cpu_limit * 100_000),
            "cpu_period": 100_000,
            "working_dir": cfg.workdir,
            "environment": cfg.env,
        }

        # Volume mounts
        binds: dict[str, dict[str, str]] = {}
        for vol in cfg.volumes:
            host_path = vol.source
            if not os.path.isabs(host_path):
                host_path = str(Path(cfg.workdir).parent / host_path)
            binds[host_path] = {"bind": vol.target, "mode": "ro" if vol.read_only else "rw"}
        if binds:
            host_config["volumes"] = binds

        # GPU
        if cfg.gpu_config != GPUConfig.NONE:
            device_requests: list[dict[str, Any]] = []
            if cfg.gpu_config == GPUConfig.ALL:
                device_requests.append({"Driver": "nvidia", "Count": -1, "Capabilities": [["gpu"]]})
            elif cfg.gpu_config == GPUConfig.SPECIFIC and cfg.gpu_devices:
                for dev in cfg.gpu_devices:
                    device_requests.append(
                        {
                            "Driver": "nvidia",
                            "DeviceIDs": [dev.device_id],
                            "Capabilities": [["gpu"]],
                        }
                    )
            if device_requests:
                host_config["device_requests"] = device_requests

        # Network
        if cfg.network.enabled and cfg.network.port_mappings:
            ports = {f"{c}/tcp": h for h, c in cfg.network.port_mappings.items()}
            host_config["ports"] = ports

        # Security
        if cfg.read_only_rootfs:
            host_config["read_only"] = True
        if cfg.capabilities_drop:
            host_config["cap_drop"] = cfg.capabilities_drop
        if cfg.capabilities_add:
            host_config["cap_add"] = cfg.capabilities_add
        if cfg.privileged:
            host_config["privileged"] = True

        # Pids, ulimits
        if cfg.pids_limit:
            host_config["pids_limit"] = cfg.pids_limit

        return host_config

    async def start(self) -> None:
        client = self._get_client()
        cfg = self.config
        if self._use_sdk and client is not None:
            try:
                host_cfg = self._build_host_config()
                container = client.containers.run(
                    image=cfg.image,
                    command="tail -f /dev/null",
                    detach=True,
                    tty=cfg.tty,
                    stdin_open=cfg.stdin_open,
                    working_dir=cfg.workdir,
                    environment=cfg.env,
                    host_config=client.api.create_host_config(**host_cfg),
                    remove=False,
                )
                self.container_id = container.id
                # Wait for container to be running
                await asyncio.sleep(0.2)
                logger.info("Docker container started via SDK: %s", self.container_id)
                return
            except Exception as exc:
                logger.warning("Docker SDK start failed: %s", exc)

        # Fallback to CLI
        parts = [
            "docker",
            "run",
            "-d",
            "--rm",
            "-w",
            cfg.workdir,
            f"--memory={cfg.memory_limit}",
            f"--cpus={cfg.cpu_limit}",
        ]
        for vol in cfg.volumes:
            mode = "ro" if vol.read_only else "rw"
            parts += ["-v", f"{vol.source}:{vol.target}:{mode}"]
        if cfg.network.enabled:
            parts += ["--network", cfg.network.mode]
        parts += [cfg.image, "tail", "-f", "/dev/null"]
        cmd = " ".join(parts)
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise SandboxStartError(stderr.decode())
        self.container_id = stdout.decode().strip()
        logger.info("Docker container started via CLI: %s", self.container_id)

    async def stop(self) -> None:
        if not self.container_id:
            return
        client = self._get_client()
        if self._use_sdk and client is not None:
            try:
                container = client.containers.get(self.container_id)
                container.stop(timeout=5)
                container.remove()
                logger.info("Docker container stopped via SDK: %s", self.container_id)
            except Exception as exc:
                logger.warning("Docker SDK stop failed: %s", exc)
        else:
            proc = await asyncio.create_subprocess_shell(
                f"docker kill {self.container_id}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        self.container_id = None

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        start_t = time.monotonic()
        if not self.container_id:
            # Fallback to local
            return await self._exec_local(command, timeout)

        client = self._get_client()
        if self._use_sdk and client is not None:
            try:
                exec_id = client.api.exec_create(
                    self.container_id,
                    command,
                    environment=self.config.env,
                    tty=self.config.tty,
                )["Id"]
                output = client.api.exec_start(exec_id, stream=True, tty=self.config.tty)
                stdout_chunks: list[bytes] = []
                # docker-py returns bytes
                for chunk in output:
                    stdout_chunks.append(chunk)
                stdout = b"".join(stdout_chunks).decode(errors="replace")
                inspect = client.api.exec_inspect(exec_id)
                exit_code = inspect.get("ExitCode", 0)
                return ExecResult(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr="",
                    duration_seconds=time.monotonic() - start_t,
                )
            except Exception as exc:
                logger.warning("Docker SDK exec failed, falling back: %s", exc)

        # CLI fallback
        exec_cmd = f"docker exec {self.container_id} sh -c {command!r}"
        proc = await asyncio.create_subprocess_shell(
            exec_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or self.config.timeout_seconds
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise ExecTimeoutError(f"Command timed out after {timeout}s")
        return ExecResult(
            exit_code=proc.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            duration_seconds=time.monotonic() - start_t,
        )

    async def _exec_local(self, command: str, timeout: float | None = None) -> ExecResult:
        start_t = time.monotonic()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.workdir if os.path.exists(self.config.workdir) else None,
            env={**os.environ, **self.config.env},
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or self.config.timeout_seconds
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise ExecTimeoutError(f"Command timed out after {timeout}s")
        return ExecResult(
            exit_code=proc.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            duration_seconds=time.monotonic() - start_t,
        )

    async def read_file(self, path: str) -> bytes:
        if not self.container_id:
            raise SandboxError("Container not running")
        client = self._get_client()
        if self._use_sdk and client is not None:
            try:
                container = client.containers.get(self.container_id)
                bits, _ = container.get_archive(path)
                # Reconstruct tar stream
                import io
                import tarfile

                stream = io.BytesIO(b"".join(bits))
                with tarfile.open(fileobj=stream) as tf:
                    member = tf.getmember(path.rsplit("/", maxsplit=1)[-1])
                    f = tf.extractfile(member)
                    return f.read() if f else b""
            except Exception:  # noqa: S110
                pass
        # CLI fallback
        cmd = f"docker exec {self.container_id} cat {path}"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        return stdout

    async def write_file(self, path: str, content: bytes | str) -> None:
        if not self.container_id:
            raise SandboxError("Container not running")
        client = self._get_client()
        if self._use_sdk and client is not None:
            try:
                container = client.containers.get(self.container_id)
                text = content.decode() if isinstance(content, bytes) else content
                # Use put_archive via tar
                import io
                import tarfile

                data = text.encode()
                tarstream = io.BytesIO()
                with tarfile.open(fileobj=tarstream, mode="w") as tf:
                    info = tarfile.TarInfo(name=Path(path).name)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))
                tarstream.seek(0)
                container.put_archive(str(Path(path).parent), tarstream.read())
                return
            except Exception:  # noqa: S110
                pass
        text = content.decode() if isinstance(content, bytes) else content
        # Escape safely
        safe_path = path.replace("'", "'\\''")
        cmd = f"docker exec {self.container_id} sh -c 'mkdir -p $(dirname {safe_path}) && cat > {safe_path}'"  # noqa: E501
        proc = await asyncio.create_subprocess_shell(cmd, stdin=asyncio.subprocess.PIPE)
        await proc.communicate(input=text.encode())

    async def exec_interactive(self, command: str) -> asyncio.subprocess.Popen:
        """PTY interactive execution. Returns a Popen for streaming I/O."""
        if not self.container_id:
            raise SandboxError("Container not running")
        # Use docker exec -i -t
        return await asyncio.create_subprocess_shell(
            f"docker exec -i -t {self.container_id} sh -c {command!r}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


__all__ = ["DockerSandbox"]
