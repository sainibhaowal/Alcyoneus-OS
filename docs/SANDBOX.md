# Sandboxes & Code Isolation — Production Guide

> **Safely execute untrusted code, run shell commands in interactive PTY terminals, and isolate AI workloads.**

---

## Overview

Alcyoneus OS provides a unified sandboxing layer for running untrusted LLM-generated code and shell sessions across local pseudo-terminals (PTYs), Docker containers, Kubernetes pods, and Cloud microVMs:

```
┌─────────────────────────────────────────────────────────┐
│                   Alcyoneus Agent                       │
└───────────────────────────┬─────────────────────────────┘
                            ▼
               ┌─────────────────────────┐
               │    BaseSandbox (API)    │
               └────────────┬────────────┘
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
┌──────────────────┐ ┌─────────────┐ ┌──────────────────┐
│  UnixPTYSandbox  │ │DockerSandbox│ │   Cloud Sandboxes│
│ (Pseudo-Terminal)│ │ (Container) │ │ (E2B, Modal, K8s)│
└──────────────────┘ └─────────────┘ └──────────────────┘
```

---

## 1. Local Interactive PTY Sandbox (`UnixPTYSandbox`)

When agents need to interact with terminal programs that expect a TTY (e.g. bash, interactive scripts, terminal output formatting), use `UnixPTYSandbox`:

```python
import asyncio
from alcyoneus.sandbox import UnixPTYSandbox, SandboxConfig

async def main():
    config = SandboxConfig(
        workdir="./workspace",
        timeout_seconds=30.0,
        env={"ENV": "sandbox", "PYTHONUNBUFFERED": "1"},
    )

    sandbox = UnixPTYSandbox(config)
    await sandbox.start()

    # Execute interactive commands
    result = await sandbox.exec("echo 'Hello from PTY' && uname -a")
    print(f"Exit code: {result.exit_code}")
    print(f"Output:\n{result.stdout}")

    await sandbox.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Features:
* **Interactive Terminal Emulation**: Uses `pty.openpty()` to provide a true pseudo-terminal.
* **Async Non-Blocking I/O**: Integrated directly with `asyncio.get_running_loop().add_reader()` and threaded fallback.
* **Timeout Enforcement**: Raises `ExecTimeoutError` if commands exceed configured duration.

---

## 2. Containerized Isolation (`DockerSandbox` & `K8sSandbox`)

For executing code with complete operating system and filesystem isolation:

### Docker Sandbox
```python
from alcyoneus.sandbox import DockerSandbox, SandboxConfig

config = SandboxConfig(
    image="python:3.11-slim",
    timeout_seconds=60.0,
    memory_limit="512m",
    cpu_limit="1.0",
)

docker_box = DockerSandbox(config)
await docker_box.start()

result = await docker_box.exec("python -c 'print(2 ** 100)'")
print(result.stdout)

await docker_box.stop()
```

### Kubernetes Sandbox (`K8sSandbox`)
Ideal for multi-tenant SaaS environments where each user session runs in an isolated ephemeral pod:
```python
from alcyoneus.sandbox import K8sSandbox, SandboxConfig

config = SandboxConfig(
    image="alcyoneus/sandbox-runner:latest",
    namespace="agent-sandboxes",
    timeout_seconds=120.0,
)

k8s_box = K8sSandbox(config)
await k8s_box.start()
```

---

## 3. Remote File Synchronization (`RemoteFileSync`)

Sync workspace files bidirectionally between the host application and isolated containers:

```python
from alcyoneus.sandbox import RemoteFileSync, SyncOptions

syncer = RemoteFileSync(
    sandbox=docker_box,
    options=SyncOptions(exclude=[".git", "__pycache__", "*.pyc"]),
)

# Upload project files to sandbox
await syncer.sync_to_sandbox(local_path="./src", remote_path="/app/src")

# Download generated artifacts
await syncer.sync_from_sandbox(remote_path="/app/output", local_path="./output")
```

---

## 4. Attaching Sandboxes to Tools

You can pair sandboxes with `@tool` handlers or custom `ToolNode` instances:

```python
from alcyoneus.core import StateGraph
from alcyoneus.sandbox import UnixPTYSandbox, SandboxConfig
from alcyoneus.utils.decorators import tool

sandbox = UnixPTYSandbox(SandboxConfig(workdir="/tmp/sandbox_run"))

@tool
async def run_bash(command: str) -> str:
    """Executes a command in an isolated PTY environment."""
    result = await sandbox.exec(command)
    if result.exit_code != 0:
        return f"Error (exit {result.exit_code}): {result.stderr or result.stdout}"
    return result.stdout
```

---

## 5. Summary of Built-In Sandboxes

| Class | Backend | Best For |
|---|---|---|
| `UnixPTYSandbox` | Local Unix PTY | Interactive CLI tools, fast execution without container overhead |
| `DockerSandbox` | Local Docker Daemon | Hard process and filesystem isolation on a single server |
| `K8sSandbox` | Kubernetes Pods | Scalable cloud clusters, auto-scaling ephemeral runner pods |
| `FirecrackerSandbox` | AWS Firecracker microVM | Multi-tenant untrusted execution with sub-second VM startup |
| `E2BSandbox` / `ModalSandbox` | Cloud Provider APIs | Serverless managed sandboxes without maintaining infrastructure |
