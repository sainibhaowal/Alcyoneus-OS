"""Regression tests for browser policy, calendar, and scheduling additions."""

from __future__ import annotations

import asyncio
import json

import pytest

from alcyoneus.prebuilt.tools.browser import BrowserPolicy
from alcyoneus.prebuilt.tools.calendar import InMemoryCalendarProvider, calendar_create_event, calendar_list_events
from alcyoneus.prebuilt.tools.scheduler import Scheduler


def test_browser_policy_blocks_unsafe_navigation():
    policy = BrowserPolicy(allowed_domains={"example.com"})
    policy.check_url("https://example.com/path")
    with pytest.raises(PermissionError):
        policy.check_url("https://not-example.com")
    with pytest.raises(PermissionError):
        policy.check_url("http://example.com")


@pytest.mark.asyncio
async def test_calendar_provider_and_tools():
    provider = InMemoryCalendarProvider()
    config = {"calendar_provider": provider}
    created = json.loads(await calendar_create_event(
        "work", "Design review", "2026-07-21T10:00:00+00:00", "2026-07-21T11:00:00+00:00", config=config
    ))
    events = json.loads(await calendar_list_events(
        "work", "2026-07-21T00:00:00+00:00", "2026-07-22T00:00:00+00:00", config=config
    ))
    assert created["title"] == "Design review"
    assert len(events["events"]) == 1


@pytest.mark.asyncio
async def test_scheduler_executes_and_persists_job(tmp_path):
    calls: list[dict] = []

    async def handler(payload):
        calls.append(payload)

    scheduler = Scheduler(str(tmp_path / "jobs.sqlite"), handlers={"test": handler}, poll_interval=0.02)
    await scheduler.start()
    result = await scheduler.schedule("test", {"value": 42}, interval_seconds=0.05)
    for _ in range(30):
        if calls:
            break
        await asyncio.sleep(0.02)
    assert calls == [{"value": 42}]
    assert await scheduler.cancel(result["job_id"])
    jobs = await scheduler.list_jobs()
    assert jobs[0]["status"] == "cancelled"
    await scheduler.stop()
