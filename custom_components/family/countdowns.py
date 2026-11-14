"""Countdowns on the Family dashboard: "12 days to the beach".

A parent adds them (name, emoji, date, optionally for one person); they live
in the Store (``countdowns``) as {id, name, emoji, date, member}. Each one
shows until the end of its day ("Today!"), then it's dropped. Birthdays set
on family members count down too, from ``BIRTHDAY_DAYS`` before.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

MAX_COUNTDOWNS = 20
# A birthday shows this many days ahead.
BIRTHDAY_DAYS = 30


class Countdowns:
    """The family's countdowns."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self.items = [c for c in data.get("countdowns") or [] if isinstance(c, dict)]

    def data(self) -> dict[str, Any]:
        return {"countdowns": self.items}

    def prune(self, today: date) -> bool:
        """Drop countdowns whose day is over."""
        keep = [c for c in self.items if c.get("date", "") >= today.isoformat()]
        changed = len(keep) != len(self.items)
        self.items = keep
        return changed

    def save(self, raw: dict[str, Any]) -> dict[str, Any]:
        day = model.clean_day(raw.get("date"))
        if not day:
            raise ValueError("Pick the day it counts down to")
        if day < dt_util.now().date().isoformat():
            raise ValueError("Pick a day that hasn't passed")
        member = raw.get("member") or None
        if member is not None:
            self.manager.member(member)
        countdown = {
            "id": raw.get("id") or uuid4().hex[:12],
            "name": model.clean_name(raw.get("name"), "What it counts down to"),
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
            "date": day,
            "member": member,
        }
        if not any(c["id"] == countdown["id"] for c in self.items):
            if len(self.items) >= MAX_COUNTDOWNS:
                raise ValueError(f"There can be at most {MAX_COUNTDOWNS} countdowns")
            self.items.append(countdown)
        else:
            self.items[:] = [
                countdown if c["id"] == countdown["id"] else c for c in self.items
            ]
        self.manager.changed()
        return countdown

    def delete(self, countdown_id: str) -> None:
        before = len(self.items)
        self.items[:] = [c for c in self.items if c["id"] != countdown_id]
        if len(self.items) == before:
            raise ValueError("That countdown is gone")
        self.manager.changed()

    def forget_member(self, member_id: str) -> None:
        self.items[:] = [c for c in self.items if c.get("member") != member_id]

    def snapshot(self, today: date) -> list[dict[str, Any]]:
        """Countdowns and coming birthdays, soonest first, with days to go."""
        rows = [
            {**c, "days": (date.fromisoformat(c["date"]) - today).days}
            for c in self.items
            if c.get("date", "") >= today.isoformat()
        ]
        for member in self.manager.members:
            birthday = member.get("birthday")
            if not birthday:
                continue
            when = model.next_birthday(birthday, today)
            days = (when - today).days
            if days <= BIRTHDAY_DAYS:
                rows.append(
                    {
                        "id": f"birthday:{member['id']}",
                        "name": f"{member['name']}'s birthday",
                        "emoji": "🎂",
                        "date": when.isoformat(),
                        "member": member["id"],
                        "days": days,
                        "birthday": True,
                    }
                )
        return sorted(rows, key=lambda c: (c["days"], c["name"]))
