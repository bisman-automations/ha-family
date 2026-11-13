"""Routines: step-by-step checklists such as Morning or Bedtime.

A parent makes a routine (its steps, who does it, which days and hours, and
the points for finishing it). On the Family dashboard each person ticks the
steps off; the last step finishes it, which is recorded like a chore done:
points straight away, and it waits under To check for a parent. Which steps
are ticked is kept for today only.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid

from homeassistant.util import dt as dt_util

from . import model
from .const import EVENT_CHORE_DONE

if TYPE_CHECKING:
    from .manager import FamilyManager

MAX_STEPS = 20


class Routines:
    """The family's routines and today's ticked steps."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []
        # Today's ticked steps: {"day": ISO date, "steps": {routine id:
        # {member id: [step numbers]}}}. An older day is dropped.
        self._progress: dict[str, Any] = {}

    # ---- storage --------------------------------------------------------------

    def load(self, data: dict[str, Any]) -> None:
        self.items = [r for r in data.get("routines") or [] if isinstance(r, dict)]
        self._progress = dict(data.get("routine_steps") or {})

    def data(self) -> dict[str, Any]:
        return {"routines": self.items, "routine_steps": self._progress}

    def _today(self, now: datetime) -> dict[str, dict[str, list[int]]]:
        day = now.date().isoformat()
        if self._progress.get("day") != day:
            self._progress = {"day": day, "steps": {}}
        return self._progress["steps"]

    # ---- editing (Parents dashboard) -----------------------------------------------

    def save(self, raw: dict[str, Any]) -> dict[str, Any]:
        steps = [
            str(s).strip()[:80]
            for s in (raw.get("steps") or [])
            if str(s or "").strip()
        ][:MAX_STEPS]
        if not steps:
            raise ValueError("Give the routine at least one step")
        routine = {
            "id": raw.get("id") or uuid.uuid4().hex[:12],
            "name": model.clean_name(raw.get("name"), "The routine's name"),
            "emoji": (raw.get("emoji") or "").strip()[:8] or None,
            "points": model.clean_points(raw.get("points") or 0),
            "members": self.manager.known_members(raw.get("members")),
            "steps": steps,
            "days": model.clean_days(raw.get("days")),
            "from_time": model.clean_time(raw.get("from_time"), "From"),
            "until_time": model.clean_time(raw.get("until_time"), "Until"),
            "enabled": bool(raw.get("enabled", True)),
        }
        for index, item in enumerate(self.items):
            if item["id"] == routine["id"]:
                self.items[index] = routine
                break
        else:
            self.items.append(routine)
        return routine

    def forget_member(self, member_id: str) -> None:
        for routine in self.items:
            routine["members"] = [m for m in routine["members"] if m != member_id]

    # ---- today ------------------------------------------------------------------

    def _who(self, routine: dict[str, Any]) -> list[str]:
        """Who does it: the people picked, or everyone."""
        known = [m["id"] for m in self.manager.members]
        picked = [m for m in routine.get("members") or [] if m in known]
        return picked or known

    def _finished(self, routine_id: str, member_id: str, now: datetime) -> bool:
        """Whether they finished it today (and it wasn't marked didn't happen)."""
        day = now.date()
        for entry in self.manager.entries:
            if (
                entry.get("routine_id") == routine_id
                and entry.get("member") == member_id
                and entry.get("review") != model.REVIEW_REJECTED
                and dt_util.as_local(dt_util.parse_datetime(entry["at"])).date() == day
            ):
                return True
        return False

    def today(self) -> list[dict[str, Any]]:
        """Routines to do now, with each person's ticked steps."""
        now = dt_util.now()
        steps = self._today(now)
        result = []
        for routine in self.items:
            if not routine.get("enabled", True) or not model.available(routine, now):
                continue
            who = self._who(routine)
            if not who:
                continue
            ticked = steps.get(routine["id"], {})
            result.append(
                {
                    **routine,
                    "who": who,
                    "ticked": {m: list(ticked.get(m, [])) for m in who},
                    "finished": [
                        m for m in who if self._finished(routine["id"], m, now)
                    ],
                }
            )
        return result

    def routine(self, routine_id: str) -> dict[str, Any]:
        for routine in self.items:
            if routine["id"] == routine_id:
                return routine
        raise ValueError("That routine isn't there any more")

    async def async_step(
        self, routine_id: str, member_id: str, step: int, done: bool
    ) -> dict[str, Any]:
        """Tick (or untick) a step. The last one ticked finishes the routine."""
        manager = self.manager
        member = manager.member(member_id)
        routine = self.routine(routine_id)
        now = dt_util.now()
        if not routine.get("enabled", True) or not model.available(routine, now):
            raise ValueError(f"{routine['name']} isn't for right now")
        if member_id not in self._who(routine):
            raise ValueError(f"{routine['name']} isn't {member['name']}'s")
        if not 0 <= step < len(routine["steps"]):
            raise ValueError("That step isn't there any more")
        if self._finished(routine_id, member_id, now):
            raise ValueError(f"{member['name']} already finished {routine['name']}")
        ticked = set(self._today(now).setdefault(routine_id, {}).get(member_id, []))
        if done:
            ticked.add(step)
        else:
            ticked.discard(step)
        self._progress["steps"][routine_id][member_id] = sorted(ticked)
        result: dict[str, Any] = {"ticked": sorted(ticked)}
        if len(ticked) >= len(routine["steps"]):
            result["entry"] = await self._finish(routine, member)
        manager.changed()
        return result

    async def _finish(
        self, routine: dict[str, Any], member: dict[str, Any]
    ) -> dict[str, Any]:
        """Every step ticked: recorded like a chore done."""
        manager = self.manager
        entry = {
            "id": uuid.uuid4().hex[:12],
            "at": dt_util.now().isoformat(),
            "kind": model.KIND_CHORE,
            "member": member["id"],
            "title": routine["name"],
            "points": int(routine.get("points", 0)),
            "routine_id": routine["id"],
            # Never a real chore's id, so chores never count it as theirs.
            "chore_id": f"routine:{routine['id']}",
            "review": model.REVIEW_PENDING,
            "penalty": None,
        }
        parent = await manager.is_parent(member)
        if parent:
            entry["review"] = model.REVIEW_APPROVED
            entry["reviewed_at"] = entry["at"]
            entry["parent"] = True
        manager.entries.append(entry)
        if not parent:
            manager.notices.chore_done(entry, member)
        manager.hass.bus.async_fire(
            EVENT_CHORE_DONE,
            {
                "member": member["name"],
                "member_id": member["id"],
                "chore": routine["name"],
                "routine": True,
                "points": entry["points"],
                "balance": manager.points(member["id"]),
            },
        )
        return entry
