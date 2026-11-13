"""Today's chores as Live Activities on the parents' phones.

Sent to the parents' phones (the same notify actions as the other
notifications), only for children with chores of their own today (parents
aren't counted):

- ``settings.live_activity``: one for the family, how far each child is,
  such as "Alex 3/5 · Sam ✓". It says "All done today!" once everyone has
  finished and stays until the day ends.
- ``settings.live_per_child``: one for each child ("2 of 4 done"). It says
  "All done!" for ``DONE_SECONDS`` once they finish, then goes away.

Both, either or neither can be on. ``settings.live_from`` ("HH:MM") holds them
back until that time, so iOS's 8-hour limit covers the day rather than the
night. Each is pushed only when what it shows changes, and everything is
cleared when it's turned off and at the end of the day.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .manager import FamilyManager

_LOGGER = logging.getLogger(__name__)

PARENTS_PATH = "/family-parents"
FAMILY_PATH = "/family"
DONE_SECONDS = 120


class ChoreActivity:
    """Keeps the parents' Live Activities in step with today's chores."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.hass = manager.hass
        # Tag -> what's on the phones now (or was, for a child who finished).
        self._shown: dict[str, tuple] = {}
        self._pending = False
        self._later: dict[str, Callable[[], None]] = {}  # tag -> cancel a clear

    @property
    def tag(self) -> str:
        return f"family-chores-{self.manager.entry.entry_id}"

    def child_tag(self, member_id: str) -> str:
        return f"{self.tag}-{member_id}"

    @property
    def _on(self) -> bool:
        settings = self.manager.settings
        return bool(settings.get("live_activity") or settings.get("live_per_child"))

    def _started(self, now: datetime) -> bool:
        """Whether today's are showing yet (``live_from``)."""
        start = self.manager.settings.get("live_from")
        return not start or now.strftime("%H:%M") >= start

    @callback
    def schedule(self) -> None:
        """Bring the phones up to date soon (several changes, one push)."""
        if self._pending:
            return
        self._pending = True
        self._spawn(self._async_refresh(), "family live activity")

    @callback
    def tick(self, now: datetime) -> None:
        """Every minute: start today's at the ``live_from`` time."""
        start = self.manager.settings.get("live_from")
        if self._on and start and now.strftime("%H:%M") == start:
            self.schedule()

    def _spawn(self, coro: Coroutine[Any, Any, None], name: str) -> None:
        self.manager.entry.async_create_background_task(self.hass, coro, name)

    async def _async_refresh(self) -> None:
        self._pending = False
        settings = self.manager.settings
        targets = self.manager.notices.targets()
        rows = (
            await self.async_rows()
            if targets and self._on and self._started(dt_util.now())
            else []
        )
        wanted: dict[str, tuple[tuple, dict[str, Any]]] = {}
        if rows and settings.get("live_activity"):
            wanted[self.tag] = (tuple(rows), self._family_message(rows))
        if rows and settings.get("live_per_child"):
            for member_id, name, total, left in rows:
                tag = self.child_tag(member_id)
                wanted[tag] = (
                    (total, left),
                    self._child_message(tag, name, total, left),
                )
        # No longer wanted (turned off, no chores, someone removed): gone.
        for tag in [t for t in self._shown if t not in wanted]:
            await self._async_clear(targets, tag)
        for tag, (key, data) in wanted.items():
            if self._shown.get(tag) == key:
                continue
            child = tag != self.tag
            if child and tag not in self._shown and key[1] == 0:
                continue  # finished before it was ever shown: nothing to say
            self._shown[tag] = key
            self._cancel_later(tag)
            await self._async_send(targets, data)
            if child and key[1] == 0:
                # They finished: "All done!" for a moment, then it goes.
                self._later[tag] = async_call_later(
                    self.hass, DONE_SECONDS, self._clear_later(tag)
                )

    def _family_message(self, rows: list[tuple]) -> dict[str, Any]:
        total = sum(t for _i, _n, t, _l in rows)
        done = sum(t - left for _i, _n, t, left in rows)
        everyone = done >= total
        parts = [
            f"{name} ✓" if left == 0 else f"{name} {t - left}/{t}"
            for _i, name, t, left in rows
        ]
        return {
            "title": "All done today! 🎉" if everyone else "Today's chores",
            "message": " · ".join(parts),
            "data": {
                "tag": self.tag,
                "live_update": True,
                "progress": done,
                "progress_max": total,
                "critical_text": "Done" if everyone else f"{done}/{total}",
                "notification_icon": "mdi:broom",
                "url": PARENTS_PATH,
                "clickAction": PARENTS_PATH,
            },
        }

    @staticmethod
    def _child_message(tag: str, name: str, total: int, left: int) -> dict[str, Any]:
        done = total - left
        return {
            "title": f"{name}: all done! 🎉" if not left else f"{name}'s chores",
            "message": (
                f"All {total} done."
                if not left
                else f"{done} of {total} done · {left} to go"
            ),
            "data": {
                "tag": tag,
                "live_update": True,
                "progress": done,
                "progress_max": total,
                "critical_text": "Done" if not left else f"{done}/{total}",
                "notification_icon": "mdi:check-circle" if not left else "mdi:broom",
                "url": FAMILY_PATH,
                "clickAction": FAMILY_PATH,
            },
        }

    async def async_rows(self) -> list[tuple[str, str, int, int]]:
        """(id, name, their own chores today, how many are left), for each
        child with chores of their own today. Parents aren't counted."""
        manager = self.manager
        rows = []
        for member in manager.members:
            total, left = manager.own_today(member["id"])
            if not total or await manager.is_parent(member):
                continue
            rows.append((member["id"], member["name"], total, left))
        return rows

    def _clear_later(self, tag: str) -> Callable[[Any], None]:
        @callback
        def _clear(_now: Any) -> None:
            self._later.pop(tag, None)
            # Kept in _shown, so a child who finished isn't shown again today.
            self._spawn(
                self._async_send(
                    self.manager.notices.targets(),
                    {"message": "clear_notification", "data": {"tag": tag}},
                ),
                "family live activity",
            )

        return _clear

    def _cancel_later(self, tag: str) -> None:
        if cancel := self._later.pop(tag, None):
            cancel()

    async def _async_clear(self, targets: list[str], tag: str) -> None:
        self._cancel_later(tag)
        self._shown.pop(tag, None)
        await self._async_send(
            targets, {"message": "clear_notification", "data": {"tag": tag}}
        )

    @callback
    def new_day(self) -> None:
        """Yesterday's go; today's start at ``live_from``, or straight away."""
        tags = list(self._shown)
        self.stop()
        self._shown.clear()
        targets = self.manager.notices.targets()
        if targets and tags:
            self._spawn(self._async_clear_all(targets, tags), "family live activity")
        if self._on:
            self.schedule()

    async def _async_clear_all(self, targets: list[str], tags: list[str]) -> None:
        for tag in tags:
            await self._async_send(
                targets, {"message": "clear_notification", "data": {"tag": tag}}
            )

    @callback
    def stop(self) -> None:
        """Cancel the delayed clears (on unload and at the end of the day)."""
        for tag in list(self._later):
            self._cancel_later(tag)

    async def _async_send(self, targets: list[str], data: dict[str, Any]) -> None:
        for target in targets:
            try:
                await self.hass.services.async_call(
                    "notify", target, data, blocking=True
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Family: couldn't update %s: %s", target, err)
