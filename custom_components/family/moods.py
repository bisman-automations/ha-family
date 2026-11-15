"""How was today? An evening check-in, one emoji a day each.

Turned on by ``settings.mood_check``. Each member taps how their day was;
it's kept for ``KEEP_DAYS`` in the Store (``moods``: {member: {date:
mood}}). Only parents see the last two weeks; the Family dashboard shows
just today's pick, so a child can change it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .manager import FamilyManager

MOODS = ("great", "good", "ok", "tired", "sad", "angry")
KEEP_DAYS = 60
SHOW_DAYS = 14


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class Moods:
    """Each member's mood by day."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: dict[str, dict[str, str]] = {}

    def load(self, data: dict[str, Any]) -> None:
        raw = data.get("moods") or {}
        self.items = {
            str(k): {str(d): str(m) for d, m in v.items() if m in MOODS}
            for k, v in raw.items()
            if isinstance(v, dict)
        }

    def data(self) -> dict[str, Any]:
        return {"moods": self.items}

    def prune(self, today: date) -> bool:
        cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
        changed = False
        for member, days in self.items.items():
            keep = {d: m for d, m in days.items() if d >= cutoff}
            if len(keep) != len(days):
                self.items[member] = keep
                changed = True
        return changed

    def set(self, member_id: str, mood: str | None) -> None:
        if not self.manager.settings.get("mood_check"):
            raise _error("The evening check-in is turned off")
        self.manager.member(member_id)
        today = dt_util.now().date().isoformat()
        days = self.items.setdefault(member_id, {})
        if mood is None:
            days.pop(today, None)
        elif mood not in MOODS:
            raise _error("Pick how today was")
        else:
            days[today] = mood
        self.manager.changed()

    def today(self, member_id: str) -> str | None:
        return self.items.get(member_id, {}).get(dt_util.now().date().isoformat())

    def forget_member(self, member_id: str) -> None:
        self.items.pop(member_id, None)

    def recent(self, today: date) -> dict[str, list[dict[str, str | None]]]:
        """The last two weeks per member, for parents (oldest first)."""
        days = [
            (today - timedelta(days=n)).isoformat()
            for n in range(SHOW_DAYS - 1, -1, -1)
        ]
        return {
            m["id"]: [
                {"date": d, "mood": self.items.get(m["id"], {}).get(d)} for d in days
            ]
            for m in self.manager.members
        }
