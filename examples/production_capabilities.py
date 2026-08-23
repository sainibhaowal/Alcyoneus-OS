"""Safe production capability wiring for Alcyoneus OS.

This example keeps host-specific concerns explicit: command policy, human
question delivery, image provider, media storage, and child-agent execution
are injected through the run config rather than hidden globals.
"""

from __future__ import annotations

from alcyoneus.core.graph.tool_node import ToolNode
from alcyoneus.prebuilt.tools import (
    BrowserController,
    BrowserPolicy,
    InMemoryCalendarProvider,
    Scheduler,
    ask_question,
    browser_click,
    browser_extract,
    browser_fill,
    browser_navigate,
    browser_screenshot,
    calendar_create_event,
    calendar_delete_event,
    calendar_list_events,
    calendar_update_event,
    cancel_scheduled_job,
    edit_file,
    finish,
    generate_image,
    list_directory,
    list_scheduled_jobs,
    schedule_job,
    shell_command,
    start_subagent,
)


def build_production_tool_node() -> ToolNode:
    """Build an additive ToolNode containing the new guarded capabilities."""
    return ToolNode(
        [
            shell_command,
            ask_question,
            list_directory,
            edit_file,
            generate_image,
            start_subagent,
            finish,
            browser_navigate,
            browser_click,
            browser_fill,
            browser_extract,
            browser_screenshot,
            calendar_create_event,
            calendar_update_event,
            calendar_delete_event,
            calendar_list_events,
            schedule_job,
            cancel_scheduled_job,
            list_scheduled_jobs,
        ]
    )


def production_config(workspace_root: str) -> dict:
    """Return a deny-by-default host configuration template."""
    return {
        "workspace_root": workspace_root,
        "command_root": workspace_root,
        "allowed_commands": ["python3", "pytest", "ruff", "git"],
        "denied_commands": ["sudo", "mount", "umount", "shutdown"],
        "inherit_environment": False,
        "max_command_timeout": 120.0,
        "max_command_output": 200_000,
        # Inject question_broker, image_generator/media_store, and
        # subagent_runner from the application host.
        # Also inject browser_controller, calendar_provider, and scheduler.
    }


def production_integrations(workspace_root: str) -> dict:
    """Build safe local defaults; replace providers with production services."""
    return {
        "browser_controller": BrowserController(
            policy=BrowserPolicy(allowed_domains={"example.com"})
        ),
        "calendar_provider": InMemoryCalendarProvider(),
        "scheduler": Scheduler(
            f"{workspace_root}/alcyoneus-scheduler.sqlite",
            handlers={},  # register application-owned handlers before start()
        ),
    }
