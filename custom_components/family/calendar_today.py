"""Today's calendar on the Family dashboard.

Reads the events of today and the next days (``DAYS``) from the calendars
a parent picked (each one for a family member, or for everyone) with ``calendar.get_events``, when Family
starts, every 15 minutes, just after midnight and whenever a calendar's
state changes (an event starting or ending). The dashboards get the list
in the snapshot; nothing is stored.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from . import model
from .const import SIGNAL_CHANGED

if TYPE_CHECKING:
    from .manager import FamilyManager

_LOGGER = logging.getLogger(__name__)
REFRESH = timedelta(minutes=15)
TIMEOUT_SECONDS = 20
MAX_EVENTS = 150
# Today and the days after it, for the Today section's "Next few days".
DAYS = 7


def clean_calendars(raw: Any, members: set[str]) -> list[dict[str, Any]]:
    """[{entity_id, member}] with known members only; one row per calendar."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw or []:
        if not isinstance(row, dict):
            raise ValueError("Each calendar needs a calendar entity")
        entity_id = str(row.get("entity_id") or "").strip()
        if not entity_id.startswith("calendar.") or entity_id in seen:
            continue
        member = row.get("member") or None
        seen.add(entity_id)
        result.append(
            {"entity_id": entity_id, "member": member if member in members else None}
        )
    return result


class CalendarToday:
    """Today's events from the family's calendars."""

    def __init__(self, manager: FamilyManager) -> None:
        self.m = manager
        self.hass = manager.hass
        self.events: list[dict[str, Any]] = []
        self._unsub: Callable[[], None] | None = None
        self._refreshing = False

    @property
    def calendars(self) -> list[dict[str, Any]]:
        return list(self.m.settings.get("calendars") or [])

    @callback
    def watch(self) -> None:
        """Follow the picked calendars' states (call again when they change)."""
        self.stop()
        ids = [c["entity_id"] for c in self.calendars]
        if not ids:
            return

        @callback
        def _changed(_event: Event) -> None:
            self.schedule()

        self._unsub = async_track_state_change_event(self.hass, ids, _changed)

    @callback
    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def schedule(self, _now: Any = None) -> None:
        self.m.entry.async_create_background_task(
            self.hass, self.async_refresh(), "family calendar refresh"
        )

    async def async_refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            now = dt_util.now()
            start = dt_util.start_of_local_day(now)
            end = start + timedelta(days=DAYS)
            events: list[dict[str, Any]] = []
            for row in self.calendars:
                events.extend(await self._read(row, start, end, now.date()))
        finally:
            self._refreshing = False
        events.sort(key=lambda e: (not e["all_day"], e["start"], e["title"].casefold()))
        events = events[:MAX_EVENTS]
        if events != self.events:
            self.events = events
            async_dispatcher_send(self.hass, SIGNAL_CHANGED)

    def on(self, day: str) -> list[dict[str, Any]]:
        """The events on one day (an ISO date)."""
        return [e for e in self.events if day in e["days"]]

    async def _read(
        self, row: dict[str, Any], start: datetime, end: datetime, today: date
    ) -> list[dict[str, Any]]:
        entity_id = row["entity_id"]
        state = self.hass.states.get(entity_id)
        if state is None or not self.hass.services.has_service(
            "calendar", "get_events"
        ):
            return []
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):
                response = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": entity_id,
                        "start_date_time": start.isoformat(),
                        "end_date_time": end.isoformat(),
                    },
                    blocking=True,
                    return_response=True,
                )
        except Exception as err:  # noqa: BLE001 - one calendar failing mustn't stop the rest
            _LOGGER.warning("Family couldn't read %s: %s", entity_id, err)
            return []
        calendar = (response or {}).get(entity_id)
        raw = calendar.get("events") if isinstance(calendar, dict) else None
        result = []
        for event in raw if isinstance(raw, list) else []:
            if not isinstance(event, dict):
                continue
            begins = str(event.get("start") or "")
            days = _days(begins, str(event.get("end") or ""), today)
            if not days:
                continue
            result.append(
                {
                    "title": str(event.get("summary") or "Busy"),
                    "start": begins,
                    "end": str(event.get("end") or ""),
                    # All-day events give a date only.
                    "all_day": len(begins) == 10,
                    "member": row.get("member"),
                    "calendar": state.name,
                    "days": days,
                }
            )
        return result


def _days(start: str, end: str, today: date) -> list[str]:
    """The days from today on that an event covers (its end isn't included)."""
    try:
        if len(start) == 10:  # all day: dates only, the end date is the day after
            first = date.fromisoformat(start)
            last = date.fromisoformat(end[:10]) - timedelta(days=1) if end else first
        else:
            begins = dt_util.as_local(datetime.fromisoformat(start))
            ends = dt_util.as_local(datetime.fromisoformat(end)) if end else begins
            first = begins.date()
            last = max(first, (ends - timedelta(microseconds=1)).date())
    except ValueError:
        return []
    return model.event_days(first, last, today, DAYS)
