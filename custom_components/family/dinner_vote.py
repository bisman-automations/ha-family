"""Vote on dinner.

A parent lists two to ``model.MAX_VOTE_OPTIONS`` choices for a day's dinner
(and optionally when voting closes); everyone taps one on the Family
dashboard, one vote each, and can change it until it closes. When a parent
closes it, or its time comes, the choice with the most votes (a tie: the one
listed first) becomes that day's dinner on the meal plan. One vote at a
time, kept in the Store (``vote``) as {id, day, options, votes, closes,
status, winner}; a closed vote shows its result until the end of its day.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

OPEN = "open"
CLOSED = "closed"


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class DinnerVote:
    """Today's (or a coming day's) dinner vote."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.vote: dict[str, Any] | None = None

    def load(self, data: dict[str, Any]) -> None:
        vote = data.get("vote")
        self.vote = vote if isinstance(vote, dict) else None

    def data(self) -> dict[str, Any]:
        return {"vote": self.vote}

    def start(self, options: Any, day: Any = None, closes: Any = None) -> dict:
        names = []
        for option in options or []:
            text = " ".join(str(option or "").split())
            if text and text.casefold() not in {n.casefold() for n in names}:
                names.append(text[: model.MAX_MEAL_LENGTH])
        if len(names) < 2:
            raise _error("Give at least two choices")
        if len(names) > model.MAX_VOTE_OPTIONS:
            raise _error(f"Give at most {model.MAX_VOTE_OPTIONS} choices")
        today = dt_util.now().date().isoformat()
        when = model.clean_day(day) or today
        if when < today:
            raise _error("Pick today or a day to come")
        if self.vote and self.vote.get("status") == OPEN:
            raise _error("A vote is already going. Close it first.")
        self.vote = {
            "id": uuid4().hex[:12],
            "day": when,
            "options": names,
            "votes": {},
            "closes": model.clean_time(closes, "Voting closes at"),
            "status": OPEN,
            "winner": None,
            "at": dt_util.now().isoformat(),
        }
        self.manager.changed()
        return self.vote

    def cast(self, member_id: str, option: int) -> dict[str, Any]:
        self.manager.member(member_id)
        vote = self.vote
        if not vote or vote.get("status") != OPEN:
            raise _error("There's no vote going on")
        if not 0 <= option < len(vote["options"]):
            raise _error("Pick one of the choices")
        vote["votes"][member_id] = option
        self.manager.changed()
        return vote

    def close(self) -> dict[str, Any]:
        """Count the votes and put the winner on the meal plan."""
        vote = self.vote
        if not vote or vote.get("status") != OPEN:
            raise _error("There's no vote going on")
        winner = model.vote_winner(vote["options"], vote["votes"])
        vote["status"] = CLOSED
        vote["winner"] = winner
        if winner is not None:
            meals = dict(self.manager.meals.get(vote["day"], {}))
            meals["dinner"] = vote["options"][winner]
            self.manager.meals[vote["day"]] = meals
        self.manager.changed()
        return vote

    def cancel(self) -> None:
        if not self.vote:
            raise _error("There's no vote to take down")
        self.vote = None
        self.manager.changed()

    def tick(self, now: datetime) -> None:
        """Close the vote when its time comes (on its day), and drop a closed
        vote once its day is over."""
        vote = self.vote
        if not vote:
            return
        today = now.date().isoformat()
        if vote.get("status") == CLOSED:
            if vote["day"] < today:
                self.vote = None
                self.manager.changed()
            return
        closes = vote.get("closes")
        if vote["day"] < today or (
            closes and vote["day"] == today and now.strftime("%H:%M") >= closes
        ):
            self.close()

    def forget_member(self, member_id: str) -> None:
        if self.vote:
            self.vote["votes"].pop(member_id, None)

    def snapshot(self) -> dict[str, Any] | None:
        vote = self.vote
        if not vote:
            return None
        counts = [0] * len(vote["options"])
        for choice in vote["votes"].values():
            if 0 <= int(choice) < len(counts):
                counts[int(choice)] += 1
        return {**vote, "counts": counts}
