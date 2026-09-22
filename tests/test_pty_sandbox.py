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

"""Unit tests for UnixPTYSandbox non-blocking execution and capabilities."""

import asyncio
import tempfile
import unittest

from alcyoneus.sandbox.errors import ExecTimeoutError
from alcyoneus.sandbox.pty_sandbox import UnixPTYSandbox
from alcyoneus.sandbox.types import SandboxConfig


class TestUnixPTYSandbox(unittest.IsolatedAsyncioTestCase):
    async def test_pty_exec_basic(self):
        """Test standard command execution and stdout capture in PTY."""
        async with UnixPTYSandbox() as sb:
            result = await sb.exec("echo 'hello pty sandbox'")
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("hello pty sandbox", result.stdout)
            self.assertGreater(result.duration_seconds, 0)

    async def test_pty_exec_nonzero_exit(self):
        """Test command that exits with non-zero exit code."""
        sb = UnixPTYSandbox()
        result = await sb.exec("exit 42")
        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 42)

    async def test_pty_exec_timeout(self):
        """Test command that exceeds timeout raises ExecTimeoutError and terminates."""
        sb = UnixPTYSandbox()
        with self.assertRaises(ExecTimeoutError):
            await sb.exec("sleep 5", timeout=0.1)

    async def test_pty_exec_large_output(self):
        """Test reading large output without deadlocks or buffer truncation."""
        async with UnixPTYSandbox() as sb:
            result = await sb.exec("python3 -c \"print('A' * 50000)\"")
            self.assertTrue(result.success)
            self.assertIn("AAAAA", result.stdout)
            self.assertGreaterEqual(len(result.stdout), 50000)

    async def test_pty_nonblocking_event_loop(self):
        """Verify that asyncio event loop is not blocked by select() during execution."""
        sb = UnixPTYSandbox()
        ticks = 0
        stop_ticks = False

        async def ticker():
            nonlocal ticks
            while not stop_ticks:
                ticks += 1
                await asyncio.sleep(0.01)

        ticker_task = asyncio.create_task(ticker())
        res = await sb.exec("python3 -c \"import time; time.sleep(0.15); print('done')\"")
        stop_ticks = True
        await ticker_task

        self.assertTrue(res.success)
        self.assertIn("done", res.stdout)
        # In a 150ms command with 10ms sleep, ticker should yield at least 8-10 ticks
        self.assertGreaterEqual(ticks, 8)

    async def test_pty_read_and_write_file(self):
        """Test read_file and write_file methods on UnixPTYSandbox filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sb = UnixPTYSandbox(config=SandboxConfig(workdir=tmpdir))
            # Text write
            await sb.write_file("test.txt", "hello world")
            content = await sb.read_file("test.txt")
            self.assertEqual(content, b"hello world")

            # Binary write
            await sb.write_file("test.bin", b"\x00\x01\x02\xff")
            bin_content = await sb.read_file("test.bin")
            self.assertEqual(bin_content, b"\x00\x01\x02\xff")


if __name__ == "__main__":
    unittest.main()
