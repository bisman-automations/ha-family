"""Pet care: each pet's meals (or walks) at set times, and who did them.

A parent adds a pet: {id, name, emoji, times ["07:00", "18:00"], task
("Feed"), points, members (None: everyone)} in the Store (``pets``). Each
time is a slot for the day. Doing it is a chore entry with chore id
``pet:<pet>:<slot>`` (checked like a chore, undone like one), so a slot
already done today can't be done twice: no feeding the dog two breakfasts.
A slot is due from an hour before its time.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

PREFIX = "pet:"
DUE_BEFORE = timedelta(hours=1)
MAX_TIMES = 6


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def slot_id(pet_id: str, slot: int) -> str:
    return f"{PREFIX}{pet_id}:{slot}"


class Pets:
    """The family's pets and today's care."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self.items = [p for p in data.get("pets") or [] if isinstance(p, dict)]

    def data(self) -> dict[str, Any]:
        return {"pets": self.items}

    def _get(self, pet_id: str) -> dict[str, Any]:
        for pet in self.items:
            if pet["id"] == pet_id:
                return pet
        raise _error("That pet isn't on the list any more")

    def save(self, raw: dict[str, Any]) -> dict[str, Any]:
        times = sorted(
            {
                t
                for t in (model.clean_time(x, "A time") for x in raw.get("times") or [])
                if t
            }
        )
        if not times:
            raise _error("Give at least one time")
        if len(times) > MAX_TIMES:
            raise _error(f"Up to {MAX_TIMES} times a day")
        old = next((p for p in self.items if p["id"] == raw.get("id")), None)
        members = raw.get("members")
        pet = {
            "id": old["id"] if old else uuid4().hex[:12],
            "name": model.clean_name(raw.get("name"), "The pet's name"),
            "emoji": model.clean_emoji(raw.get("emoji"), 4),
            "task": str(raw.get("task") or "Feed").strip()[:30] or "Feed",
            "times": times,
            "points": model.clean_points(raw.get("points") or 0),
            "members": None
            if not members
            else self.manager.known_members(members) or None,
        }
        if old:
            self.items[self.items.index(old)] = pet
        else:
            self.items.append(pet)
        self.manager.changed()
        return pet

    def delete(self, pet_id: str) -> None:
        self.items.remove(self._get(pet_id))
        self.manager.changed()

    def _done_today(
        self, pet_id: str, slot: int, now: datetime
    ) -> dict[str, Any] | None:
        today = now.date().isoformat()
        wanted = slot_id(pet_id, slot)
        return next(
            (
                e
                for e in self.manager.entries
                if e.get("chore_id") == wanted
                and e["at"][:10] == today
                and e.get("review") != model.REVIEW_REJECTED
            ),
            None,
        )

    def care(self, pet_id: str, slot: int, member_id: str) -> dict[str, Any]:
        pet = self._get(pet_id)
        member = self.manager.member(member_id)
        if not 0 <= slot < len(pet["times"]):
            raise _error("Pick which time it is")
        if pet.get("members") and member_id not in pet["members"]:
            raise _error(f"Looking after {pet['name']} isn't {member['name']}'s job")
        now = dt_util.now()
        if self.manager.away.on(now.date()):
            raise _error("Pet care is off while the family is away")
        if done := self._done_today(pet_id, slot, now):
            who = next(
                (m["name"] for m in self.manager.members if m["id"] == done["member"]),
                "Someone",
            )
            raise _error(f"{who} already did it at {done['at'][11:16]}")
        hour, minute = (int(x) for x in pet["times"][slot].split(":")[:2])
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < due - DUE_BEFORE:
            raise _error(f"Not yet: it's for {pet['times'][slot]}")
        entry = {
            "id": uuid4().hex[:12],
            "at": now.isoformat(),
            "kind": model.KIND_CHORE,
            "member": member_id,
            "title": f"{pet['task']} {pet['name']} ({pet['times'][slot]})",
            "points": pet["points"],
            "chore_id": slot_id(pet_id, slot),
            "review": model.REVIEW_PENDING,
        }
        self.manager.entries.append(entry)
        self.manager.changed()
        return entry

    def forget_member(self, member_id: str) -> None:
        for pet in self.items:
            if pet.get("members"):
                pet["members"] = [m for m in pet["members"] if m != member_id] or None

    def snapshot(self) -> list[dict[str, Any]]:
        now = dt_util.now()
        result = []
        for pet in self.items:
            slots = []
            for i, time in enumerate(pet["times"]):
                done = self._done_today(pet["id"], i, now)
                hour, minute = (int(x) for x in time.split(":")[:2])
                due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                slots.append(
                    {
                        "time": time,
                        "done_by": done["member"] if done else None,
                        "done_at": done["at"] if done else None,
                        "entry": done["id"] if done else None,
                        "due": now >= due - DUE_BEFORE,
                        "late": not done and now > due + DUE_BEFORE,
                    }
                )
            result.append({**pet, "slots": slots})
        return result
