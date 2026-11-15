"""Asking for a reward that isn't on the list.

A child asks on the Family dashboard ("Sleepover", maybe with how many
points they think it's worth). The parents' phones are told (with Notify
when something's done), and a parent says yes, with the points it costs, or
no. A yes adds the reward for that child only. Requests live in the Store
(``requests``) as {id, member, name, emoji, points, at, status}; an answered
one stays a few days so the child can see it, then it's dropped.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

PENDING = "pending"
APPROVED = "approved"
DECLINED = "declined"
MAX_PENDING = 5
KEEP_ANSWERED = timedelta(days=3)


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class RewardRequests:
    """Rewards the kids asked for."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self.items = [r for r in data.get("requests") or [] if isinstance(r, dict)]

    def data(self) -> dict[str, Any]:
        return {"requests": self.items}

    def prune(self, now: datetime) -> bool:
        keep = [
            r
            for r in self.items
            if r.get("status") == PENDING
            or datetime.fromisoformat(r.get("answered_at") or r["at"])
            >= now - KEEP_ANSWERED
        ]
        changed = len(keep) != len(self.items)
        self.items = keep
        return changed

    def _get(self, request_id: str) -> dict[str, Any]:
        for request in self.items:
            if request["id"] == request_id:
                return request
        raise _error("That request is gone")

    def ask(
        self, member_id: str, name: Any, emoji: Any = None, points: Any = None
    ) -> dict[str, Any]:
        member = self.manager.member(member_id)
        pending = [
            r
            for r in self.items
            if r["member"] == member_id and r.get("status") == PENDING
        ]
        if len(pending) >= MAX_PENDING:
            raise _error(
                f"{member['name']} already asked for {MAX_PENDING} things. "
                "Wait for a parent to answer those."
            )
        request = {
            "id": uuid4().hex[:12],
            "member": member_id,
            "name": model.clean_name(name, "What you'd like"),
            "emoji": model.clean_emoji(emoji, 4),
            "points": model.optional_points(points, "Points"),
            "at": dt_util.now().isoformat(),
            "status": PENDING,
        }
        self.items.append(request)
        self.manager.changed()
        self.manager.notices.reward_requested(request, member)
        return request

    def cancel(self, request_id: str) -> None:
        """The child takes it back before a parent answers."""
        request = self._get(request_id)
        if request.get("status") != PENDING:
            raise _error("A parent already answered that")
        self.items.remove(request)
        self.manager.notices.clear(request_id)
        self.manager.changed()

    def decide(
        self, request_id: str, approved: bool, points: Any = None
    ) -> dict[str, Any]:
        """A parent's yes (with what it costs) or no."""
        request = self._get(request_id)
        if request.get("status") != PENDING:
            raise _error("That request was already answered")
        reward = None
        if approved:
            cost = model.clean_points(
                points if points is not None else request.get("points"),
                "What it costs",
            )
            reward = self.manager.save_reward(
                {
                    "name": request["name"],
                    "emoji": request.get("emoji"),
                    "points": cost,
                    "kind": model.REWARD_CUSTOM,
                    "members": [request["member"]],
                }
            )
            request["points"] = cost
            request["reward_id"] = reward["id"]
        request["status"] = APPROVED if approved else DECLINED
        request["answered_at"] = dt_util.now().isoformat()
        self.manager.notices.clear(request_id)
        self.manager.changed()
        return {"request": request, "reward": reward}

    def forget_member(self, member_id: str) -> None:
        self.items[:] = [r for r in self.items if r.get("member") != member_id]

    def snapshot(self) -> list[dict[str, Any]]:
        return sorted((dict(r) for r in self.items), key=lambda r: r["at"])
