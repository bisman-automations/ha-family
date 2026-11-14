"""Bonuses that come by themselves: the saving bonus and birthdays.

**Saving bonus** (``settings.saving_percent``, ``saving_max``): once a week,
at the allowance's day and hour, each member gets that percent of the
points they kept all week: the lower of their points now and a week ago, so
points earned this week and points spent don't count. Given once per week
(``settings.saving_week``), as a ``saving`` entry.

**Birthday bonus** (``settings.birthday_points``, a member's ``birthday``
as 'MM-DD'): on their birthday they get those points once that year (the
member keeps ``birthday_year``), as a ``birthday`` entry, and the Family
dashboard wishes them a happy birthday.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager


def _entry(member_id: str, kind: str, title: str, points: int, now: datetime) -> dict:
    return {
        "id": uuid4().hex[:12],
        "at": now.isoformat(),
        "kind": kind,
        "member": member_id,
        "title": title,
        "points": points,
    }


def kept_points(manager: FamilyManager, member_id: str, now: datetime) -> int:
    """Points kept all week: the lower of now and a week ago."""
    carried = manager.carried.get(member_id, 0)
    week_ago = carried + model.balance_before(
        manager.entries, member_id, now - timedelta(days=7)
    )
    return max(0, min(manager.points(member_id), week_ago))


def give_saving_bonus(manager: FamilyManager, now: datetime | None = None) -> bool:
    """The weekly saving bonus, when it's due. True when anything changed."""
    settings = manager.settings
    percent = int(settings.get("saving_percent") or 0)
    if percent <= 0:
        return False
    now = now or dt_util.now()
    key = model.allowance_due(
        now,
        int(settings.get("allowance_day", model.DEFAULT_ALLOWANCE_DAY)),
        int(settings.get("allowance_hour", model.DEFAULT_ALLOWANCE_HOUR)),
        settings.get("saving_week"),
    )
    if key is None:
        return False
    most = int(settings.get("saving_max") or 0)
    for member in manager.members:
        bonus = model.saving_bonus(
            kept_points(manager, member["id"], now), percent, most
        )
        if bonus > 0:
            manager.entries.append(
                _entry(
                    member["id"],
                    model.KIND_SAVING,
                    f"Saving bonus ({percent}% of points kept)",
                    bonus,
                    now,
                )
            )
    settings["saving_week"] = key
    return True


def give_birthday_bonus(manager: FamilyManager, now: datetime | None = None) -> bool:
    """Birthday points, once on the day. True when anything changed."""
    now = now or dt_util.now()
    points = int(manager.settings.get("birthday_points") or 0)
    changed = False
    for member in manager.members:
        if not model.birthday_on(member.get("birthday"), now.date()):
            continue
        if member.get("birthday_year") == now.year:
            continue
        member["birthday_year"] = now.year
        changed = True
        if points > 0:
            manager.entries.append(
                _entry(
                    member["id"],
                    model.KIND_BIRTHDAY,
                    "Happy birthday! 🎂",
                    points,
                    now,
                )
            )
    return changed


def birthday_today(member: dict[str, Any], now: datetime | None = None) -> bool:
    return model.birthday_on(member.get("birthday"), (now or dt_util.now()).date())
