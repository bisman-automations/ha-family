"""Race you! One child challenges another to finish their own chores first.

A challenge is for today only: {id, day, members [a, b], points, at}. The
first of the two to finish all of their own chores today wins
``settings.challenge_points``, as a bonus kept with the chore that finished
it (bonus ``challenge``, with the challenge's id), so undoing or rejecting
that chore opens the race again. Challenges from other days are dropped.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

BONUS_CHALLENGE = "challenge"
MAX_A_DAY = 3


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class Challenges:
    """Today's races."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self.items = [c for c in data.get("challenges") or [] if isinstance(c, dict)]

    def data(self) -> dict[str, Any]:
        return {"challenges": self.items}

    def prune(self, today: date) -> bool:
        keep = [c for c in self.items if c.get("day") == today.isoformat()]
        changed = len(keep) != len(self.items)
        self.items = keep
        return changed

    def winner(self, challenge: dict[str, Any]) -> str | None:
        for e in self.manager.entries:
            if (
                e.get("bonus") == BONUS_CHALLENGE
                and e.get("challenge") == challenge["id"]
                and e.get("review") != model.REVIEW_REJECTED
            ):
                return e["member"]
        return None

    def start(self, from_id: str, to_id: str) -> dict[str, Any]:
        points = int(self.manager.settings.get("challenge_points") or 0)
        if not points:
            raise _error("Races are turned off. Ask a parent.")
        if from_id == to_id:
            raise _error("Pick someone else to race")
        challenger = self.manager.member(from_id)
        other = self.manager.member(to_id)
        today = dt_util.now().date()
        for member in (challenger, other):
            total, left = self.manager.own_today(member["id"])
            if not total or not left:
                raise _error(f"{member['name']} has no chores left to race with today")
        mine = [
            c
            for c in self.items
            if from_id in c["members"] and c["day"] == today.isoformat()
        ]
        if any(to_id in c["members"] and self.winner(c) is None for c in mine):
            raise _error(f"You're already racing {other['name']}")
        if len(mine) >= MAX_A_DAY:
            raise _error(f"That's {MAX_A_DAY} races today already")
        challenge = {
            "id": uuid4().hex[:12],
            "day": today.isoformat(),
            "members": [from_id, to_id],
            "points": points,
            "at": dt_util.now().isoformat(),
        }
        self.items.append(challenge)
        self.manager.changed()
        return challenge

    def wins(self, member_id: str, today: date) -> list[tuple[str, str, int, str]]:
        """The races this member just won by finishing: (kind, title, points, id)."""
        found = []
        for c in self.items:
            if c["day"] != today.isoformat() or member_id not in c["members"]:
                continue
            if self.winner(c) is not None:
                continue
            other_id = next(m for m in c["members"] if m != member_id)
            other = next((m for m in self.manager.members if m["id"] == other_id), None)
            name = other["name"] if other else "someone"
            found.append(
                (
                    BONUS_CHALLENGE,
                    f"Won the race with {name}!",
                    int(c["points"]),
                    c["id"],
                )
            )
        return found

    def snapshot(self) -> list[dict[str, Any]]:
        today = dt_util.now().date().isoformat()
        return [
            {**c, "winner": self.winner(c)} for c in self.items if c["day"] == today
        ]
