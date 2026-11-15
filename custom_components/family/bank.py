"""Screen-time bank: TV minutes not used today are saved for later.

A member with ``bank_tv`` (a TV Mgmt TV, for a TV that child uses) has the
minutes that TV had left at the end of each day (TV Mgmt's "time remaining
today" sensor, read at ``DEPOSIT_AT``) added to their bank, up to
``bank_max`` minutes in it. They spend saved minutes on the Family
dashboard: TV Mgmt gives that TV the extra time for today. The bank is in
the Store (``bank``: {minutes: {member: n}, day, log}).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import TV_MGMT_DOMAIN

if TYPE_CHECKING:
    from .manager import FamilyManager

DEPOSIT_AT = time(23, 55)
DEFAULT_MAX = 120
MAX_BANK = 600
KEEP_LOG = 30
TIME_LEFT_KEY = "time_remaining_today"


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def deposit(balance: int, left: float | None, cap: int) -> int:
    """Minutes added to a bank holding ``balance``: what's left, up to the cap."""
    if left is None or left <= 0:
        return 0
    return max(0, min(int(left), cap - balance))


class ScreenBank:
    """Saved TV minutes per member."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.minutes: dict[str, int] = {}
        self.day: str | None = None
        self.log: list[dict[str, Any]] = []

    def load(self, data: dict[str, Any]) -> None:
        bank = data.get("bank") or {}
        self.minutes = {k: int(v) for k, v in (bank.get("minutes") or {}).items()}
        self.day = bank.get("day")
        self.log = list(bank.get("log") or [])[-KEEP_LOG:]

    def data(self) -> dict[str, Any]:
        return {"bank": {"minutes": self.minutes, "day": self.day, "log": self.log}}

    def _left(self, tv: str) -> float | None:
        """What TV Mgmt says this TV has left today, in minutes."""
        entity_id = er.async_get(self.manager.hass).async_get_entity_id(
            "sensor", TV_MGMT_DOMAIN, f"{tv}_{TIME_LEFT_KEY}"
        )
        state = self.manager.hass.states.get(entity_id) if entity_id else None
        try:
            return float(state.state) if state else None
        except ValueError:
            return None  # unknown or unavailable: nothing saved

    def tick(self, now: datetime) -> None:
        """Once a day, just before midnight: save what each TV has left."""
        today = now.date().isoformat()
        if self.day == today or now.time() < DEPOSIT_AT:
            return
        self.day = today
        if self.manager.away.on(now.date()):
            self.manager.changed()
            return
        for member in self.manager.members:
            tv = member.get("bank_tv")
            if not tv:
                continue
            cap = int(member.get("bank_max") or DEFAULT_MAX)
            balance = self.minutes.get(member["id"], 0)
            added = deposit(balance, self._left(tv), cap)
            if added:
                self.minutes[member["id"]] = balance + added
                self._note(member["id"], added, "Saved from today")
        self.manager.changed()

    def _note(self, member_id: str, minutes: int, what: str) -> None:
        self.log.append(
            {
                "at": dt_util.now().isoformat(),
                "member": member_id,
                "minutes": minutes,
                "what": what,
            }
        )
        self.log = self.log[-KEEP_LOG:]

    async def async_spend(self, member_id: str, minutes: Any) -> int:
        """Use saved minutes: TV Mgmt gives the member's TV that much more today."""
        member = self.manager.member(member_id)
        tv = member.get("bank_tv")
        if not tv:
            raise _error(f"{member['name']} doesn't have a screen-time bank")
        want = int(minutes or 0)
        have = self.minutes.get(member_id, 0)
        if want < 1:
            raise _error("Use at least 1 minute")
        if want > have:
            raise _error(f"{member['name']} has {have} minutes saved")
        await self.manager.async_grant_tv_time(
            tv, want, False, f"{member['name']}'s saved screen time"
        )
        self.minutes[member_id] = have - want
        self._note(member_id, -want, "Used")
        self.manager.changed()
        return self.minutes[member_id]

    def forget_member(self, member_id: str) -> None:
        self.minutes.pop(member_id, None)

    def snapshot(self) -> dict[str, int]:
        return {
            m["id"]: self.minutes.get(m["id"], 0)
            for m in self.manager.members
            if m.get("bank_tv")
        }
