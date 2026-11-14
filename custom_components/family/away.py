"""Away: vacation mode.

While the family is away, chores and routines don't show, nothing is
missed, the all-done bonus and streaks skip those days (a day away is a day
off, like a day with none of one's own chores), and the weekly allowance
isn't given. Points, rewards and everything else keep working.

Periods are kept in settings (``away``) as {id, from, until}: ISO days, both
included; no ``until`` means until it's turned off. Turning it off while
away ends the period yesterday (or drops it, if it started today), so today
counts as usual again. Periods stay for ``KEEP_DAYS``, so streaks still
know those days were off.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

KEEP_DAYS = 400
MAX_PERIODS = 20


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


class Away:
    """The family's away periods."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager

    @property
    def periods(self) -> list[dict[str, Any]]:
        periods = self.manager.settings.get("away")
        return periods if isinstance(periods, list) else []

    def _save(self, periods: list[dict[str, Any]]) -> None:
        self.manager.settings["away"] = sorted(periods, key=lambda p: p["from"])
        self.manager.changed()

    def on(self, day: date) -> bool:
        return model.away_on(self.periods, day)

    @property
    def today(self) -> bool:
        return self.on(dt_util.now().date())

    def add(self, start: Any, end: Any = None) -> dict[str, Any]:
        today = dt_util.now().date().isoformat()
        first = model.clean_day(start, "Away from") or today
        last = model.clean_day(end, "Back on")
        if last is not None and last < first:
            raise _error("The last day away can't be before the first")
        if (last or first) < today:
            raise _error("Pick days that haven't passed")
        if len(self.periods) >= MAX_PERIODS:
            raise _error("Remove an old trip first")
        for other in self.periods:
            other_last = other.get("until") or "9999-12-31"
            if first <= other_last and (last or "9999-12-31") >= other["from"]:
                raise _error("That overlaps another time away")
        period = {"id": uuid4().hex[:12], "from": first, "until": last}
        self._save([*self.periods, period])
        return period

    def back(self) -> None:
        """Home again: today counts as usual."""
        today = dt_util.now().date()
        periods = []
        changed = False
        for period in self.periods:
            if model.away_on([period], today):
                changed = True
                if period["from"] < today.isoformat():
                    periods.append(
                        {**period, "until": (today - timedelta(days=1)).isoformat()}
                    )
                continue
            periods.append(period)
        if not changed:
            raise _error("The family isn't away")
        self._save(periods)

    def remove(self, period_id: str) -> None:
        """Take a planned trip off (one that's going on: Back home instead)."""
        period = next((p for p in self.periods if p["id"] == period_id), None)
        if period is None:
            raise _error("That time away is gone")
        if period["from"] <= dt_util.now().date().isoformat():
            raise _error("It has started. Use Back home instead.")
        self._save([p for p in self.periods if p["id"] != period_id])

    def prune(self, today: date) -> bool:
        oldest = (today - timedelta(days=KEEP_DAYS)).isoformat()
        keep = [p for p in self.periods if (p.get("until") or "9999") >= oldest]
        if len(keep) == len(self.periods):
            return False
        self.manager.settings["away"] = keep
        return True

    def snapshot(self) -> dict[str, Any]:
        today = dt_util.now().date()
        current = next((p for p in self.periods if model.away_on([p], today)), None)
        return {
            "now": current,
            "planned": [p for p in self.periods if p["from"] > today.isoformat()],
        }
