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

"""Interactive Terminal Prompts and Human-in-the-Loop (HITL) Hooks for Alcyoneus OS.

Provides terminal spinners, async CLI inputs, tool confirmation hooks, and ask_question handlers.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any


async def async_input(prompt: str = "") -> str:
    """Asynchronously reads input from stdin without blocking the main event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


class Spinner:
    """ASCII Terminal Spinner for displaying async task progress."""

    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Processing...") -> None:
        self.message = message
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> Spinner:
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join()
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _spin(self) -> None:
        idx = 0
        while self._running:
            frame = self._SPINNER_FRAMES[idx % len(self._SPINNER_FRAMES)]
            sys.stdout.write(f"\r{frame} {self.message}")
            sys.stdout.flush()
            time.sleep(0.08)
            idx += 1

    def __enter__(self) -> Spinner:
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


class ToolConfirmationHook:
    """Interactive CLI hook that prompts user for approval before calling an ASK_USER tool."""

    def __init__(self, input_fn: Callable[[str], str] | None = None) -> None:
        self._input_fn = input_fn or input

    def __call__(self, tool_name: str, args: dict[str, Any]) -> bool:
        print(f"\n⚠️  [Policy Confirmation] Tool '{tool_name}' requires approval.")
        print(f"   Arguments: {args}")
        try:
            resp = self._input_fn("Allow tool execution? [y/N]: ").strip().lower()
            return resp in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            print("\nRejected execution.")
            return False


class AskQuestionHook:
    """Interactive hook handling ask_question tools."""

    def __init__(self, input_fn: Callable[[str], str] | None = None) -> None:
        self._input_fn = input_fn or input

    def __call__(self, question: str, options: Sequence[str] | None = None) -> str:
        print(f"\n❓ {question}")
        if options:
            for idx, opt in enumerate(options, 1):
                print(f"  [{idx}] {opt}")
        try:
            ans = self._input_fn("Your answer: ").strip()
            if options and ans.isdigit():
                val = int(ans)
                if 1 <= val <= len(options):
                    return options[val - 1]
            return ans
        except (EOFError, KeyboardInterrupt):
            return ""


async def run_interactive_loop(
    prompt_fn: Callable[[], str | None],
    process_fn: Callable[[str], Any],
) -> None:
    """Runs an interactive CLI loop prompting user for continuous input."""
    while True:
        try:
            user_msg = prompt_fn()
            if user_msg is None or user_msg.strip().lower() in ("exit", "quit"):
                print("Exiting interactive session.")
                break
            if not user_msg.strip():
                continue
            res = process_fn(user_msg)
            if asyncio.iscoroutine(res):
                await res
        except (EOFError, KeyboardInterrupt):
            print("\nSession interrupted.")
            break


__all__ = [
    "AskQuestionHook",
    "Spinner",
    "ToolConfirmationHook",
    "async_input",
    "run_interactive_loop",
]
