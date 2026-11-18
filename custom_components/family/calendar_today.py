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
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from . import model

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
        # Asked to refresh while a refresh was running: once more after it,
        # so a calendar change in the middle isn't missed.
        self._again = False

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
        """Read the picked calendars (all at once) and tell the dashboards
        when today's or the coming days' events changed.

        A refresh asked for while one runs is done once more afterwards
        instead of being dropped.
        """
        if self._refreshing:
            self._again = True
            return
        self._refreshing = True
        try:
            while True:
                self._again = False
                await self._refresh_once()
                if not self._again:
                    break
        finally:
            self._refreshing = False

    async def _refresh_once(self) -> None:
        now = dt_util.now()
        start = dt_util.start_of_local_day(now)
        end = start + timedelta(days=DAYS)
        # Every calendar at the same time: one slow calendar (each has
        # TIMEOUT_SECONDS) no longer holds up the others.
        results = await asyncio.gather(
            *(self._read(row, start, end, now.date()) for row in self.calendars)
        )
        events: list[dict[str, Any]] = [event for found in results for event in found]
        events.sort(key=lambda e: (not e["all_day"], e["start"], e["title"].casefold()))
        events = events[:MAX_EVENTS]
        if events != self.events:
            self.events = events
            # One update for the moment, with everything else that changed.
            self.m.changed_view()

    async def async_add(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Add an event to one of the picked calendars (Parents dashboard).

        All day: ``date`` (and an optional last ``end_date``). Otherwise
        ``date`` with ``start`` and ``end`` times ("HH:MM").
        """
        from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

        entity_id = raw.get("entity_id")
        if entity_id not in {c["entity_id"] for c in self.calendars}:
            raise FamilyError("Pick one of the family's calendars")
        title = model.clean_name(raw.get("title"), "What's happening")
        day = model.clean_day(raw.get("date"), "The day")
        if not day:
            raise FamilyError("Pick the day")
        first = date.fromisoformat(day)
        data: dict[str, Any] = {"summary": title}
        if raw.get("start"):
            start = model.clean_time(raw.get("start"), "Starts")
            end = model.clean_time(raw.get("end"), "Ends") or start
            zone = dt_util.get_default_time_zone()
            begins = datetime.combine(
                first, datetime.strptime(start, "%H:%M").time(), tzinfo=zone
            )
            ends = datetime.combine(
                first, datetime.strptime(end, "%H:%M").time(), tzinfo=zone
            )
            if ends <= begins:
                ends = begins + timedelta(hours=1)
            data.update(
                start_date_time=begins.isoformat(), end_date_time=ends.isoformat()
            )
        else:
            last = model.clean_day(raw.get("end_date"), "The last day") or day
            if last < day:
                raise FamilyError("The last day can't be before the first")
            data.update(
                start_date=day,
                end_date=(date.fromisoformat(last) + timedelta(days=1)).isoformat(),
            )
        try:
            await self.hass.services.async_call(
                "calendar",
                "create_event",
                data,
                target={"entity_id": entity_id},
                blocking=True,
            )
        except Exception as err:
            raise FamilyError(f"Couldn't add it to the calendar: {err}") from err
        await self.async_refresh()
        return {"title": title, **data}

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
