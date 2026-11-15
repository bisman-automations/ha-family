"""The Family dashboard's extras for the kids' screen (2.6.0).

- **Tomorrow**: each member's own chores tomorrow, and tomorrow's events.
- **Screen time left**: each TV Mgmt TV and Media Mgmt speaker, by its
  "time remaining today" sensor (found by unique id; the page reads its live
  state).
- **What to wear**: today's weather from ``settings.weather_entity``.
- **High fives**: a no-points thank-you from one member to another, kept in
  the ledger as ``kind: high_five`` (``from`` is the sender).
- **Points story**: one member's recent entries with their points before and
  after each.
- **Family streak**: days in a row everyone finished their own chores.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import model
from .const import MEDIA_MGMT_DOMAIN, TV_MGMT_DOMAIN

if TYPE_CHECKING:
    from .manager import FamilyManager


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415

    return FamilyError(message)


# A member can send this many high fives a day.
MAX_HIGH_FIVES = 10
STORY_ENTRIES = 30
TIME_LEFT_KEY = "time_remaining_today"  # TV Mgmt's and Media Mgmt's sensor


class KidBoard:
    """Extras for the Family dashboard."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager

    # ---- tomorrow -----------------------------------------------------------------

    def tomorrow(self) -> dict[str, Any]:
        """Tomorrow's own chores for each member, and tomorrow's events."""
        manager = self.manager
        day = dt_util.now().date() + timedelta(days=1)
        noon = dt_util.as_local(
            datetime.combine(day, time(12), tzinfo=dt_util.get_default_time_zone())
        )
        chores: dict[str, list[dict[str, Any]]] = {}
        if not manager.away.on(day):
            for raw in manager.chores:
                chore = model.for_ages(raw, manager.members, day)
                if not chore.get("enabled", True) or not model.on_day(chore, day):
                    continue
                if chore.get("repeat") == model.REPEAT_ONCE:
                    continue  # once: done today or not, it isn't "tomorrow's"
                if chore.get("turns"):
                    turn = model.turn_member(chore, manager.entries, noon)
                    people = [turn] if turn else []
                else:
                    people = [
                        m["id"] for m in manager.members if model.is_own(chore, m["id"])
                    ]
                for member_id in people:
                    chores.setdefault(member_id, []).append(
                        {
                            "id": chore["id"],
                            "name": chore["name"],
                            "emoji": chore.get("emoji"),
                            "points": int(chore.get("points", 0)),
                            "from_time": chore.get("from_time"),
                        }
                    )
        return {
            "date": day.isoformat(),
            "chores": chores,
            "events": manager.calendar.on(day.isoformat()),
            "away": manager.away.on(day),
        }

    def next_week(self, member_id: str) -> list[str]:
        """The names of a member's own chores in the coming week (Monday on),
        for the family meeting: their own, taken in turns (if it may be
        theirs) and the ones they picked from the pool."""
        manager = self.manager
        names: list[str] = []
        for chore in manager.chores:
            if (
                not chore.get("enabled", True)
                or chore.get("repeat") == model.REPEAT_ONCE
            ):
                continue
            if chore.get("pool"):
                mine = manager.picks.picked_by(chore["id"]) == member_id
            elif chore.get("turns"):
                mine = member_id in (chore.get("members") or [])
            else:
                mine = model.is_own(chore, member_id)
            if mine:
                names.append(
                    chore["name"] + (" (taking turns)" if chore.get("turns") else "")
                )
        return names

    # ---- screen time left ------------------------------------------------------------

    def screen(self) -> list[dict[str, Any]]:
        """Each TV and speaker with a "time remaining today" sensor."""
        hass = self.manager.hass
        registry = er.async_get(hass)
        found = []
        for domain, kind in ((TV_MGMT_DOMAIN, "tv"), (MEDIA_MGMT_DOMAIN, "music")):
            for entry in hass.config_entries.async_entries(domain):
                if entry.disabled_by:
                    continue
                entity_id = registry.async_get_entity_id(
                    "sensor", domain, f"{entry.entry_id}_{TIME_LEFT_KEY}"
                )
                if entity_id:
                    found.append(
                        {"kind": kind, "name": entry.title, "entity_id": entity_id}
                    )
        return found

    # ---- what to wear ----------------------------------------------------------------

    def weather(self) -> dict[str, Any] | None:
        entity_id = self.manager.settings.get("weather_entity")
        state = self.manager.hass.states.get(entity_id) if entity_id else None
        if state is None:
            return None
        attrs = state.attributes
        unit = attrs.get("temperature_unit") or "°"
        wear = model.what_to_wear(attrs.get("temperature"), unit, state.state)
        if wear is None:
            return None
        return {
            "entity_id": entity_id,
            "temperature": attrs.get("temperature"),
            "unit": unit,
            "condition": state.state,
            **wear,
        }

    # ---- high fives ------------------------------------------------------------------

    def high_five(self, from_id: str, to_id: str, emoji: str | None) -> dict[str, Any]:
        manager = self.manager
        sender = manager.member(from_id)
        receiver = manager.member(to_id)
        if from_id == to_id:
            raise _error("Send a high five to someone else")
        today = dt_util.now().date()
        sent = sum(
            1
            for e in manager.entries
            if e.get("kind") == model.KIND_HIGH_FIVE
            and e.get("from") == from_id
            and model.entry_day(e) == today
        )
        if sent >= MAX_HIGH_FIVES:
            raise _error(
                f"That's {MAX_HIGH_FIVES} high fives today, {sender['name']}. "
                "Save some for tomorrow!"
            )
        entry = {
            "id": uuid4().hex,
            "at": dt_util.now().isoformat(),
            "kind": model.KIND_HIGH_FIVE,
            "member": receiver["id"],
            "from": sender["id"],
            "title": emoji if emoji in model.HIGH_FIVE_EMOJI else "🙌",
            "points": 0,
        }
        manager.entries.append(entry)
        manager.changed()
        return entry

    # ---- points story ----------------------------------------------------------------

    def story(self, member_id: str) -> dict[str, Any]:
        """A member's latest entries, newest first, with before and after."""
        manager = self.manager
        member = manager.member(member_id)
        balances = model.running_balances(manager.entries, manager.carried)
        mine = sorted(
            (
                e
                for e in manager.entries
                if e.get("member") == member["id"]
                and e.get("kind") != model.KIND_HIGH_FIVE
                and not (e.get("kind") == model.KIND_BONUS and not e.get("points"))
            ),
            key=lambda e: e["at"],
            reverse=True,
        )[:STORY_ENTRIES]
        return {
            "member": member["id"],
            "points": manager.points(member["id"]),
            "entries": [
                {**e, "before": balances[e["id"]][0], "after": balances[e["id"]][1]}
                if e.get("id") in balances
                else dict(e)
                for e in mine
            ],
        }

    # ---- family streak ---------------------------------------------------------------

    def family_streak(self, today: date | None = None) -> int:
        manager = self.manager
        today = today or dt_util.now().date()
        people = [m["id"] for m in manager.members]
        return model.family_streak(
            {m: model.all_done_days(manager.entries, m) for m in people},
            {m: manager.has_own(m) for m in people},
            today,
        )
