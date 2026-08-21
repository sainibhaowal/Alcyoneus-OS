"""Safe, workspace-scoped command execution for Alcyoneus OS.

The command tool deliberately uses ``shell=False``.  String commands are
tokenized with :mod:`shlex` and shell metacharacters are rejected; callers
that need a pipeline should model it as several explicit commands or provide
an approved host runner.  This avoids turning a tool call into an ambient
shell while still supporting normal executable invocations.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import signal
import time
from pathlib import Path
from typing import Any

from alcyoneus.utils.decorators import tool


_SHELL_TOKENS = {"|", ";", "&&", "||", ">", ">>", "<", "2>", "&", "`"}
_DEFAULT_TIMEOUT = 30.0
_MAX_TIMEOUT = 300.0
_DEFAULT_OUTPUT = 100_000
_MAX_OUTPUT = 1_000_000


def _root(config: dict[str, Any] | None) -> Path:
    cfg = config or {}
    return (
        Path(str(cfg.get("command_root") or cfg.get("workspace_root") or "."))
        .expanduser()
        .resolve()
    )


def _cwd(value: str | None, root: Path) -> Path:
    candidate = (
        (root / (value or ".")).resolve()
        if not Path(value or ".").is_absolute()
        else Path(value).resolve()
    )
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(f"cwd must stay inside the configured workspace root: {root}") from None
    if not candidate.is_dir():
        raise ValueError(f"cwd is not a directory: {candidate}")
    return candidate


def _argv(command: str | list[str]) -> list[str]:
    values = shlex.split(command) if isinstance(command, str) else [str(v) for v in command]
    if not values:
        raise ValueError("command is required")
    if any(
        token in _SHELL_TOKENS or any(ch in token for ch in ("|", ";", "&", "<", ">", "`"))
        for token in values
    ):
        raise ValueError("shell operators are not allowed; use an explicit argv command")
    return values


def _allowed(argv: list[str], config: dict[str, Any] | None) -> None:
    cfg = config or {}
    executable = Path(argv[0]).name
    allowed = cfg.get("allowed_commands")
    denied = cfg.get("denied_commands", [])
    if allowed is not None and executable not in set(map(str, allowed)):
        raise PermissionError(f"command is not allowlisted: {executable}")
    if executable in set(map(str, denied)):
        raise PermissionError(f"command is denied: {executable}")
    allowed_args = (cfg.get("allowed_command_args") or {}).get(executable)
    if allowed_args is not None:
        allowed_args = set(map(str, allowed_args))
        disallowed = [arg for arg in argv[1:] if arg not in allowed_args]
        if disallowed:
            raise PermissionError(f"command arguments are not allowlisted: {disallowed}")
    patterns = (cfg.get("denied_argument_patterns") or {}).get(executable, [])
    for argument in argv[1:]:
        if any(re.search(str(pattern), argument) for pattern in patterns):
            raise PermissionError(f"command argument denied by policy: {argument}")


async def _run(
    argv: list[str], cwd: Path, timeout: float, max_output: int, env: dict[str, str] | None
) -> dict[str, Any]:
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = await process.communicate()
    return {
        "command": argv,
        "cwd": str(cwd),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "stdout": stdout[:max_output].decode("utf-8", "replace"),
        "stderr": stderr[:max_output].decode("utf-8", "replace"),
        "output_truncated": len(stdout) > max_output or len(stderr) > max_output,
    }


@tool(
    name="shell_command",
    description="Run one allowlisted executable inside the configured workspace without a shell.",
    tags=["command", "execution", "workspace"],
    capabilities=["execute_commands"],
    metadata={"safe_by_default": True, "shell": False},
)
async def shell_command(
    command: str | list[str],
    cwd: str = ".",
    timeout: float = _DEFAULT_TIMEOUT,
    max_output_chars: int = _DEFAULT_OUTPUT,
    env: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Execute a command with workspace, timeout, output, and allowlist controls."""
    try:
        cfg = config or {}
        argv = _argv(command)
        _allowed(argv, cfg)
        root = _root(cfg)
        workdir = _cwd(cwd, root)
        safe_timeout = max(
            0.1, min(float(timeout), float(cfg.get("max_command_timeout", _MAX_TIMEOUT)))
        )
        limit = max(1, min(int(max_output_chars), int(cfg.get("max_command_output", _MAX_OUTPUT))))
        base_env = os.environ.copy() if cfg.get("inherit_environment", False) else {}
        if env:
            allowed_env = cfg.get("allowed_environment")
            if allowed_env is not None:
                unknown = set(env) - set(map(str, allowed_env))
                if unknown:
                    raise PermissionError(
                        f"environment variables are not allowlisted: {sorted(unknown)}"
                    )
            base_env.update({str(k): str(v) for k, v in env.items()})
        result = await _run(argv, workdir, safe_timeout, limit, base_env)
        audit = cfg.get("audit_tool_call")
        if audit:
            outcome = audit("shell_command", result)
            if asyncio.iscoroutine(outcome):
                await outcome
        return json.dumps(result)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return json.dumps({"error": str(exc), "tool": "shell_command"})
