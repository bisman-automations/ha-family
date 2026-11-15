"""Pick your chores: chores in the weekly pool belong to nobody until someone
picks them.

A chore with ``pool`` set is in the pool. Each week (``picks`` in the Store:
{week, chosen: {chore id: member id}}) the children take turns picking:
whoever has picked the fewest points this week goes next
(``model.next_picker``), until the pool is empty or everyone has
``settings.pick_points`` worth. A picked chore is that person's own chore for
the week; one nobody picked isn't shown. A parent can put a pick back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager


class Picks:
    """This week's picks from the chore pool."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.week = ""
        self.chosen: dict[str, str] = {}

    def load(self, data: dict[str, Any]) -> None:
        raw = data.get("picks") or {}
        self.week = str(raw.get("week") or "")
        self.chosen = {str(k): str(v) for k, v in (raw.get("chosen") or {}).items()}

    def data(self) -> dict[str, Any]:
        return {"picks": {"week": self.week, "chosen": self.chosen}}

    def _current(self) -> dict[str, str]:
        week = model.week_key(dt_util.now().date())
        if week != self.week:
            self.week, self.chosen = week, {}
        return self.chosen

    def pool(self) -> list[dict[str, Any]]:
        return [
            c for c in self.manager.chores if c.get("pool") and c.get("enabled", True)
        ]

    def picked_by(self, chore_id: str) -> str | None:
        return self._current().get(chore_id)

    def apply(self, chore: dict[str, Any]) -> dict[str, Any]:
        """A pool chore as it is this week: the picker's own, or nobody's yet."""
        if not chore.get("pool"):
            return chore
        member = self.picked_by(chore["id"])
        if member is None:
            return dict(chore, unpicked=True)
        return dict(chore, members=[member], grab=False, picked_by=member)

    def _pickers(self) -> list[str]:
        """Who picks, in family order: the pool chores' people (everyone,
        for a chore with nobody ticked) who have something left to pick and
        haven't reached the week's points."""
        pool = self.pool()
        allowed = set()
        for chore in pool:
            allowed.update(
                chore.get("members") or [m["id"] for m in self.manager.members]
            )
        target = int(self.manager.settings.get("pick_points") or 0)
        points = {c["id"]: int(c.get("points") or 0) for c in pool}
        chosen = self._current()
        result = []
        for m in self.manager.members:
            if m["id"] not in allowed:
                continue
            if target:
                mine = sum(
                    points.get(c, 0) for c, who in chosen.items() if who == m["id"]
                )
                if mine >= target:
                    continue  # they have enough for the week
            if not any(
                c["id"] not in chosen and m["id"] in (c.get("members") or [m["id"]])
                for c in pool
            ):
                continue  # nothing left they can pick
            result.append(m["id"])
        return result

    def next(self) -> str | None:
        pool = self.pool()
        return model.next_picker(
            self._pickers(),
            self._current(),
            {c["id"]: int(c.get("points") or 0) for c in pool},
        )

    def snapshot(self) -> dict[str, Any] | None:
        pool = self.pool()
        if not pool:
            return None
        chosen = self._current()
        return {
            "week": self.week,
            "next": self.next(),
            "target": int(self.manager.settings.get("pick_points") or 0),
            "pool": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "emoji": c.get("emoji"),
                    "points": int(c.get("points") or 0),
                    "members": list(c.get("members") or []),
                    "picked_by": chosen.get(c["id"]),
                }
                for c in pool
            ],
        }

    def pick(self, member_id: str, chore_id: str) -> dict[str, Any]:
        member = self.manager.member(member_id)
        chore = next((c for c in self.pool() if c["id"] == chore_id), None)
        if chore is None:
            raise ValueError("That chore isn't in the pool")
        chosen = self._current()
        if chore_id in chosen:
            raise ValueError(f"{chore['name']} was already picked")
        if member_id not in (chore.get("members") or [member_id]):
            raise ValueError(f"{chore['name']} isn't one {member['name']} can pick")
        turn = self.next()
        if turn != member_id:
            who = self.manager.member(turn)["name"] if turn else "nobody"
            raise ValueError(f"It's {who}'s turn to pick")
        chosen[chore_id] = member_id
        self.manager.changed()
        return {"chore_id": chore_id, "member_id": member_id, "next": self.next()}

    def unpick(self, chore_id: str) -> None:
        if self._current().pop(chore_id, None) is None:
            raise ValueError("Nobody picked that chore")
        self.manager.changed()

    def forget_member(self, member_id: str) -> None:
        self.chosen = {c: m for c, m in self.chosen.items() if m != member_id}
