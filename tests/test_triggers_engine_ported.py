# Copyright 2026 Alcyoneus Authors

import asyncio
import unittest

from alcyoneus import (
    TriggerRunner,
    QueueTriggerConnection,
    trigger,
    TriggerContext,
    every,
)


class TestTriggerEngine(unittest.IsolatedAsyncioTestCase):

    async def test_trigger_decorator(self):
        @trigger
        async def sample_trigger(ctx: TriggerContext):
            pass

        self.assertTrue(getattr(sample_trigger, "__is_trigger__", False))

        with self.assertRaises(ValueError):
            @trigger
            def sync_trigger(ctx: TriggerContext):
                pass

    async def test_trigger_runner_interval(self):
        conn = QueueTriggerConnection()

        async def my_callback(ctx: TriggerContext):
            await ctx.send("ping")

        interval_trig = every(0.05, my_callback)

        async with TriggerRunner([interval_trig], connection=conn) as runner:
            self.assertTrue(runner.is_running)
            msg = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
            self.assertEqual(msg, "ping")

        self.assertFalse(runner.is_running)


if __name__ == "__main__":
    unittest.main()
