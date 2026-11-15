"""The give jar: points the kids give toward something for others.

A parent sets what the family gives for (``settings.give_goal``: {name,
emoji, target, since}), and optionally a share of each allowance that goes
in by itself (``settings.give_percent``). A child gives points from the
Family dashboard; each gift is a ledger entry (kind ``give``, negative
points), so it comes off their points like a reward. The jar counts the
gifts since the goal was set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

KIND_GIVE = "give"
MAX_GIVE_PERCENT = 50


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def clean_goal(
    raw: Any, old: dict[str, Any] | None, restart: bool
) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _error("Say what the family gives for")
    keep = old and not restart
    return {
        "name": model.clean_name(raw.get("name"), "What it's for"),
        "emoji": model.clean_emoji(raw.get("emoji"), 4),
        "target": max(1, model.clean_points(raw.get("target") or 0, "The target")),
        "since": old["since"] if keep else dt_util.now().isoformat(),
    }


class Give:
    """Gifts into the give jar."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager

    @property
    def goal(self) -> dict[str, Any] | None:
        return self.manager.settings.get("give_goal")

    def _entry(self, member_id: str, points: int, title: str) -> dict[str, Any]:
        return {
            "id": uuid4().hex[:12],
            "at": dt_util.now().isoformat(),
            "kind": KIND_GIVE,
            "member": member_id,
            "title": title,
            "points": -points,
        }

    def give(self, member_id: str, points: Any) -> dict[str, Any]:
        goal = self.goal
        if goal is None:
            raise _error("There's nothing to give to yet. Ask a parent.")
        member = self.manager.member(member_id)
        amount = model.clean_points(points, "Points")
        if amount < 1:
            raise _error("Give at least 1 point")
        if amount > self.manager.points(member_id):
            raise _error(f"{member['name']} doesn't have that many points")
        entry = self._entry(member_id, amount, f"Gave to {goal['name']}")
        self.manager.entries.append(entry)
        self.manager.changed()
        return entry

    def from_allowance(self, member_id: str, allowance: int) -> dict[str, Any] | None:
        """The allowance's share for the jar, as an entry (None: nothing)."""
        goal = self.goal
        percent = int(self.manager.settings.get("give_percent") or 0)
        share = allowance * percent // 100
        if goal is None or share < 1:
            return None
        return self._entry(member_id, share, f"Allowance to {goal['name']}")

    def snapshot(self) -> dict[str, Any] | None:
        goal = self.goal
        if goal is None:
            return None
        gifts = [
            e
            for e in self.manager.entries
            if e.get("kind") == KIND_GIVE and e["at"] >= goal["since"]
        ]
        total = -sum(int(e["points"]) for e in gifts)
        by: dict[str, int] = {}
        for e in gifts:
            by[e["member"]] = by.get(e["member"], 0) - int(e["points"])
        return {
            **goal,
            "total": total,
            "reached": total >= goal["target"],
            "by": by,
            "percent": int(self.manager.settings.get("give_percent") or 0),
        }
