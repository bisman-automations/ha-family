"""Chores the kids offer to do.

A child suggests a chore on the Family dashboard ("Wash the car", and how
many points they think it's worth). A parent says yes, with the points, or
no. A yes adds it as a one-off chore of that child's. Ideas live in the
Store (``chore_ideas``) like reward requests, and an answered one stays a
few days so the child can see it.
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
MAX_PENDING = 3
KEEP_ANSWERED = timedelta(days=3)


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class ChoreIdeas:
    """Chores the kids suggested."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self.items = [i for i in data.get("chore_ideas") or [] if isinstance(i, dict)]

    def data(self) -> dict[str, Any]:
        return {"chore_ideas": self.items}

    def prune(self, now: datetime) -> bool:
        keep = [
            i
            for i in self.items
            if i.get("status") == PENDING
            or datetime.fromisoformat(i.get("answered_at") or i["at"])
            >= now - KEEP_ANSWERED
        ]
        changed = len(keep) != len(self.items)
        self.items = keep
        return changed

    def _get(self, idea_id: str) -> dict[str, Any]:
        for idea in self.items:
            if idea["id"] == idea_id:
                return idea
        raise _error("That idea is gone")

    def add(
        self, member_id: str, name: Any, emoji: Any = None, points: Any = None
    ) -> dict[str, Any]:
        member = self.manager.member(member_id)
        pending = [
            i
            for i in self.items
            if i["member"] == member_id and i.get("status") == PENDING
        ]
        if len(pending) >= MAX_PENDING:
            raise _error(
                f"{member['name']} already has {MAX_PENDING} ideas waiting. "
                "Wait for a parent to answer those."
            )
        idea = {
            "id": uuid4().hex[:12],
            "member": member_id,
            "name": model.clean_name(name, "The chore"),
            "emoji": model.clean_emoji(emoji, 4),
            "points": model.optional_points(points, "Points"),
            "at": dt_util.now().isoformat(),
            "status": PENDING,
        }
        self.items.append(idea)
        self.manager.changed()
        self.manager.notices.chore_idea(idea, member)
        return idea

    def cancel(self, idea_id: str) -> None:
        idea = self._get(idea_id)
        if idea.get("status") != PENDING:
            raise _error("A parent already answered that")
        self.items.remove(idea)
        self.manager.notices.clear(idea_id)
        self.manager.changed()

    def decide(
        self, idea_id: str, approved: bool, points: Any = None
    ) -> dict[str, Any]:
        idea = self._get(idea_id)
        if idea.get("status") != PENDING:
            raise _error("That idea was already answered")
        chore = None
        if approved:
            worth = model.clean_points(
                points if points is not None else idea.get("points"), "Points"
            )
            chore = self.manager.save_chore(
                {
                    "name": idea["name"],
                    "emoji": idea.get("emoji"),
                    "points": worth,
                    "members": [idea["member"]],
                    "repeat": model.REPEAT_ONCE,
                }
            )
            idea["points"] = worth
            idea["chore_id"] = chore["id"]
        idea["status"] = APPROVED if approved else DECLINED
        idea["answered_at"] = dt_util.now().isoformat()
        self.manager.notices.clear(idea_id)
        self.manager.changed()
        return {"idea": idea, "chore": chore}

    def forget_member(self, member_id: str) -> None:
        self.items[:] = [i for i in self.items if i.get("member") != member_id]

    def snapshot(self) -> list[dict[str, Any]]:
        return sorted((dict(i) for i in self.items), key=lambda i: i["at"])
