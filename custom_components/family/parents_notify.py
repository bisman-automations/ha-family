"""Phone notifications for parents.

When a chore is marked done (or a reward needs handing out), the parents'
phones get a notification with buttons: Done right / Didn't happen, or
Handed out. The Companion app sends a button press back as the
``mobile_app_notification_action`` event; only an admin's phone can act on
it. Once a chore is checked anywhere, its notification is cleared. A weekly
summary goes out on Sunday evening.

Settings (from the Parents dashboard): ``notify_targets`` (notify actions,
such as ``mobile_app_my_phone``), ``notify_done``, ``notify_rewards`` and
``weekly_summary``.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import model
from .const import ACTION_PREFIX, SUMMARY_HOUR, SUMMARY_WEEKDAY

if TYPE_CHECKING:
    from .manager import FamilyManager

_LOGGER = logging.getLogger(__name__)

PARENTS_PATH = "/family-parents"
ACTION_RIGHT = f"{ACTION_PREFIX}RIGHT_"
ACTION_DIDNT = f"{ACTION_PREFIX}DIDNT_"
ACTION_GIVEN = f"{ACTION_PREFIX}GIVEN_"
ACTION_YES = f"{ACTION_PREFIX}YES_"
ACTION_NO = f"{ACTION_PREFIX}NO_"


def tag_for(entry_id: str) -> str:
    return f"family-{entry_id}"


def target_name(service: str) -> str:
    """ "mobile_app_dads_phone" -> "Dads phone"."""
    name = service.removeprefix("mobile_app_").replace("_", " ").strip()
    return name[:1].upper() + name[1:] if name else service


class ParentNotices:
    """Sends the parents' notifications and acts on their buttons."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.hass = manager.hass

    @property
    def _settings(self) -> dict[str, Any]:
        return self.manager.settings

    def targets(self) -> list[str]:
        """The notify actions to use, leaving out any that are gone."""
        return [
            t
            for t in self._settings.get("notify_targets") or []
            if self.hass.services.has_service("notify", t)
        ]

    def _spawn(self, coro: Coroutine[Any, Any, None], name: str) -> None:
        # Never slow down a tap on the shared screen.
        self.manager.entry.async_create_background_task(self.hass, coro, name)

    async def _send(self, data: dict[str, Any]) -> None:
        for target in self.targets():
            try:
                await self.hass.services.async_call(
                    "notify", target, data, blocking=True
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Family: couldn't notify %s: %s", target, err)

    # ---- what's sent ------------------------------------------------------------

    @callback
    def chore_done(self, entry: dict[str, Any], member: dict[str, Any]) -> None:
        if not self._settings.get("notify_done") or not self.targets():
            return
        entry_id = entry["id"]
        data = {
            "title": f"{member['name']} did {entry['title']}",
            "message": f"+{entry['points']} points. Was it done right?",
            "data": {
                "tag": tag_for(entry_id),
                "group": "family",
                "url": PARENTS_PATH,
                "clickAction": PARENTS_PATH,
                "actions": [
                    {"action": f"{ACTION_RIGHT}{entry_id}", "title": "Done right"},
                    {
                        "action": f"{ACTION_DIDNT}{entry_id}",
                        "title": "Didn't happen",
                        "destructive": True,
                    },
                ],
            },
        }
        self._spawn(self._send(data), "family_notify_chore")

    @callback
    def reward_to_give(self, entry: dict[str, Any], member: dict[str, Any]) -> None:
        if not self._settings.get("notify_rewards") or not self.targets():
            return
        entry_id = entry["id"]
        data = {
            "title": f"{member['name']} picked {entry['title']}",
            "message": "Tap Handed out once you've given it.",
            "data": {
                "tag": tag_for(entry_id),
                "group": "family",
                "url": PARENTS_PATH,
                "clickAction": PARENTS_PATH,
                "actions": [
                    {"action": f"{ACTION_GIVEN}{entry_id}", "title": "Handed out"}
                ],
            },
        }
        self._spawn(self._send(data), "family_notify_reward")

    @callback
    def reward_to_approve(
        self, group: str, names: str, reward: str, shares: dict[str, int]
    ) -> None:
        """Members want a reward together: a parent says yes or no."""
        if not self._settings.get("notify_rewards") or not self.targets():
            return
        split = ", ".join(f"{name} {points}" for name, points in shares.items())
        data = {
            "title": f"{names} want {reward} together",
            "message": f"Points: {split}. They're held until you say yes.",
            "data": {
                "tag": tag_for(group),
                "group": "family",
                "url": PARENTS_PATH,
                "clickAction": PARENTS_PATH,
                "actions": [
                    {"action": f"{ACTION_YES}{group}", "title": "Yes"},
                    {
                        "action": f"{ACTION_NO}{group}",
                        "title": "No",
                        "destructive": True,
                    },
                ],
            },
        }
        self._spawn(self._send(data), "family_notify_approve")

    @callback
    def clear(self, entry_id: str) -> None:
        """Take a chore's or reward's notification away: it's been dealt with."""
        if (
            not (
                self._settings.get("notify_done")
                or self._settings.get("notify_rewards")
            )
            or not self.targets()
        ):
            return
        data = {"message": "clear_notification", "data": {"tag": tag_for(entry_id)}}
        self._spawn(self._send(data), "family_notify_clear")

    async def async_weekly(self, now: datetime | None = None) -> None:
        """The week in one notification: each member's chores and points."""
        if not self._settings.get("weekly_summary") or not self.targets():
            return
        manager = self.manager
        now = now or dt_util.now()
        lines = model.week_summary(
            manager.members,
            manager.entries,
            {m["id"]: manager.points(m["id"]) for m in manager.members},
            now,
        )
        waiting = sum(
            1 for e in manager.entries if e.get("review") == model.REVIEW_PENDING
        )
        if waiting:
            lines.append(f"{waiting} {'chore' if waiting == 1 else 'chores'} to check")
        if not lines:
            return
        await self._send(
            {
                "title": "Family this week",
                "message": "\n".join(lines),
                "data": {
                    "tag": "family-week",
                    "group": "family",
                    "url": PARENTS_PATH,
                    "clickAction": PARENTS_PATH,
                },
            }
        )

    @callback
    def weekly_tick(self, now: datetime) -> None:
        """Called every day at SUMMARY_HOUR; sends on Sunday."""
        local = dt_util.as_local(now)
        if local.weekday() == SUMMARY_WEEKDAY and local.hour == SUMMARY_HOUR:
            self._spawn(self.async_weekly(local), "family_weekly_summary")

    # ---- buttons pressed on a phone -------------------------------------------------

    async def async_on_action(self, event: Event) -> None:
        action = str(event.data.get("action") or "")
        if not action.startswith(ACTION_PREFIX):
            return
        user_id = event.context.user_id
        user = await self.hass.auth.async_get_user(user_id) if user_id else None
        if user is None or not user.is_admin:
            _LOGGER.warning(
                "Family: ignored %s from someone who isn't a parent", action
            )
            return
        manager = self.manager
        try:
            if action.startswith(ACTION_RIGHT):
                await manager.async_review(action.removeprefix(ACTION_RIGHT), True)
            elif action.startswith(ACTION_DIDNT):
                await manager.async_review(action.removeprefix(ACTION_DIDNT), False)
            elif action.startswith(ACTION_YES):
                await manager.async_approve(action.removeprefix(ACTION_YES), True)
            elif action.startswith(ACTION_NO):
                await manager.async_approve(action.removeprefix(ACTION_NO), False)
            elif action.startswith(ACTION_GIVEN):
                manager.mark_given(action.removeprefix(ACTION_GIVEN))
        except HomeAssistantError as err:
            # Undone or checked already: nothing to do.
            _LOGGER.info("Family: %s: %s", action, err)
