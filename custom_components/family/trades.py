"""Trading chores: one child offers one of their own chores for today, another
takes it, and a parent says yes.

Trades live in the Store (``trades``) as {id, chore_id, chore, points, from,
to (None: anyone in the family), day, status, at}. Status goes ``offered``
→ ``taken`` (someone took it, waiting for a parent) → ``approved`` (it's
theirs today). A parent's no, or the offerer taking it back, removes it.
An approved trade only changes today: ``apply`` swaps the people on that
chore for the day (``manager._effective``). Trades from other days are
dropped.

Only dashboard chores with people picked can be traded (up for grabs ones
are anyone's already, and to-do items come back by their list).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .manager import FamilyManager

OFFERED = "offered"
TAKEN = "taken"
APPROVED = "approved"


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class Trades:
    """The family's chore trades for today."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self._items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self._items = [t for t in data.get("trades") or [] if isinstance(t, dict)]

    def data(self) -> dict[str, Any]:
        return {"trades": self._items}

    @property
    def items(self) -> list[dict[str, Any]]:
        """Today's trades (older ones are dropped)."""
        today = dt_util.now().date().isoformat()
        if any(t.get("day") != today for t in self._items):
            self._items[:] = [t for t in self._items if t.get("day") == today]
        return self._items

    def _get(self, trade_id: str) -> dict[str, Any]:
        for trade in self.items:
            if trade["id"] == trade_id:
                return trade
        raise _error("That trade is gone")

    def apply(self, chore: dict[str, Any]) -> dict[str, Any]:
        """A dashboard chore as today's approved trades make it."""
        members = list(chore.get("members") or [])
        if not members:
            return chore
        today = dt_util.now().date().isoformat()
        for trade in self._items:
            if (
                trade.get("status") == APPROVED
                and trade.get("day") == today
                and trade.get("chore_id") == chore["id"]
                and trade.get("from") in members
            ):
                members = [trade["to"] if m == trade["from"] else m for m in members]
                members = list(dict.fromkeys(members))
                chore = dict(chore, members=members, traded=trade["id"])
        return chore

    def offer(
        self, member_id: str, chore_id: str, to: str | None = None
    ) -> dict[str, Any]:
        manager = self.manager
        member = manager.member(member_id)
        if to is not None:
            manager.member(to)
            if to == member_id:
                raise _error("Pick someone else to take it")
        chore = next(
            (c for c in manager.chores_for(member_id) if c["id"] == chore_id), None
        )
        if (
            chore is None
            or chore.get("source") != "family"
            or chore.get("grab")
            or member_id not in (chore.get("members") or [])
        ):
            raise _error("Only your own chores for today can be traded")
        if any(
            t["chore_id"] == chore_id and t["from"] == member_id for t in self.items
        ):
            raise _error("You've already offered that one")
        trade = {
            "id": uuid4().hex,
            "chore_id": chore_id,
            "chore": chore["name"],
            "emoji": chore.get("emoji"),
            "points": int(chore.get("points", 0)),
            "from": member_id,
            "from_name": member["name"],
            "to": to,
            "day": dt_util.now().date().isoformat(),
            "status": OFFERED,
            "at": dt_util.now().isoformat(),
        }
        self.items.append(trade)
        manager.changed()
        return trade

    def take(self, trade_id: str, member_id: str) -> dict[str, Any]:
        manager = self.manager
        member = manager.member(member_id)
        trade = self._get(trade_id)
        if trade["status"] != OFFERED:
            raise _error("Someone already took that one")
        if member_id == trade["from"]:
            raise _error("That's your own chore")
        if trade.get("to") not in (None, member_id):
            raise _error("That trade is for someone else")
        if any(c["id"] == trade["chore_id"] for c in manager.chores_for(member_id)):
            raise _error("You already have that chore today")
        trade["to"] = member_id
        trade["status"] = TAKEN
        manager.changed()
        manager.notices.trade_to_approve(trade, member["name"])
        return trade

    def cancel(self, trade_id: str) -> None:
        """The offerer takes it back, before a parent says yes."""
        trade = self._get(trade_id)
        if trade["status"] == APPROVED:
            raise _error("A parent already said yes to that trade")
        self.items.remove(trade)
        self.manager.notices.clear(trade_id)
        self.manager.changed()

    def decide(self, trade_id: str, approved: bool) -> dict[str, Any] | None:
        """A parent's yes or no to a taken trade."""
        trade = self._get(trade_id)
        if trade["status"] != TAKEN:
            raise _error("Nobody has taken that trade yet")
        self.manager.notices.clear(trade_id)
        if not approved:
            self.items.remove(trade)
            self.manager.changed()
            return None
        trade["status"] = APPROVED
        self.manager.changed()
        return trade

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self.items]
