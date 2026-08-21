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

"""Manages and executes triggers based on background tasks or event streams.

Supports both:
1. Event-based triggers (TriggerConfig, TriggerEvent, emit_event)
2. Background decorator triggers (@trigger, TriggerContext, interval/file-watch)
"""

from __future__ import annotations

import asyncio
import logging
import typing as t
from collections.abc import Sequence

from alcyoneus.core.triggers import triggers as triggers_module
from alcyoneus.core.triggers.event_triggers import (
    TriggerConfig,
    TriggerEvent,
)


logger = logging.getLogger("alcyoneus.triggers")


class QueueTriggerConnection:
    """Default in-memory queue connection for triggers."""

    def __init__(self, queue: asyncio.Queue[str] | None = None) -> None:
        self.queue = queue or asyncio.Queue()

    async def send_trigger_notification(self, content: str) -> None:
        await self.queue.put(content)


class TriggerRunner:
    """Manages and executes triggers based on events or background tasks.

    Can be initialized with a TriggerConfig (for event-based triggers) or a sequence of
    decorator triggers.
    """

    def __init__(
        self,
        config_or_triggers: TriggerConfig | Sequence[triggers_module.Trigger],
        connection: t.Any | None = None,
    ):
        self._connection = connection or QueueTriggerConnection()
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

        if isinstance(config_or_triggers, TriggerConfig):
            self._config = config_or_triggers
            self._background_triggers: list[triggers_module.Trigger] = []
        else:
            self._config = TriggerConfig(triggers=[])
            self._background_triggers = list(config_or_triggers)

        self._event_queue: asyncio.Queue[TriggerEvent] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def __aenter__(self) -> TriggerRunner:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start processing trigger events and background triggers."""
        if self._running:
            return

        self._running = True

        # Start event-based worker task
        self._worker_task = asyncio.create_task(self._process_events())

        # Start background decorator triggers
        for trig in self._background_triggers:
            ctx = triggers_module.TriggerContext(connection=self._connection)
            trig_name = getattr(trig, "__name__", "unknown")
            task = asyncio.create_task(
                self._run_background_trigger(trig, ctx),
                name=f"alcyoneus-trigger-{trig_name}",
            )
            self._tasks.append(task)

        logger.info("Trigger runner started")

    async def stop(self) -> None:
        """Stop processing trigger events and cancel background triggers."""
        if not self._running:
            return

        self._running = False

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        logger.info("Trigger runner stopped")

    @property
    def is_running(self) -> bool:
        """True if trigger processing is active."""
        return self._running or any(not task.done() for task in self._tasks)

    async def _process_events(self) -> None:
        """Process events from the queue and execute matching event triggers."""
        while self._running:
            try:
                event = await self._event_queue.get()
                await self._handle_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error processing trigger event: {e}")

    async def _handle_event(self, event: TriggerEvent) -> None:
        """Handle a single event by executing matching triggers."""
        if not self._config.enabled:
            return

        for trig in self._config.triggers:
            if trig.matches(event):
                await trig.execute(event)

    async def emit_event(self, event: TriggerEvent) -> None:
        """Emit an event for trigger processing."""
        if not self._running:
            logger.warning("Trigger runner not running, event ignored")
            return

        await self._event_queue.put(event)

    def emit_event_sync(self, event: TriggerEvent) -> None:
        """Emit an event synchronously."""
        if not self._running:
            logger.warning("Trigger runner not running, event ignored")
            return

        try:
            asyncio.create_task(self._event_queue.put(event))
        except RuntimeError:
            pass

    @staticmethod
    async def _run_background_trigger(
        trig: triggers_module.Trigger,
        ctx: triggers_module.TriggerContext,
    ) -> None:
        trig_name = getattr(trig, "__name__", repr(trig))
        try:
            await trig(ctx)
        except asyncio.CancelledError:
            logger.info(f"Trigger '{trig_name}' cancelled.")
            raise
        except Exception as e:
            logger.exception(f"Trigger '{trig_name}' failed with unhandled exception: {e}")


__all__ = ["QueueTriggerConnection", "TriggerRunner"]
