"""System health and diagnostic suite for Alcyoneus OS."""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import sys
from typing import Any

from rich.console import Console
from rich.table import Table


OPTIONAL_DEPENDENCIES: list[tuple[str, str, str]] = [
    ("google-genai", "google.genai", "Google Gemini integration and Realtime multimodal"),
    ("openai", "openai", "OpenAI models and Realtime audio API"),
    ("fastmcp", "fastmcp", "Model Context Protocol (MCP) server & client runtime"),
    ("mcp", "mcp", "Core Model Context Protocol standard library"),
    ("qdrant-client", "qdrant_client", "Qdrant vector store and hybrid neural search"),
    ("asyncpg", "asyncpg", "High-performance PostgreSQL checkpointer"),
    ("redis", "redis.asyncio", "Redis checkpointer and publisher"),
    ("piexif", "piexif", "Image EXIF metadata processing and analysis"),
    ("playwright", "playwright", "Headless browser automation tool"),
    ("aiokafka", "aiokafka", "Apache Kafka event publisher"),
    ("aio-pika", "aio_pika", "RabbitMQ AMQP event publisher"),
    ("mem0ai", "mem0", "Mem0 long-term memory engine"),
]

API_CREDENTIALS: list[tuple[str, str]] = [
    ("OPENAI_API_KEY", "OpenAI API"),
    ("GEMINI_API_KEY", "Google Gemini API"),
    ("ANTHROPIC_API_KEY", "Anthropic API"),
    ("QDRANT_API_KEY", "Qdrant Cloud"),
]


def check_python_environment() -> dict[str, Any]:
    """Validate Python version and runtime environment."""
    version_tuple = sys.version_info
    is_valid = version_tuple >= (3, 12)
    return {
        "name": "Python Version",
        "status": "PASS" if is_valid else "FAIL",
        "detail": f"{platform.python_version()} ({sys.executable})",
        "recommended": "Python >= 3.12 is required for full feature compatibility.",
    }


def check_dependencies() -> list[dict[str, Any]]:
    """Check status of optional dependencies."""
    results: list[dict[str, Any]] = []
    for pkg_name, import_module, description in OPTIONAL_DEPENDENCIES:
        try:
            mod = importlib.import_module(import_module)
            ver = getattr(mod, "__version__", "installed")
            results.append({
                "package": pkg_name,
                "status": "INSTALLED",
                "version": str(ver),
                "description": description,
            })
        except ImportError:
            results.append({
                "package": pkg_name,
                "status": "MISSING",
                "version": None,
                "description": description,
            })
    return results


def check_api_credentials() -> list[dict[str, Any]]:
    """Check presence of API keys without exposing secrets."""
    results = []
    for env_var, service in API_CREDENTIALS:
        val = os.getenv(env_var)
        if val and not val.startswith("dummy-"):
            masked = f"{val[:4]}...{val[-4:]}" if len(val) >= 8 else "configured"
            results.append({
                "variable": env_var,
                "service": service,
                "status": "CONFIGURED",
                "detail": masked,
            })
        else:
            results.append({
                "variable": env_var,
                "service": service,
                "status": "NOT SET",
                "detail": "Optional: needed for live model/service calls",
            })
    return results


def check_docker_daemon() -> dict[str, Any]:
    """Check Docker daemon availability for sandboxing."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return {
            "name": "Docker Daemon",
            "status": "NOT INSTALLED",
            "detail": "'docker' binary not found in PATH",
            "recommended": "Install Docker if using DockerSandbox for code execution.",
        }

    import subprocess  # nosec: B404
    try:
        res = subprocess.run(  # noqa: S603
            [docker_bin, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        if res.returncode == 0:
            return {
                "name": "Docker Daemon",
                "status": "ONLINE",
                "detail": "Docker daemon reachable and responsive",
                "recommended": "Ready for container sandboxing",
            }
        else:
            return {
                "name": "Docker Daemon",
                "status": "OFFLINE",
                "detail": "Docker installed but daemon is not running",
                "recommended": "Start Docker service (e.g. systemctl start docker)",
            }
    except Exception as exc:
        return {
            "name": "Docker Daemon",
            "status": "ERROR",
            "detail": f"Failed to check docker daemon: {exc}",
            "recommended": "Ensure current user is in 'docker' group",
        }


def check_pty_subsystem() -> dict[str, Any]:
    """Check PTY availability for interactive terminal sandbox."""
    try:
        import pty
        import tty  # noqa: F401

        master, slave = pty.openpty()
        os.close(master)
        os.close(slave)
        return {
            "name": "PTY Subsystem",
            "status": "AVAILABLE",
            "detail": "PTY master/slave pair allocated successfully",
            "recommended": "Full support for interactive PTY terminal sandboxing",
        }
    except Exception as exc:
        return {
            "name": "PTY Subsystem",
            "status": "UNAVAILABLE",
            "detail": f"PTY allocation failed: {exc}",
            "recommended": "PTY is Unix-specific; Windows requires ConPTY",
        }


def run_diagnostics() -> dict[str, Any]:
    """Execute full diagnostic suite and return structured data."""
    return {
        "python": check_python_environment(),
        "docker": check_docker_daemon(),
        "pty": check_pty_subsystem(),
        "dependencies": check_dependencies(),
        "credentials": check_api_credentials(),
    }


def render_diagnostics_table(data: dict[str, Any], console: Console) -> None:
    """Render diagnostic suite results in Rich tables."""
    console.print("[bold cyan]🔍 Alcyoneus OS — System Health & Diagnostics[/bold cyan]\n")

    # 1. Core Runtime Environment
    env_table = Table(title="[bold]Core Runtime Environment[/bold]", title_justify="left")
    env_table.add_column("Component", style="bold cyan", no_wrap=True)
    env_table.add_column("Status", no_wrap=True)
    env_table.add_column("Detail")
    env_table.add_column("Recommendation", style="dim")

    py = data["python"]
    py_style = "[green]PASS[/green]" if py["status"] == "PASS" else "[red]FAIL[/red]"
    env_table.add_row(py["name"], py_style, py["detail"], py["recommended"])

    pty_info = data["pty"]
    pty_style = "[green]AVAILABLE[/green]" if pty_info["status"] == "AVAILABLE" else "[yellow]UNAVAILABLE[/yellow]"
    env_table.add_row(pty_info["name"], pty_style, pty_info["detail"], pty_info["recommended"])

    doc = data["docker"]
    if doc["status"] == "ONLINE":
        doc_style = "[green]ONLINE[/green]"
    elif doc["status"] == "OFFLINE":
        doc_style = "[yellow]OFFLINE[/yellow]"
    else:
        doc_style = "[dim]NOT FOUND[/dim]"
    env_table.add_row(doc["name"], doc_style, doc["detail"], doc["recommended"])

    console.print(env_table)
    console.print("")

    # 2. Optional Dependencies
    dep_table = Table(title="[bold]Ecosystem & Optional Dependencies[/bold]", title_justify="left")
    dep_table.add_column("Package", style="bold cyan")
    dep_table.add_column("Status", no_wrap=True)
    dep_table.add_column("Installed Version", no_wrap=True)
    dep_table.add_column("Feature Description", style="dim")

    for dep in data["dependencies"]:
        status_str = "[green]INSTALLED[/green]" if dep["status"] == "INSTALLED" else "[dim]MISSING[/dim]"
        ver_str = dep["version"] or "-"
        dep_table.add_row(dep["package"], status_str, ver_str, dep["description"])

    console.print(dep_table)
    console.print("")

    # 3. API Credentials
    cred_table = Table(title="[bold]API Credentials & Providers[/bold]", title_justify="left")
    cred_table.add_column("Environment Variable", style="bold cyan")
    cred_table.add_column("Service")
    cred_table.add_column("Status", no_wrap=True)
    cred_table.add_column("Detail", style="dim")

    for cred in data["credentials"]:
        status_str = "[green]CONFIGURED[/green]" if cred["status"] == "CONFIGURED" else "[dim]NOT SET[/dim]"
        cred_table.add_row(cred["variable"], cred["service"], status_str, cred["detail"])

    console.print(cred_table)
    console.print("")
