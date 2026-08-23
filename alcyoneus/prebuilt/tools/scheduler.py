"""Durable, timezone-aware Alcyoneus OS job scheduler.

The scheduler uses SQLite from the standard library, supports one-shot,
interval, and five-field cron jobs, retries with exponential backoff, and
survives process restarts.  Persisted jobs reference named handlers supplied
by the host instead of serializing arbitrary Python code.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from alcyoneus.utils.decorators import tool


Handler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _next_cron(expression: str, after: datetime, zone: ZoneInfo) -> datetime:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron must contain five fields: minute hour day month weekday")
    allowed = []
    for field in fields:
        values: set[int] = set()
        for part in field.split(","):
            if part == "*":
                values.add(-1)
            elif part.startswith("*/"):
                step = int(part[2:])
                values.update(range(0, 60, step))
            elif "-" in part:
                bounds, _, step_text = part.partition("/")
                first, last = (int(value) for value in bounds.split("-", 1))
                step = int(step_text) if step_text else 1
                values.update(range(first, last + 1, step))
            else:
                values.add(int(part))
        allowed.append(values)
    candidate = after.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 366):
        values = [
            candidate.minute,
            candidate.hour,
            candidate.day,
            candidate.month,
            (candidate.weekday() + 1) % 7,
        ]
        if all(-1 in allowed[i] or values[i] in allowed[i] for i in range(5)):
            return candidate.astimezone(UTC)
        candidate += timedelta(minutes=1)
    raise ValueError("cron expression did not produce a time within one year")


class Scheduler:
    """Persistent scheduler with named, application-owned handlers."""

    def __init__(
        self,
        database: str = ":memory:",
        *,
        handlers: dict[str, Handler] | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self.database = database
        self.handlers = handlers or {}
        self.poll_interval = max(0.05, poll_interval)
        self._db: sqlite3.Connection | None = None
        self._task: asyncio.Task[Any] | None = None
        self._stop = asyncio.Event()

    def _connection(self) -> sqlite3.Connection:
        if self._db is None:
            if self.database != ":memory:":
                Path(self.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.database, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("""CREATE TABLE IF NOT EXISTS alcyoneus_jobs (
                id TEXT PRIMARY KEY, handler TEXT NOT NULL, payload TEXT NOT NULL,
                schedule_type TEXT NOT NULL, schedule_value TEXT NOT NULL,
                timezone TEXT NOT NULL, next_run TEXT NOT NULL, status TEXT NOT NULL,
                retries INTEGER NOT NULL DEFAULT 0, max_retries INTEGER NOT NULL DEFAULT 3,
                backoff_seconds REAL NOT NULL DEFAULT 2, last_error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            self._db.commit()
        return self._db

    async def start(self) -> None:
        self._connection()
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="alcyoneus-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        if self._db is not None:
            self._db.close()
            self._db = None

    async def schedule(
        self,
        handler: str,
        payload: dict[str, Any],
        *,
        run_at: str | None = None,
        interval_seconds: float | None = None,
        cron: str | None = None,
        timezone_name: str = "UTC",
        max_retries: int = 3,
        backoff_seconds: float = 2.0,
    ) -> dict[str, Any]:
        if handler not in self.handlers:
            raise ValueError(f"unknown scheduler handler: {handler}")
        modes = [run_at is not None, interval_seconds is not None, cron is not None]
        if sum(modes) != 1:
            raise ValueError("provide exactly one of run_at, interval_seconds, or cron")
        zone = ZoneInfo(timezone_name)
        now = datetime.now(UTC)
        if run_at:
            next_run = datetime.fromisoformat(run_at.replace("Z", "+00:00"))
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=zone)
        elif interval_seconds is not None:
            if interval_seconds <= 0:
                raise ValueError("interval_seconds must be positive")
            next_run = now + timedelta(seconds=interval_seconds)
        else:
            _next_cron(str(cron), now, zone)
            next_run = _next_cron(str(cron), now, zone)
        job_id = str(uuid.uuid4())
        timestamp = _now()
        db = self._connection()
        db.execute(
            "INSERT INTO alcyoneus_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                handler,
                json.dumps(payload),
                "once" if run_at else "interval" if interval_seconds else "cron",
                str(run_at or interval_seconds or cron),
                timezone_name,
                next_run.astimezone(UTC).isoformat(),
                "active",
                0,
                max(0, int(max_retries)),
                max(0.1, float(backoff_seconds)),
                None,
                timestamp,
                timestamp,
            ),
        )
        db.commit()
        return {
            "job_id": job_id,
            "next_run": next_run.astimezone(UTC).isoformat(),
            "status": "active",
        }

    async def cancel(self, job_id: str) -> bool:
        db = self._connection()
        changed = db.execute(
            "UPDATE alcyoneus_jobs SET status='cancelled', updated_at=? WHERE id=? AND status='active'",  # noqa: E501
            (_now(), job_id),
        ).rowcount
        db.commit()
        return bool(changed)

    async def list_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
        db = self._connection()
        rows = db.execute(
            "SELECT * FROM alcyoneus_jobs"  # noqa: S608
            + (" WHERE status=?" if status else "")
            + " ORDER BY next_run",
            (status,) if status else (),
        ).fetchall()
        return [dict(row) for row in rows]

    async def _run(self) -> None:
        while not self._stop.is_set():
            db = self._connection()
            rows = db.execute(
                "SELECT * FROM alcyoneus_jobs WHERE status='active' AND next_run<=? ORDER BY next_run LIMIT 20",  # noqa: E501
                (_now(),),
            ).fetchall()
            for row in rows:
                await self._execute(row)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    async def _execute(self, row: sqlite3.Row) -> None:
        db = self._connection()
        handler = self.handlers.get(row["handler"])
        if handler is None:
            db.execute(
                "UPDATE alcyoneus_jobs SET status='failed', last_error=?, updated_at=? WHERE id=?",
                ("handler unavailable", _now(), row["id"]),
            )
            db.commit()
            return
        try:
            result = handler(json.loads(row["payload"]))
            if inspect.isawaitable(result):
                await result
            if row["schedule_type"] == "once":
                db.execute(
                    "UPDATE alcyoneus_jobs SET status='completed', updated_at=? WHERE id=?",
                    (_now(), row["id"]),
                )
            else:
                if row["schedule_type"] == "interval":
                    next_run = datetime.now(UTC) + timedelta(seconds=float(row["schedule_value"]))
                else:
                    next_run = _next_cron(
                        row["schedule_value"], datetime.now(UTC), ZoneInfo(row["timezone"])
                    )
                db.execute(
                    "UPDATE alcyoneus_jobs SET next_run=?, retries=0, last_error=NULL, updated_at=? WHERE id=?",  # noqa: E501
                    (next_run.isoformat(), _now(), row["id"]),
                )
        except Exception as exc:
            retries = int(row["retries"]) + 1
            if retries > int(row["max_retries"]):
                db.execute(
                    "UPDATE alcyoneus_jobs SET status='failed', retries=?, last_error=?, updated_at=? WHERE id=?",  # noqa: E501
                    (retries, str(exc)[:2000], _now(), row["id"]),
                )
            else:
                next_run = datetime.now(UTC) + timedelta(
                    seconds=float(row["backoff_seconds"]) * (2 ** (retries - 1))
                )
                db.execute(
                    "UPDATE alcyoneus_jobs SET next_run=?, retries=?, last_error=?, updated_at=? WHERE id=?",  # noqa: E501
                    (next_run.isoformat(), retries, str(exc)[:2000], row["id"]),
                )
        db.commit()


def _scheduler(config: dict[str, Any] | None) -> Scheduler:
    scheduler = (config or {}).get("scheduler")
    if not isinstance(scheduler, Scheduler):
        raise RuntimeError("configure config['scheduler'] with Scheduler")
    return scheduler


@tool(
    name="schedule_job",
    description="Schedule a named Alcyoneus OS handler once, repeatedly, or by cron.",
    tags=["scheduling"],
    capabilities=["schedule_jobs"],
)
async def schedule_job(
    handler: str,
    payload: dict[str, Any] | None = None,
    run_at: str | None = None,
    interval_seconds: float | None = None,
    cron: str | None = None,
    timezone_name: str = "UTC",
    max_retries: int = 3,
    config: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        await _scheduler(config).schedule(
            handler,
            payload or {},
            run_at=run_at,
            interval_seconds=interval_seconds,
            cron=cron,
            timezone_name=timezone_name,
            max_retries=max_retries,
        )
    )


@tool(
    name="cancel_scheduled_job",
    description="Cancel an active scheduled job.",
    tags=["scheduling"],
    capabilities=["cancel_jobs"],
)
async def cancel_scheduled_job(job_id: str, config: dict[str, Any] | None = None) -> str:
    return json.dumps({"job_id": job_id, "cancelled": await _scheduler(config).cancel(job_id)})


@tool(
    name="list_scheduled_jobs",
    description="List persisted scheduled jobs.",
    tags=["scheduling"],
    capabilities=["list_jobs"],
)
async def list_scheduled_jobs(
    status: str | None = None, config: dict[str, Any] | None = None
) -> str:
    return json.dumps({"jobs": await _scheduler(config).list_jobs(status)}, default=str)


__all__ = ["Scheduler", "cancel_scheduled_job", "list_scheduled_jobs", "schedule_job"]
