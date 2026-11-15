"""Chores a device finishes: a robot vacuum back on its dock, the dishwasher
emptied (its door sensor), the washing machine done.

A dashboard chore's ``done_when`` ({entity_id, state}) marks it done when
that device changes to that state. Who gets the points: whoever started the
device from Home Assistant (the user behind its last change, through their
family member); else the one person the chore is for right now (their own,
or whose turn it is). Otherwise it waits on the Family dashboard as
"Who did this?" (``claims``, today's only) until someone says it was them.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .manager import FamilyManager

_LOGGER = logging.getLogger(__name__)
MAX_CLAIMS = 10


class DoneWhen:
    """Watches the devices chores are finished by."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.claims: list[dict[str, Any]] = []
        # The last user who changed each watched device (who started it).
        self._started_by: dict[str, str] = {}
        self._unsub: Callable[[], None] | None = None
        self._watched: tuple[str, ...] = ()

    def load(self, data: dict[str, Any]) -> None:
        self.claims = [c for c in data.get("claims") or [] if isinstance(c, dict)]

    def data(self) -> dict[str, Any]:
        return {"claims": self.claims}

    def _chores(self) -> list[dict[str, Any]]:
        return [
            c
            for c in self.manager.chores
            if (c.get("done_when") or {}).get("entity_id") and c.get("enabled", True)
        ]

    @callback
    def watch(self) -> None:
        """Follow the devices the chores name (again after a chore is saved)."""
        entities = tuple(sorted({c["done_when"]["entity_id"] for c in self._chores()}))
        if entities == self._watched:
            return
        self.stop()
        self._watched = entities
        if entities:
            self._unsub = async_track_state_change_event(
                self.manager.hass, list(entities), self._changed
            )

    @callback
    def stop(self) -> None:
        if self._unsub:
            self._unsub()
        self._unsub = None
        self._watched = ()

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        new, old = event.data["new_state"], event.data["old_state"]
        entity_id = event.data["entity_id"]
        if new is None:
            return
        if new.context.user_id:
            self._started_by[entity_id] = new.context.user_id
        if old is None or old.state == new.state:
            return
        for chore in self._chores():
            rule = chore["done_when"]
            if rule["entity_id"] == entity_id and new.state == rule.get("state"):
                self.manager.hass.async_create_task(
                    self._async_finished(chore["id"], entity_id),
                    f"family done when {chore['id']}",
                )

    async def _async_finished(self, chore_id: str, entity_id: str) -> None:
        manager = self.manager
        try:
            chore = manager.chore(chore_id)
        except Exception:  # noqa: BLE001 - deleted since
            return
        member_id = None
        if user_id := self._started_by.pop(entity_id, None):
            member_id = manager.member_for_user(user_id)
        if member_id is None and len(chore.get("members") or []) == 1:
            member_id = chore["members"][0]
        if member_id is not None:
            try:
                await manager.async_complete(member_id, chore_id)
            except Exception as err:  # noqa: BLE001 - done already, not theirs, off
                _LOGGER.debug("%s finished but wasn't marked done: %s", chore_id, err)
            return
        today = dt_util.now().date().isoformat()
        if any(c["chore_id"] == chore_id and c["day"] == today for c in self.claims):
            return
        self.claims = [c for c in self.claims if c["day"] == today][-MAX_CLAIMS + 1 :]
        self.claims.append(
            {
                "id": uuid4().hex[:12],
                "chore_id": chore_id,
                "name": chore["name"],
                "emoji": chore.get("emoji"),
                "points": int(chore.get("points") or 0),
                "day": today,
                "at": dt_util.now().isoformat(),
            }
        )
        manager.changed()

    def snapshot(self) -> list[dict[str, Any]]:
        today = dt_util.now().date().isoformat()
        return [c for c in self.claims if c["day"] == today]

    async def async_claim(self, claim_id: str, member_id: str) -> dict[str, Any]:
        claim = next((c for c in self.claims if c["id"] == claim_id), None)
        if claim is None:
            raise ValueError("Someone already said it was them")
        result = await self.manager.async_complete(member_id, claim["chore_id"])
        self.claims = [c for c in self.claims if c["id"] != claim_id]
        self.manager.changed()
        return result

    def forget_chore(self, chore_id: str) -> None:
        self.claims = [c for c in self.claims if c["chore_id"] != chore_id]
