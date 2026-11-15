"""Family quests: a bigger job in steps, such as clearing out the garage.

A parent sets a quest: {id, name, emoji, members (None: everyone), steps:
[{name, points}], done: [{member, at, entry}]} in the Store (``quests``).
Steps are done in order: the next one only shows once the one before is
done. Whoever does a step gets its points as a bonus (``quest``); a parent
can put the last step back. A finished quest stays until a parent removes
it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

BONUS_QUEST = "quest"
MAX_STEPS = 12
MAX_QUESTS = 6


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class Quests:
    """The family's quests."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.items: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        self.items = [q for q in data.get("quests") or [] if isinstance(q, dict)]

    def data(self) -> dict[str, Any]:
        return {"quests": self.items}

    def _get(self, quest_id: str) -> dict[str, Any]:
        for quest in self.items:
            if quest["id"] == quest_id:
                return quest
        raise _error("That quest is gone")

    def save(self, raw: dict[str, Any]) -> dict[str, Any]:
        steps = []
        for step in raw.get("steps") or []:
            if not isinstance(step, dict) or not str(step.get("name") or "").strip():
                continue
            steps.append(
                {
                    "name": model.clean_name(step.get("name"), "A step"),
                    "points": model.clean_points(step.get("points") or 0),
                }
            )
        if not steps:
            raise _error("Give the quest at least one step")
        if len(steps) > MAX_STEPS:
            raise _error(f"A quest has up to {MAX_STEPS} steps")
        old = next((q for q in self.items if q["id"] == raw.get("id")), None)
        if old is None and len(self.items) >= MAX_QUESTS:
            raise _error(f"Up to {MAX_QUESTS} quests at a time")
        members = raw.get("members")
        quest = {
            "id": old["id"] if old else uuid4().hex[:12],
            "name": model.clean_name(raw.get("name"), "The quest's name"),
            "emoji": model.clean_emoji(raw.get("emoji"), 4),
            "members": None
            if members is None
            else self.manager.known_members(members) or None,
            "steps": steps,
            # Steps already done stay done (as many as there still are).
            "done": (old["done"] if old else [])[: len(steps)],
        }
        if old:
            self.items[self.items.index(old)] = quest
        else:
            self.items.append(quest)
        self.manager.changed()
        return quest

    def delete(self, quest_id: str) -> None:
        self.items.remove(self._get(quest_id))
        self.manager.changed()

    def step(self, quest_id: str, member_id: str) -> dict[str, Any]:
        """Someone did the quest's next step: its points, and the next one opens."""
        quest = self._get(quest_id)
        member = self.manager.member(member_id)
        if quest.get("members") and member_id not in quest["members"]:
            raise _error(f"{quest['name']} isn't {member['name']}'s quest")
        index = len(quest["done"])
        if index >= len(quest["steps"]):
            raise _error(f"{quest['name']} is already finished")
        step = quest["steps"][index]
        entry = {
            "id": uuid4().hex[:12],
            "at": dt_util.now().isoformat(),
            "kind": model.KIND_BONUS,
            "bonus": BONUS_QUEST,
            "member": member_id,
            "title": f"{quest['name']}: {step['name']}",
            "points": step["points"],
            "quest": quest_id,
        }
        self.manager.entries.append(entry)
        quest["done"].append(
            {"member": member_id, "at": entry["at"], "entry": entry["id"]}
        )
        self.manager.changed()
        return entry

    def undo_step(self, quest_id: str) -> None:
        """A parent puts the last step back (its points too)."""
        quest = self._get(quest_id)
        if not quest["done"]:
            raise _error("No step is done yet")
        last = quest["done"].pop()
        self.manager.entries[:] = [
            e for e in self.manager.entries if e["id"] != last.get("entry")
        ]
        self.manager.changed()

    def forget_member(self, member_id: str) -> None:
        for quest in self.items:
            if quest.get("members"):
                quest["members"] = [
                    m for m in quest["members"] if m != member_id
                ] or None

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                **q,
                "next": len(q["done"]) if len(q["done"]) < len(q["steps"]) else None,
                "finished": len(q["done"]) >= len(q["steps"]),
            }
            for q in self.items
        ]
