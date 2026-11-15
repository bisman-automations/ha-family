"""More than one family goal at a time.

``settings.family_goals`` is a list of {id, name, emoji, target, since,
reached_at}. Every goal counts the chore and bonus points everyone earned
since it began (``model.goal_progress``); nobody spends any, so the same
points count toward each goal. Before 2.13.0 there was one goal in
``settings.family_goal``; it becomes the first one on load. Reaching a goal
fires ``family_goal_reached`` once, with the goal's id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model
from .const import EVENT_GOAL_REACHED

if TYPE_CHECKING:
    from .manager import FamilyManager

MAX_GOALS = 6
# Shown and announced once each on the way to a goal.
MILESTONES = (25, 50, 75)
EVENT_GOAL_MILESTONE = "family_goal_milestone"


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class FamilyGoals:
    """The goals the whole family works toward together."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager

    def load(self) -> None:
        """One goal from before 2.13.0 becomes the first of the list."""
        settings = self.manager.settings
        old = settings.pop("family_goal", None)
        if old and not settings.get("family_goals"):
            settings["family_goals"] = [{**old, "id": old.get("id") or "goal"}]

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.manager.settings.get("family_goals") or []

    def _writable(self) -> list[dict[str, Any]]:
        return self.manager.settings.setdefault("family_goals", [])

    def _get(self, goal_id: str) -> dict[str, Any]:
        for goal in self.items:
            if goal["id"] == goal_id:
                return goal
        raise _error("That goal is gone")

    def save(
        self, raw: dict[str, Any], goal_id: str | None = None, restart: bool = False
    ) -> dict[str, Any]:
        """Add a goal, or change one. A new goal, or starting over, counts
        from now; changing the name or target keeps going."""
        try:
            goal = model.clean_goal(raw)
        except ValueError as err:
            raise _error(str(err)) from err
        if goal is None:
            raise _error("Give the goal a name and a target")
        # Only some of the family (brothers and sisters saving together);
        # None: everyone.
        goal["kids"] = bool(raw.get("kids"))
        picked = [] if goal["kids"] else self.manager.known_members(raw.get("members"))
        goal["members"] = picked if len(picked) >= 2 else None
        if raw.get("members") and not goal["kids"] and goal["members"] is None:
            raise _error("A goal for some of the family needs two or more people")
        now = dt_util.now().isoformat()
        if goal_id:
            old = self._get(goal_id)
            goal["id"] = goal_id
            goal["since"] = now if restart else old.get("since") or now
            if not restart and goal["target"] == old["target"]:
                goal["milestones"] = list(old.get("milestones") or [])
            # A bigger target makes a reached goal open again.
            if (
                not restart
                and old.get("reached_at")
                and goal["target"] <= old["target"]
            ):
                goal["reached_at"] = old["reached_at"]
            goals = self._writable()
            goals[goals.index(old)] = goal
        else:
            if len(self.items) >= MAX_GOALS:
                raise _error(f"The family can work toward up to {MAX_GOALS} goals")
            goal["id"] = uuid4().hex[:12]
            goal["since"] = now
            self._writable().append(goal)
        self.check()
        return goal

    def who(self, goal: dict[str, Any]) -> list[str] | None:
        """The members a goal is for: the kids, the people picked, or None
        for everyone."""
        if goal.get("kids"):
            return self.manager.kid_ids()
        return goal.get("members")

    def forget_member(self, member_id: str) -> None:
        for goal in self.items:
            if goal.get("members"):
                left = [m for m in goal["members"] if m != member_id]
                goal["members"] = left if len(left) >= 2 else None

    def delete(self, goal_id: str) -> None:
        self._writable().remove(self._get(goal_id))

    def save_legacy(self, raw: Any, restart: bool) -> None:
        """The ``family_goal`` setting (before 2.13.0): the first goal."""
        if raw is None:
            if self.items:
                self._writable().pop(0)
            return
        first = self.items[0]["id"] if self.items else None
        self.save(raw, first, restart)

    def check(self) -> None:
        """Goals just reached, or a quarter, half or three quarters of the way:
        say so once each (events to automate on)."""
        for goal in self.items:
            if goal.get("reached_at"):
                continue
            progress = model.goal_progress(
                self.manager.entries, goal.get("since"), self.who(goal)
            )
            done = goal.setdefault("milestones", [])
            for percent in MILESTONES:
                if percent not in done and progress * 100 >= goal["target"] * percent:
                    done.append(percent)
                    if progress < goal["target"]:
                        self.manager.hass.bus.async_fire(
                            EVENT_GOAL_MILESTONE,
                            {
                                "id": goal["id"],
                                "name": goal["name"],
                                "percent": percent,
                            },
                        )
            if progress < goal["target"]:
                continue
            goal["reached_at"] = dt_util.now().isoformat()
            self.manager.hass.bus.async_fire(
                EVENT_GOAL_REACHED,
                {
                    "id": goal["id"],
                    "name": goal["name"],
                    "target": goal["target"],
                    "members": goal.get("members"),
                    "kids": bool(goal.get("kids")),
                },
            )

    def _view(self, goal: dict[str, Any]) -> dict[str, Any]:
        progress = model.goal_progress(
            self.manager.entries, goal.get("since"), self.who(goal)
        )
        return {
            "id": goal["id"],
            "name": goal["name"],
            "emoji": goal.get("emoji"),
            "target": goal["target"],
            "progress": min(progress, goal["target"]),
            "reached": bool(goal.get("reached_at")) or progress >= goal["target"],
            "since": goal.get("since"),
            "members": goal.get("members"),
            "kids": bool(goal.get("kids")),
            "milestone": max(goal.get("milestones") or [0]),
            # Whose points count and whose pages show it (None: everyone's).
            "who": self.who(goal),
        }

    def snapshot(self) -> list[dict[str, Any]]:
        """Every goal, the ones still to reach first (closest first)."""
        views = [self._view(g) for g in self.items]
        return sorted(
            views,
            key=lambda g: (g["reached"], -(g["progress"] / max(g["target"], 1))),
        )

    def first(self) -> dict[str, Any] | None:
        """The goal shown where there's room for one (``family_goal``)."""
        views = self.snapshot()
        return views[0] if views else None
