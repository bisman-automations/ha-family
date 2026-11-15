"""Chore auctions: the lowest bid does it.

A parent puts a chore up for auction ("Clean the garage", up to 30 points)
for a number of minutes. Each child bids how few points they'd do it for
(at most the starting points; a new bid replaces their old one). When the
time is up, or a parent closes it, the lowest bid wins (a tie goes to
whoever bid first) and gets it as a one-off chore of theirs worth their
bid. Auctions live in the Store (``auctions``); closed ones stay a day.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

OPEN = "open"
CLOSED = "closed"
MAX_OPEN = 3
MIN_MINUTES = 5
MAX_MINUTES = 24 * 60
KEEP_CLOSED = timedelta(days=1)


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def winner(bids: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The lowest bid; a tie goes to the earliest."""
    if not bids:
        return None
    return min(bids, key=lambda b: (b["points"], b["at"]))


class Auctions:
    """Chores up for auction."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self.items = [a for a in data.get("auctions") or [] if isinstance(a, dict)]

    def data(self) -> dict[str, Any]:
        return {"auctions": self.items}

    def _get(self, auction_id: str) -> dict[str, Any]:
        for auction in self.items:
            if auction["id"] == auction_id:
                return auction
        raise _error("That auction is over")

    def start(
        self,
        name: Any,
        points: Any,
        minutes: Any,
        emoji: Any = None,
        members: Any = None,
    ) -> dict[str, Any]:
        if len([a for a in self.items if a["status"] == OPEN]) >= MAX_OPEN:
            raise _error(f"Up to {MAX_OPEN} auctions at a time")
        start = model.clean_points(points, "Starting points")
        if start < 1:
            raise _error("Start the auction at 1 point or more")
        length = int(minutes or 0)
        if not MIN_MINUTES <= length <= MAX_MINUTES:
            raise _error(f"An auction runs {MIN_MINUTES} minutes to a day")
        now = dt_util.now()
        auction = {
            "id": uuid4().hex[:12],
            "name": model.clean_name(name, "The chore"),
            "emoji": model.clean_emoji(emoji, 4),
            "points": start,
            "members": self.manager.known_members(members) or None,
            "at": now.isoformat(),
            "closes": (now + timedelta(minutes=length)).isoformat(),
            "bids": [],
            "status": OPEN,
        }
        self.items.append(auction)
        self.manager.changed()
        return auction

    def bid(self, auction_id: str, member_id: str, points: Any) -> dict[str, Any]:
        auction = self._get(auction_id)
        member = self.manager.member(member_id)
        if auction["status"] != OPEN:
            raise _error("That auction is over")
        if auction.get("members") and member_id not in auction["members"]:
            raise _error(f"{auction['name']} isn't up for {member['name']}")
        offer = model.clean_points(points, "Your bid")
        if not 1 <= offer <= auction["points"]:
            raise _error(f"Bid 1 to {auction['points']} points")
        auction["bids"] = [b for b in auction["bids"] if b["member"] != member_id]
        auction["bids"].append(
            {"member": member_id, "points": offer, "at": dt_util.now().isoformat()}
        )
        self.manager.changed()
        return auction

    def close(self, auction_id: str) -> dict[str, Any]:
        """Close it now: the lowest bid gets the chore."""
        auction = self._get(auction_id)
        if auction["status"] != OPEN:
            raise _error("That auction is over")
        self._close(auction)
        self.manager.changed()
        return auction

    def _close(self, auction: dict[str, Any]) -> None:
        auction["status"] = CLOSED
        auction["closed_at"] = dt_util.now().isoformat()
        best = winner(auction["bids"])
        if best is None:
            return
        chore = self.manager.save_chore(
            {
                "name": auction["name"],
                "emoji": auction.get("emoji"),
                "points": best["points"],
                "members": [best["member"]],
                "repeat": model.REPEAT_ONCE,
            }
        )
        auction["winner"] = best["member"]
        auction["won_for"] = best["points"]
        auction["chore_id"] = chore["id"]

    def cancel(self, auction_id: str) -> None:
        auction = self._get(auction_id)
        if auction["status"] != OPEN:
            raise _error("That auction is over")
        self.items.remove(auction)
        self.manager.changed()

    def tick(self, now: datetime) -> None:
        """Every minute: close auctions whose time is up, drop old ones."""
        changed = False
        for auction in list(self.items):
            if (
                auction["status"] == OPEN
                and datetime.fromisoformat(auction["closes"]) <= now
            ):
                self._close(auction)
                changed = True
            elif (
                auction["status"] == CLOSED
                and datetime.fromisoformat(auction["closed_at"]) < now - KEEP_CLOSED
            ):
                self.items.remove(auction)
                changed = True
        if changed:
            self.manager.changed()

    def forget_member(self, member_id: str) -> None:
        for auction in self.items:
            auction["bids"] = [b for b in auction["bids"] if b["member"] != member_id]
            if auction.get("members"):
                auction["members"] = [m for m in auction["members"] if m != member_id]

    def snapshot(self) -> list[dict[str, Any]]:
        """Open auctions show who bid but not how much (the lowest so far is
        shown, so kids know what to beat)."""
        result = []
        for auction in self.items:
            view = {k: v for k, v in auction.items() if k != "bids"}
            best = winner(auction["bids"])
            view["bidders"] = [b["member"] for b in auction["bids"]]
            view["lowest"] = best["points"] if best else None
            view["bids"] = {b["member"]: b["points"] for b in auction["bids"]}
            result.append(view)
        return sorted(result, key=lambda a: (a["status"] != OPEN, a["closes"]))
