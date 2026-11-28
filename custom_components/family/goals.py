"""More than one family goal at a time.

``settings.family_goals`` is a list of {id, name, emoji, target, since,
reached_at, reward}. Every goal counts the chore and bonus points everyone earned
since it began (``model.goal_progress``); nobody spends any, so the same
points count toward each goal. Before 2.13.0 there was one goal in
``settings.family_goal``; it becomes the first one on load. Reaching a goal
fires ``family_goal_reached`` once, with the goal's id.

A goal's ``reward`` (a reward id, or None) is unlocked when it's reached:
one person it's for uses it once, for no points
(``FamilyManager.async_claim_goal_reward``), or with ``reward_each`` each of
them uses it once. Parents are told when it unlocks
(``notices.goal_reached``). A use is a reward entry with
``goal_id`` and ``goal_since``, so starting the goal again unlocks it again
and an undo puts it back.
"""

from __future__ import annotations

from datetime import datetime
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
        reward_id = raw.get("reward") or None
        if reward_id and not any(r["id"] == reward_id for r in self.manager.rewards):
            raise _error("That reward isn't on the list any more")
        goal["reward"] = reward_id
        goal["reward_each"] = bool(reward_id and raw.get("reward_each"))
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

    def _reward(self, goal: dict[str, Any]) -> dict[str, Any] | None:
        """The reward reaching it unlocks, while it's still on the list."""
        reward_id = goal.get("reward")
        if not reward_id:
            return None
        return next((r for r in self.manager.rewards if r["id"] == reward_id), None)

    def claims(self, goal: dict[str, Any]) -> list[dict[str, Any]]:
        """The entries that used this round's reward, oldest first."""
        since = goal.get("since")
        return [
            entry
            for entry in self.manager.ledger.kind(model.KIND_REWARD)
            if entry.get("goal_id") == goal["id"] and entry.get("goal_since") == since
        ]

    def claimable(
        self, goal_id: str, member_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """The goal and its reward, when this member may use it now."""
        goal = self._get(goal_id)
        reward = self._reward(goal)
        if reward is None:
            raise _error("This goal has no reward to use")
        if not goal.get("reached_at") and self.progress(goal) < goal["target"]:
            raise _error(f"{goal['name']} isn't reached yet")
        who = self.who(goal)
        if who is not None and member_id not in who:
            raise _error(f"{reward['name']} is for the people working on this goal")
        used = self.claims(goal)
        if goal.get("reward_each"):
            if any(entry["member"] == member_id for entry in used):
                name = self.manager.member(member_id)["name"]
                raise _error(f"{name} used {reward['name']} already")
        elif used:
            raise _error(f"{reward['name']} has been used already")
        return goal, reward

    def forget_reward(self, reward_id: str) -> None:
        """A deleted reward: goals that unlocked it unlock nothing now."""
        for goal in self.items:
            if goal.get("reward") == reward_id:
                goal["reward"] = None

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
            progress = self.progress(goal)
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
            if reward := self._reward(goal):
                self.manager.notices.goal_reached(
                    goal, reward["name"], bool(goal.get("reward_each"))
                )
            self.manager.hass.bus.async_fire(
                EVENT_GOAL_REACHED,
                {
                    "id": goal["id"],
                    "name": goal["name"],
                    "target": goal["target"],
                    "members": goal.get("members"),
                    "kids": bool(goal.get("kids")),
                    "reward": (self._reward(goal) or {}).get("name"),
                },
            )

    def progress(self, goal: dict[str, Any]) -> int:
        """Points toward it: only entries since it began are read."""
        since = goal.get("since")
        if not since:
            return 0
        recent = self.manager.ledger.since(datetime.fromisoformat(since))
        return model.goal_progress(recent, since, self.who(goal))

    def _view(self, goal: dict[str, Any]) -> dict[str, Any]:
        progress = self.progress(goal)
        reward = self._reward(goal)
        used = self.claims(goal) if reward else []
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
            # What reaching it unlocks, and who used it this time round.
            "reward": {
                "id": reward["id"],
                "name": reward["name"],
                "emoji": reward.get("emoji"),
            }
            if reward
            else None,
            # One use for the goal, or one each (``reward_each``).
            "reward_each": bool(goal.get("reward_each")) and reward is not None,
            "reward_used_by": used[0]["member"] if used else None,
            "reward_given": used[0].get("given") if used else None,
            "reward_used": [entry["member"] for entry in used],
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
