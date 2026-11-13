"""Speaker reminders: a chore still to do is said out loud at its time.

A chore with a ``remind_time`` ("HH:MM") and ``remind_speakers`` (media
players) is announced through the text-to-speech entity picked on the
Parents dashboard (``settings.reminder_tts``), once a day, on its days, and
only while someone still has it to do. The names said are the people who
still have it; a chore for anyone just says its name.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

_LOGGER = logging.getLogger(__name__)


class ChoreReminders:
    """Says chores out loud at their reminder time."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.hass = manager.hass
        # Chore id -> the day it was last said, so a minute that runs twice
        # (or a restart in that minute) says it once.
        self._said: dict[str, str] = {}

    @property
    def wanted(self) -> bool:
        """Whether any chore has a reminder to say."""
        return bool(self.manager.settings.get("reminder_tts")) and any(
            c.get("remind_time") and c.get("remind_speakers")
            for c in self.manager.chores
        )

    @callback
    def check(self, now: datetime) -> None:
        """Say every chore whose reminder time is this minute."""
        tts = self.manager.settings.get("reminder_tts")
        if not tts:
            return
        minute = now.strftime("%H:%M")
        today = now.date().isoformat()
        for chore in self.manager.chores:
            if (
                not chore.get("enabled", True)
                or chore.get("remind_time") != minute
                or not chore.get("remind_speakers")
                or self._said.get(chore["id"]) == today
            ):
                continue
            who = self.manager.still_to_do(chore, now)
            if who is None:
                continue  # done, or not one of its days
            self._said[chore["id"]] = today
            names = [self.manager.member(m)["name"] for m in who]
            self.say(
                list(chore["remind_speakers"]),
                model.reminder_text(chore["name"], names),
            )

    @callback
    def say(self, speakers: list[str], message: str) -> None:
        """Say a message on the speakers, in the background."""
        tts = self.manager.settings.get("reminder_tts")
        if not tts or not speakers:
            return
        self._spawn(self._say(tts, speakers, message), "family reminder")

    def _spawn(self, coro: Coroutine[Any, Any, None], name: str) -> None:
        self.manager.entry.async_create_background_task(self.hass, coro, name)

    async def _say(self, tts: str, speakers: list[str], message: str) -> None:
        try:
            await self.hass.services.async_call(
                "tts",
                "speak",
                {"media_player_entity_id": speakers, "message": message},
                target={"entity_id": tts},
                blocking=True,
            )
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.warning("Couldn't say a chore reminder: %s", err)
