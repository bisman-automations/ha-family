"""Talking to Family through Assist (a voice speaker, or typing to Assist).

Three kinds of sentence, registered as conversation triggers while Family is
loaded (only when Home Assistant's conversation integration is):

- "I finished feed the dog", "Alex did make your bed": marks the chore done
  for that person, the same as tapping it, so it waits for a parent's check.
- "How many points do I have?", "How many points does Sam have?"
- "What chores do I have left?", "What does Riley have left?"

"I" is whoever is logged in to the Assist device or app, through their
person (``manager.member_for_user``); otherwise a name has to be said.
The matching (``find_member``, ``find_chore``) and the replies are plain
functions so they're tested without a voice pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable
import difflib
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

_LOGGER = logging.getLogger(__name__)

SENTENCES_DONE = [
    "{who} (finished|did|have done|has done) [the] {chore}",
    "{who} (am|is|'m) done with [the] {chore}",
]
SENTENCES_POINTS = [
    "how many points (do|does) {who} have",
    "how many points have I got",
    "what are my points",
]
SENTENCES_LEFT = [
    "what [chores] (do|does) {who} have left [to do]",
    "what's left for {who}",
    "what chores are left for {who}",
]
_ME = {"i", "me", "my", "myself", ""}


def _clean(text: str | None) -> str:
    text = re.sub(r"[^\w\s']", " ", (text or "").casefold())
    return re.sub(r"\s+", " ", text).strip()


def find_member(
    members: Iterable[dict[str, Any]], said: str | None
) -> dict[str, Any] | None:
    """The family member a spoken name means (first name, any case)."""
    said = _clean(said)
    if said.endswith("'s"):
        said = said[:-2]
    if not said:
        return None
    members = list(members)
    for member in members:
        name = _clean(member["name"])
        if said == name or said == name.split(" ")[0]:
            return member
    names = {_clean(m["name"]): m for m in members}
    close = difflib.get_close_matches(said, list(names), n=1, cutoff=0.75)
    return names[close[0]] if close else None


def find_chore(
    chores: Iterable[dict[str, Any]], said: str | None
) -> dict[str, Any] | None:
    """The chore a spoken phrase means: same words, one inside the other, or close."""
    said = _clean(said)
    said = re.sub(r"^(the|my|our) ", "", said)
    if not said:
        return None
    chores = list(chores)
    by_name = {_clean(c["name"]): c for c in chores}
    if said in by_name:
        return by_name[said]
    inside = [c for name, c in by_name.items() if said in name or name in said]
    if len(inside) == 1:
        return inside[0]
    close = difflib.get_close_matches(said, list(by_name), n=1, cutoff=0.6)
    return by_name[close[0]] if close else None


def names_text(items: list[str]) -> str:
    return model.names_text(items)


def is_me(said: str | None) -> bool:
    return _clean(said) in _ME


class Voice:
    """Registers the sentences and answers them."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.hass: HomeAssistant = manager.hass
        self._remove: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        if "conversation" not in self.hass.config.components:
            return
        from homeassistant.helpers.script import ScriptRunResult  # noqa: PLC0415
        from homeassistant.helpers.trigger import (  # noqa: PLC0415
            async_initialize_triggers,
            async_validate_trigger_config,
        )

        removers = []
        for kind, sentences in (
            ("done", SENTENCES_DONE),
            ("points", SENTENCES_POINTS),
            ("left", SENTENCES_LEFT),
        ):

            async def action(
                run_variables: dict[str, Any], context: Any = None, kind: str = kind
            ) -> ScriptRunResult:
                trigger = run_variables.get("trigger") or {}
                try:
                    text = await self.async_answer(
                        kind,
                        trigger.get("slots") or {},
                        ((trigger.get("user_input") or {}).get("context") or {}).get(
                            "user_id"
                        ),
                    )
                except Exception as err:  # noqa: BLE001 - say it, don't crash the pipeline
                    text = str(err) or "Something went wrong."
                return ScriptRunResult(
                    conversation_response=text, service_response=None, variables={}
                )

            try:
                config = await async_validate_trigger_config(
                    self.hass, [{"platform": "conversation", "command": sentences}]
                )
                remove = await async_initialize_triggers(
                    self.hass,
                    config,
                    action,
                    "family",
                    f"Family voice ({kind})",
                    _LOGGER.log,
                )
            except Exception:  # noqa: BLE001 - voice is extra; the rest works without it
                _LOGGER.warning(
                    "Family: couldn't add the Assist sentences", exc_info=True
                )
                continue
            if remove:
                removers.append(remove)

        def _remove_all() -> None:
            for remove in removers:
                remove()

        self._remove = _remove_all

    def stop(self) -> None:
        if self._remove:
            self._remove()
            self._remove = None

    def _who(self, said: str | None, user_id: str | None) -> dict[str, Any] | None:
        manager = self.manager
        if is_me(said):
            member_id = manager.member_for_user(user_id)
            return manager.member(member_id) if member_id else None
        return find_member(manager.members, said)

    async def async_answer(
        self, kind: str, slots: dict[str, Any], user_id: str | None
    ) -> str:
        manager = self.manager
        said_who = slots.get("who")
        member = self._who(said_who, user_id)
        if member is None:
            if is_me(said_who):
                return (
                    "I don't know who you are. Say your name, like "
                    "'Alex finished feed the dog'."
                )
            return f"I couldn't find {said_who} in the family."
        name = member["name"]
        if kind == "points":
            points = manager.points(member["id"])
            return f"{name} has {points} point{'s' if points != 1 else ''}."
        mine = [
            c
            for c in manager.chores_for(member["id"])
            if member["id"] in c.get("can", [])
        ]
        if kind == "left":
            own = [c["name"] for c in mine if not c.get("grab")]
            if not own:
                return f"{name} has nothing left to do right now."
            count = len(own)
            return f"{name} has {count} chore{'s' if count != 1 else ''} left: {names_text(own)}."
        chore = find_chore(mine, slots.get("chore"))
        if chore is None:
            return f"I couldn't find {slots.get('chore')} in {name}'s chores right now."
        entry = await manager.async_complete(member["id"], chore["id"])
        points = int(entry.get("points", 0))
        text = f"Nice, {name}! {chore['name']} is done"
        text += f", +{points} point{'s' if points != 1 else ''}." if points else "."
        if entry.get("review") == model.REVIEW_PENDING:
            text += " A parent will check it."
        badges = manager.take_new_badges(member["id"])
        if badges:
            text += " New badge: " + names_text([b["name"] for b in badges]) + "!"
        return text
