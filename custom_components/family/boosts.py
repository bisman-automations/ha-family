"""Double points: chores worth two or three times their points for a while.

A parent starts one ("Saturday cleanup", 2×, until 5 PM, every chore or
just the ones picked). Kept in settings (``boosts``) as {id, label, factor,
from, until, chores}: ISO times; ``chores`` None is every chore (to-do items
too). Chores done while it's on are worth that many times their points; the
entry keeps ``boost``. Ones that ended are dropped.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

MAX_HOURS = 24 * 14
MAX_BOOSTS = 10


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def _time(value: Any, label: str) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        raise _error(f"{label} needs a date and time")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed


class Boosts:
    """The family's double-points times."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager

    @property
    def items(self) -> list[dict[str, Any]]:
        boosts = self.manager.settings.get("boosts")
        return boosts if isinstance(boosts, list) else []

    def factor(self, chore_id: str, now: datetime | None = None) -> int:
        return model.boost_factor(self.items, chore_id, now or dt_util.now())

    def add(self, raw: dict[str, Any]) -> dict[str, Any]:
        now = dt_util.now()
        factor = int(raw.get("factor") or 2)
        if factor not in model.BOOST_FACTORS:
            raise _error("Pick double or triple points")
        start = _time(raw.get("from"), "Starts") or now
        end = _time(raw.get("until"), "Ends")
        if end is None:
            raise _error("Pick when it ends")
        if end <= max(start, now):
            raise _error("Pick an end after it starts, and after now")
        if end - start > timedelta(hours=MAX_HOURS):
            raise _error("Keep it to two weeks at most")
        if len(self.items) >= MAX_BOOSTS:
            raise _error("Too many at once. Stop one first.")
        chores = raw.get("chores") or None
        if chores is not None:
            known = {c["id"] for c in self.manager.chores}
            chores = [c for c in dict.fromkeys(chores) if c in known] or None
        boost = {
            "id": uuid4().hex[:12],
            "label": " ".join(str(raw.get("label") or "").split())[:60]
            or ("Double points" if factor == 2 else "Triple points"),
            "factor": factor,
            "from": start.isoformat(),
            "until": end.isoformat(),
            "chores": chores,
        }
        self.manager.settings["boosts"] = [*self.items, boost]
        self.manager.changed()
        return boost

    def stop(self, boost_id: str) -> None:
        if not any(b["id"] == boost_id for b in self.items):
            raise _error("That's already over")
        self.manager.settings["boosts"] = [b for b in self.items if b["id"] != boost_id]
        self.manager.changed()

    def prune(self, now: datetime) -> bool:
        keep = []
        for boost in self.items:
            end = dt_util.parse_datetime(str(boost.get("until") or ""))
            if end is not None and end > now:
                keep.append(boost)
        if len(keep) == len(self.items):
            return False
        self.manager.settings["boosts"] = keep
        return True

    def snapshot(self) -> list[dict[str, Any]]:
        """Going on now (``on``) or coming up, soonest first."""
        now = dt_util.now()
        rows = []
        for boost in self.items:
            start = dt_util.parse_datetime(boost["from"])
            end = dt_util.parse_datetime(boost["until"])
            if start is None or end is None or end <= now:
                continue
            rows.append({**boost, "on": start <= now})
        return sorted(rows, key=lambda b: b["from"])
