# Copyright 2026 Alcyoneus Authors

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from alcyoneus import (
    Decision,
    Policy,
    PolicyEngine,
    allow,
    deny,
    ask_user,
    allow_all,
    deny_all,
    confirm_run_command,
    workspace_only,
)


class TestPolicyEngine(unittest.IsolatedAsyncioTestCase):

    async def test_policy_priority_tiers(self):
        policies = [
            allow_all(),                                            # tier 9
            deny("shell_command"),                                  # tier 1
            ask_user("view_file", handler=lambda name, args: True), # tier 2
            allow("read_file"),                                     # tier 3
        ]

        engine = PolicyEngine(policies)

        dec, pol = await engine.evaluate("shell_command", {})
        self.assertEqual(dec, Decision.DENY)

        dec, pol = await engine.evaluate("view_file", {})
        self.assertEqual(dec, Decision.ASK_USER)

        dec, pol = await engine.evaluate("read_file", {})
        self.assertEqual(dec, Decision.APPROVE)

        dec, pol = await engine.evaluate("search_web", {})
        self.assertEqual(dec, Decision.APPROVE)

    async def test_workspace_only_sandboxing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            policies = workspace_only([tmp_path])
            engine = PolicyEngine(policies)

            inside_file = str(tmp_path / "test.txt")
            dec, pol = await engine.evaluate("read_file", {"path": inside_file})
            self.assertEqual(dec, Decision.APPROVE)

            outside_file = "/etc/passwd"
            dec, pol = await engine.evaluate("read_file", {"path": outside_file})
            self.assertEqual(dec, Decision.DENY)

    async def test_confirm_run_command_policy(self):
        policies = confirm_run_command()
        engine = PolicyEngine(policies)

        dec, _ = await engine.evaluate("shell_command", {})
        self.assertEqual(dec, Decision.DENY)

        dec, _ = await engine.evaluate("read_file", {})
        self.assertEqual(dec, Decision.APPROVE)


if __name__ == "__main__":
    unittest.main()
