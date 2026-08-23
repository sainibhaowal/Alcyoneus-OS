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

"""Advanced ShellTool with support for local, container, and hosted environments.

Hardened with:
- Command timeout (kills runaway processes)
- Working-directory scoping (runs inside a configured workspace)
- Destructive command deny-list (rm -rf, mkfs, dd, shutdown, ...)
- Output size limits
- Optional ``allowlist`` / ``denylist`` command policies
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from alcyoneus.sandbox.types import ExecResult


# Commands that are always refused in any environment. The tuple values are
# human-readable reasons surfaced in the tool result.
_DANGEROUS_COMMANDS: dict[str, str] = {
    "rm": "rm -rf can destroy data",
    "mkfs": "formatting disks is not allowed",
    "dd": "raw device writes are not allowed",
    "shutdown": "shutting down the host is not allowed",
    "reboot": "rebooting the host is not allowed",
    "halt": "halting the host is not allowed",
    "poweroff": "powering off the host is not allowed",
    "mkfs.ext4": "formatting disks is not allowed",
    "mkfs.xfs": "formatting disks is not allowed",
    "fdisk": "disk partitioning is not allowed",
    "parted": "disk partitioning is not allowed",
    "pvremove": "LVM destruction is not allowed",
    "vgremove": "LVM destruction is not allowed",
    "lvremove": "LVM destruction is not allowed",
    "gitpush": "not a command",
}

# Patterns that, when present in the command, trigger a refusal.
_DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-[^\s]*)?(-[^\s]*)?r", re.IGNORECASE), "recursive rm is not allowed"),
    (re.compile(r"\bmkfs(\.\w+)?\b", re.IGNORECASE), "formatting disks is not allowed"),
    (re.compile(r"\bdd\s+of=/dev/", re.IGNORECASE), "raw device writes are not allowed"),
    (re.compile(r"\b>:?\s*/dev/\w+", re.IGNORECASE), "redirecting to device files is not allowed"),
    (
        re.compile(r"\bchmod\s+[0-7]{3,4}\s+/", re.IGNORECASE),
        "chmod on absolute paths is restricted",
    ),
    (re.compile(r"\bcurl\s+[^\|]*\|?\s*sh\b", re.IGNORECASE), "pipe-to-shell is not allowed"),
    (re.compile(r"\bwget\s+[^\|]*\|?\s*sh\b", re.IGNORECASE), "pipe-to-shell is not allowed"),
    (
        re.compile(r"\b(base64|echo)\s+.*\|.*\s*(sh|bash)\b", re.IGNORECASE),
        "obfuscated shell execution is not allowed",
    ),
]

# Env vars that could leak secrets or alter behavior unexpectedly.
_FORBIDDEN_ENV_PREFIXES = ("AWS_", "GCP_", "AZURE_", "OPENAI_", "GOOGLE_", "GEMINI_", "KUBECONFIG")


@dataclass
class ShellResult:
    """Rich execution result of a shell command."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_ms: float = 0.0
    truncated: bool = False


class ShellPolicyError(RuntimeError):
    """Raised when a command violates the configured shell policy."""


@dataclass
class ShellPolicy:
    """Safety policy applied before executing any command."""

    timeout_seconds: float = 120.0
    max_output_chars: int = 200_000
    deny_dangerous: bool = True
    allowlist: Sequence[str] | None = None
    denylist: Sequence[str] = ()
    workspace_dir: str | None = None
    allow_network: bool = True
    max_memory_mb: int | None = None

    def check_command(self, command: str, workspace_dir: str | None = None) -> None:
        """Validate a command against this policy.

        Raises:
            ShellPolicyError: If the command violates the policy.
        """
        if not command.strip():
            raise ShellPolicyError("empty command")

        if self.deny_dangerous:
            argv = shlex.split(command)
            base = argv[0].split("/")[-1] if argv else ""
            if base in _DANGEROUS_COMMANDS:
                raise ShellPolicyError(f"command '{base}' is blocked: {_DANGEROUS_COMMANDS[base]}")
            for pattern, reason in _DANGEROUS_PATTERNS:
                if pattern.search(command):
                    raise ShellPolicyError(f"command blocked: {reason}")

        if self.denylist:
            argv = shlex.split(command)
            base = argv[0].split("/")[-1] if argv else ""
            if base in self.denylist:
                raise ShellPolicyError(f"command '{base}' is on the denylist")

        if self.allowlist:
            argv = shlex.split(command)
            base = argv[0].split("/")[-1] if argv else ""
            if base not in self.allowlist:
                raise ShellPolicyError(
                    f"command '{base}' is not on the allowlist; allowed: {', '.join(self.allowlist)}"  # noqa: E501
                )

        if not self.allow_network:
            argv = shlex.split(command)
            for token in argv:
                base = token.split("/")[-1]
                if base in (
                    "curl",
                    "wget",
                    "nc",
                    "ncat",
                    "telnet",
                    "ssh",
                    "scp",
                    "ftp",
                    "ping",
                    "nslookup",
                    "dig",
                ):
                    raise ShellPolicyError(f"network command '{base}' is disabled by policy")

        # Workspace scoping: reject commands that try to escape the workspace via
        # cd /, absolute-path redirects, or path traversal.
        if workspace_dir:
            if re.search(r"\bcd\s+(/|~|\.\.)", command):
                raise ShellPolicyError("cd outside the workspace is not allowed")
            if re.search(r"(>|>>)\s*/", command):
                raise ShellPolicyError("redirecting to absolute paths is not allowed")

    @property
    def cwd(self) -> str | None:
        return self.workspace_dir


class ShellToolEnvironment:
    """Base class for shell environments."""


class ShellToolLocalEnvironment(ShellToolEnvironment):
    """Local host system shell environment."""

    def __init__(self, cwd: str = ".") -> None:
        self.cwd = cwd


class ShellToolContainerEnvironment(ShellToolEnvironment):
    """Containerized shell environment backed by Docker/Podman."""

    def __init__(
        self,
        image: str = "python:3.11-slim",
        name: str | None = None,
        mounts: list[str] | None = None,
        env: dict[str, str] | None = None,
        workdir: str = "/workspace",
        memory: str = "512m",
        cpus: float = 1.0,
        network: str = "bridge",
        auto_remove: bool = True,
        runtime: str | None = None,
    ) -> None:
        self.image = image
        self.name = name or f"alcyoneus-shell-{uuid.uuid4().hex[:8]}"
        self.mounts = mounts or []
        self.env = env or {}
        self.workdir = workdir
        self.memory = memory
        self.cpus = cpus
        self.network = network
        self.auto_remove = auto_remove
        self.runtime = runtime
        self.container_id: str | None = None

    async def start(self) -> None:
        """Create and start the container."""
        cmd = ["docker", "run", "-d", "--name", self.name]
        if self.auto_remove:
            cmd.append("--rm")
        cmd += ["-w", self.workdir, "-m", self.memory, "--cpus", str(self.cpus)]
        if self.network and self.network != "host":
            cmd += ["--network", self.network]
        if self.runtime:
            cmd += ["--runtime", self.runtime]
        for m in self.mounts:
            cmd += ["-v", m]
        for k, v in self.env.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += [self.image, "tail", "-f", "/dev/null"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {stderr.decode()}")
        self.container_id = stdout.decode().strip()

    async def stop(self) -> None:
        """Stop and remove the container."""
        if self.container_id:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                self.container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            self.container_id = None

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        """Run a command inside the container."""
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            "-w",
            self.workdir,
            self.container_id or self.name,
            "sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise
        return ExecResult(
            exit_code=proc.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            duration_seconds=time.monotonic() - start,
        )


class ShellToolHostedEnvironment(ShellToolEnvironment):
    """Hosted shell environment backed by SSH or a remote execution API."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 22,
        user: str = "root",
        password: str | None = None,
        key_file: str | None = None,
        workdir: str = "~",
        api_url: str | None = None,
        api_token: str | None = None,
        api_provider: str = "generic",
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.key_file = key_file
        self.workdir = workdir
        self.api_url = api_url
        self.api_token = api_token
        self.api_provider = api_provider
        self._client: Any = None

    async def start(self) -> None:
        """Open connection (SSH) or session (HTTP API)."""
        if self.api_url:
            self._client = {
                "provider": self.api_provider,
                "url": self.api_url,
                "token": self.api_token,
            }
            return
        try:
            import asyncssh  # type: ignore

            self._client = await asyncssh.connect(
                self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                client_keys=[self.key_file] if self.key_file else None,
            )
        except ImportError:
            # Fallback to paramiko
            try:
                import paramiko  # type: ignore

                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # noqa: S507
                client.connect(
                    self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    key_filename=self.key_file,
                )
                self._client = client
            except ImportError:
                raise RuntimeError("Neither asyncssh nor paramiko installed")

    async def stop(self) -> None:
        """Close connection."""
        if self._client is None:
            return
        try:
            if hasattr(self._client, "close"):
                self._client.close()
        except Exception:  # noqa: S110
            pass
        self._client = None

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        """Run a command remotely."""
        start = time.monotonic()
        if self.api_url and isinstance(self._client, dict):
            # HTTP API execution
            import aiohttp

            async with aiohttp.ClientSession() as sess:
                headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
                async with sess.post(
                    f"{self.api_url}/exec",
                    json={"command": command, "timeout": timeout, "cwd": self.workdir},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout or 60),
                ) as resp:
                    data = await resp.json()
                    return ExecResult(
                        exit_code=data.get("exit_code", 0),
                        stdout=data.get("stdout", ""),
                        stderr=data.get("stderr", ""),
                        duration_seconds=time.monotonic() - start,
                    )
        if hasattr(self._client, "run"):
            # asyncssh
            proc = await self._client.run(command, term_type=None)
            return ExecResult(
                exit_code=proc.exit_status or 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=time.monotonic() - start,
            )
        # paramiko
        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return ExecResult(
            exit_code=exit_code,
            stdout=stdout.read().decode(errors="replace"),
            stderr=stderr.read().decode(errors="replace"),
            duration_seconds=time.monotonic() - start,
        )


class ShellTool:
    """Advanced shell tool supporting environment isolation policies."""

    def __init__(
        self,
        environment: ShellToolEnvironment | None = None,
        policy: ShellPolicy | None = None,
    ) -> None:
        self.environment = environment or ShellToolLocalEnvironment()
        self.policy = policy or ShellPolicy()

    @property
    def _workspace_dir(self) -> str | None:
        if self.policy.workspace_dir:
            return self.policy.workspace_dir
        if isinstance(self.environment, ShellToolLocalEnvironment):
            return os.path.abspath(self.environment.cwd)
        return None

    def _sanitize_env(self) -> dict[str, str]:
        """Pass through a filtered environment (never leak credential vars)."""
        env = {k: v for k, v in os.environ.items() if not k.startswith(_FORBIDDEN_ENV_PREFIXES)}
        return env

    async def run(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
        max_output_chars: int | None = None,
    ) -> ShellResult:
        """Run a command in the configured shell environment.

        Args:
            command: The shell command to execute.
            timeout_seconds: Override policy timeout for this call.
            max_output_chars: Override policy output cap for this call.

        Returns:
            A ShellResult with exit code, stdout, stderr and metadata.
        """
        import time

        ws = self._workspace_dir
        self.policy.check_command(command, workspace_dir=ws)

        timeout = timeout_seconds if timeout_seconds is not None else self.policy.timeout_seconds
        max_out = max_output_chars if max_output_chars is not None else self.policy.max_output_chars

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=ws,
                env=self._sanitize_env(),
            )
        except FileNotFoundError as err:
            return ShellResult(
                command=command,
                exit_code=127,
                stdout="",
                stderr=str(err),
                duration_ms=0.0,
            )

        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            timed_out = True
            proc.kill()
            stdout, stderr = await proc.communicate()

        duration_ms = (time.monotonic() - start) * 1000.0
        out_text = stdout.decode(errors="replace")
        err_text = stderr.decode(errors="replace")
        truncated = len(out_text) > max_out or len(err_text) > max_out
        if truncated:
            out_text = out_text[:max_out]
            err_text = err_text[:max_out]

        return ShellResult(
            command=command,
            exit_code=proc.returncode or 0,
            stdout=out_text,
            stderr=err_text,
            timed_out=timed_out,
            duration_ms=duration_ms,
            truncated=truncated,
        )

    async def run_script(self, script: str, interpreter: str = "bash") -> ShellResult:
        """Run a multi-line script via the configured interpreter."""
        if interpreter not in ("bash", "sh", "python3", "python"):
            raise ShellPolicyError(f"interpreter '{interpreter}' is not allowed")
        escaped = script.replace("'", "'\\''")
        return await self.run(f"{interpreter} -c '{escaped}'")

    def to_dict(self) -> dict[str, Any]:
        """Serializable representation for tool registration."""
        return {
            "name": "shell",
            "description": "Run shell commands in a sandboxed local environment.",
            "policy": {
                "timeout_seconds": self.policy.timeout_seconds,
                "deny_dangerous": self.policy.deny_dangerous,
                "allowlist": list(self.policy.allowlist or []),
                "denylist": list(self.policy.denylist),
                "workspace_dir": self.policy.workspace_dir,
            },
        }


__all__ = [
    "ShellPolicy",
    "ShellPolicyError",
    "ShellResult",
    "ShellTool",
    "ShellToolContainerEnvironment",
    "ShellToolEnvironment",
    "ShellToolLocalEnvironment",
]
