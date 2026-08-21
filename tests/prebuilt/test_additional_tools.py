"""Regression tests for additive built-in capabilities."""

from __future__ import annotations

import json
import asyncio
from pathlib import Path

import pytest

from alcyoneus.prebuilt.tools.command import shell_command
from alcyoneus.prebuilt.tools.directory import list_directory
from alcyoneus.prebuilt.tools.edit import edit_file
from alcyoneus.prebuilt.tools.interaction import HumanQuestionBroker, ask_question
from alcyoneus.prebuilt.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_shell_command_is_workspace_scoped(tmp_path: Path):
    result = json.loads(
        await shell_command(["python3", "-c", "print('ok')"], config={"workspace_root": str(tmp_path)})
    )
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "ok"


@pytest.mark.asyncio
async def test_shell_command_rejects_shell_operators(tmp_path: Path):
    result = json.loads(
        await shell_command("echo ok | cat", config={"workspace_root": str(tmp_path)})
    )
    assert "shell operators" in result["error"]


def test_directory_listing_and_atomic_edit(tmp_path: Path):
    target = tmp_path / "note.txt"
    target.write_text("hello\n", encoding="utf-8")
    listing = json.loads(list_directory(config={"workspace_root": str(tmp_path)}))
    assert listing["entries"][0]["name"] == "note.txt"
    edited = json.loads(
        edit_file(
            "note.txt",
            old_text="hello",
            new_text="world",
            config={"workspace_root": str(tmp_path)},
        )
    )
    assert edited["status"] == "edited"
    assert target.read_text(encoding="utf-8") == "world\n"


@pytest.mark.asyncio
async def test_question_uses_host_broker():
    async def broker(request):
        assert request["question"] == "Continue?"
        return {"answer": "yes"}

    result = json.loads(
        await ask_question("Continue?", options=["yes", "no"], config={"question_broker": broker})
    )
    assert result == {"answer": "yes", "status": "answered"}


@pytest.mark.asyncio
async def test_question_broker_can_resume_pending_request():
    broker = HumanQuestionBroker()
    pending = asyncio.create_task(
        ask_question("Approve?", config={"question_broker": broker, "question_id": "q-1"})
    )
    await asyncio.sleep(0)
    broker.answer("q-1", "approved")
    assert json.loads(await pending)["answer"] == "approved"


def test_tool_registry_describes_tools():
    registry = ToolRegistry()

    def example(value: str):
        """Example tool."""

    registry.register(example)
    descriptor = registry.descriptor("example")
    assert descriptor.name == "example"
    assert "value" in descriptor.schema["properties"]
