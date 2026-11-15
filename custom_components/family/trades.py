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

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .manager import FamilyManager

OFFERED = "offered"
TAKEN = "taken"
APPROVED = "approved"
KIND_TRADE_PAY = "trade_pay"  # points paid for taking someone's chore


def _last_day(trade: dict[str, Any]) -> str:
    """The last day a trade is for (a whole-week one runs to Sunday)."""
    return str(trade.get("until") or trade.get("day") or "")


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
        """Trades still on: today's, and whole-week ones until Sunday."""
        today = dt_util.now().date().isoformat()
        if any(_last_day(t) < today for t in self._items):
            self._items[:] = [t for t in self._items if _last_day(t) >= today]
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
                and trade.get("day", "") <= today <= _last_day(trade)
                and trade.get("chore_id") == chore["id"]
                and trade.get("from") in members
            ):
                members = [trade["to"] if m == trade["from"] else m for m in members]
                members = list(dict.fromkeys(members))
                chore = dict(chore, members=members, traded=trade["id"])
        return chore

    def offer(
        self,
        member_id: str,
        chore_id: str,
        to: str | None = None,
        pay: int = 0,
        week: bool = False,
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
        pay = max(0, int(pay or 0))
        if pay > manager.points(member_id):
            raise _error(f"{member['name']} doesn't have {pay} points to pay")
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
            # Points the offerer pays whoever takes it, on a parent's yes.
            "pay": pay,
        }
        if week:
            # The rest of the week, through Sunday.
            today = dt_util.now().date()
            trade["until"] = (today + timedelta(days=6 - today.weekday())).isoformat()
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
        pay = int(trade.get("pay") or 0)
        if pay:
            if pay > self.manager.points(trade["from"]):
                raise _error(
                    f"{trade['from_name']} doesn't have the {pay} points any more"
                )
            now = dt_util.now().isoformat()
            taker = next(
                (m["name"] for m in self.manager.members if m["id"] == trade["to"]),
                "someone",
            )
            for member, points, title in (
                (trade["from"], -pay, f"Paid {taker} to do {trade['chore']}"),
                (
                    trade["to"],
                    pay,
                    f"Paid by {trade['from_name']} for {trade['chore']}",
                ),
            ):
                self.manager.entries.append(
                    {
                        "id": uuid4().hex[:12],
                        "at": now,
                        "kind": KIND_TRADE_PAY,
                        "member": member,
                        "title": title,
                        "points": points,
                        "trade": trade["id"],
                    }
                )
        trade["status"] = APPROVED
        self.manager.changed()
        return trade

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self.items]
