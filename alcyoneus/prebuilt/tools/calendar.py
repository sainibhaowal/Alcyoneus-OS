"""Provider-neutral calendar tools with a safe in-memory implementation.

Applications can provide Google/Microsoft/CalDAV adapters by implementing
``CalendarProvider`` or use ``HttpCalendarProvider`` for an internal calendar
service.  Tools never send calendar data anywhere unless a provider is set.
"""

from __future__ import annotations

import inspect
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from alcyoneus.utils.decorators import tool


@dataclass(slots=True)
class CalendarEvent:
    id: str
    calendar_id: str
    title: str
    start: str
    end: str
    timezone: str = "UTC"
    description: str | None = None
    location: str | None = None
    attendees: list[str] = field(default_factory=list)
    recurrence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CalendarProvider(Protocol):
    async def create(self, event: CalendarEvent) -> CalendarEvent: ...
    async def update(self, event_id: str, event: CalendarEvent) -> CalendarEvent: ...
    async def delete(self, calendar_id: str, event_id: str) -> bool: ...
    async def list(self, calendar_id: str, start: str, end: str) -> list[CalendarEvent]: ...


def _validate_event(title: str, start: str, end: str, timezone: str) -> tuple[str, str]:
    try:
        zone = ZoneInfo(timezone)
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError("start/end must be ISO-8601 and timezone must be valid") from exc
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=zone)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=zone)
    if end_dt <= start_dt:
        raise ValueError("calendar event end must be after start")
    if not title.strip():
        raise ValueError("calendar event title is required")
    return start_dt.isoformat(), end_dt.isoformat()


class InMemoryCalendarProvider:
    """Deterministic provider for local apps and tests."""

    def __init__(self) -> None:
        self.events: dict[str, CalendarEvent] = {}

    async def create(self, event: CalendarEvent) -> CalendarEvent:
        self.events[event.id] = event
        return event

    async def update(self, event_id: str, event: CalendarEvent) -> CalendarEvent:
        if event_id not in self.events:
            raise KeyError(event_id)
        event.id = event_id
        self.events[event_id] = event
        return event

    async def delete(self, calendar_id: str, event_id: str) -> bool:
        event = self.events.get(event_id)
        if event is None or event.calendar_id != calendar_id:
            return False
        del self.events[event_id]
        return True

    async def list(self, calendar_id: str, start: str, end: str) -> list[CalendarEvent]:
        begin = datetime.fromisoformat(start.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return [
            e
            for e in self.events.values()
            if e.calendar_id == calendar_id
            and datetime.fromisoformat(e.end) > begin
            and datetime.fromisoformat(e.start) < finish
        ]


class HttpCalendarProvider:
    """Adapter for a calendar service exposing JSON CRUD endpoints.

    The service contract is intentionally small: ``POST /calendars/{id}/events``,
    ``PATCH|DELETE /calendars/{id}/events/{event_id}``, and
    ``GET /calendars/{id}/events?start=...&end=...``.  This supports internal
    calendar gateways and provider-specific adapters without coupling Alcyoneus OS
    to one vendor's OAuth implementation.
    """

    def __init__(
        self, base_url: str, access_token: str, *, timeout: float = 30.0, client: Any | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self.client = client

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any] | list[dict[str, Any]]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("HttpCalendarProvider requires 'httpx'") from exc
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
        }
        if self.client is None:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
        else:
            response = await self.client.request(
                method, self.base_url + path, headers=headers, **kwargs
            )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _event(data: dict[str, Any]) -> CalendarEvent:
        return CalendarEvent(**data)

    async def create(self, event: CalendarEvent) -> CalendarEvent:
        data = await self._request(
            "POST", f"/calendars/{event.calendar_id}/events", json=event.as_dict()
        )
        return self._event(data)  # type: ignore[arg-type]

    async def update(self, event_id: str, event: CalendarEvent) -> CalendarEvent:
        data = await self._request(
            "PATCH", f"/calendars/{event.calendar_id}/events/{event_id}", json=event.as_dict()
        )
        return self._event(data)  # type: ignore[arg-type]

    async def delete(self, calendar_id: str, event_id: str) -> bool:
        await self._request("DELETE", f"/calendars/{calendar_id}/events/{event_id}")
        return True

    async def list(self, calendar_id: str, start: str, end: str) -> list[CalendarEvent]:
        data = await self._request(
            "GET", f"/calendars/{calendar_id}/events", params={"start": start, "end": end}
        )
        values = data if isinstance(data, list) else data.get("events", [])
        return [self._event(value) for value in values]


async def _call(provider: Any, method: str, *args: Any) -> Any:
    value = getattr(provider, method)(*args)
    return await value if inspect.isawaitable(value) else value


def _provider(config: dict[str, Any] | None) -> CalendarProvider:
    value = (config or {}).get("calendar_provider")
    if value is None:
        raise RuntimeError("configure config['calendar_provider']")
    return value


@tool(
    name="calendar_create_event",
    description="Create a validated event through the configured calendar provider.",
    tags=["calendar"],
    capabilities=["calendar_write"],
)
async def calendar_create_event(
    calendar_id: str,
    title: str,
    start: str,
    end: str,
    timezone: str = "UTC",
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    recurrence: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    start, end = _validate_event(title, start, end, timezone)
    event = CalendarEvent(
        str(uuid.uuid4()),
        calendar_id,
        title,
        start,
        end,
        timezone,
        description,
        location,
        attendees or [],
        recurrence or [],
    )
    created = await _call(_provider(config), "create", event)
    return json.dumps(created.as_dict(), default=str)


@tool(
    name="calendar_update_event",
    description="Update an existing calendar event.",
    tags=["calendar"],
    capabilities=["calendar_write"],
)
async def calendar_update_event(
    event_id: str,
    calendar_id: str,
    title: str,
    start: str,
    end: str,
    timezone: str = "UTC",
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    recurrence: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    start, end = _validate_event(title, start, end, timezone)
    event = CalendarEvent(
        event_id,
        calendar_id,
        title,
        start,
        end,
        timezone,
        description,
        location,
        attendees or [],
        recurrence or [],
    )
    updated = await _call(_provider(config), "update", event_id, event)
    return json.dumps(updated.as_dict(), default=str)


@tool(
    name="calendar_delete_event",
    description="Delete a calendar event.",
    tags=["calendar"],
    capabilities=["calendar_write"],
)
async def calendar_delete_event(
    calendar_id: str, event_id: str, config: dict[str, Any] | None = None
) -> str:
    return json.dumps(
        {
            "deleted": await _call(_provider(config), "delete", calendar_id, event_id),
            "event_id": event_id,
        }
    )


@tool(
    name="calendar_list_events",
    description="List calendar events overlapping an ISO-8601 time range.",
    tags=["calendar"],
    capabilities=["calendar_read"],
)
async def calendar_list_events(
    calendar_id: str, start: str, end: str, config: dict[str, Any] | None = None
) -> str:
    events = await _call(_provider(config), "list", calendar_id, start, end)
    return json.dumps({"events": [event.as_dict() for event in events]}, default=str)


__all__ = [
    "CalendarEvent",
    "CalendarProvider",
    "HttpCalendarProvider",
    "InMemoryCalendarProvider",
    "calendar_create_event",
    "calendar_delete_event",
    "calendar_list_events",
    "calendar_update_event",
]
