"""Time to leave: a countdown on the Family dashboard on school mornings.

``settings.leave_times`` holds a time for each weekday (Monday "0"), such as
"07:40", and ``settings.leave_warn`` how many minutes before it the
countdown shows (30 by default). Days with no time, and days the family is
away, have none.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from . import model

DEFAULT_WARN = 30
MAX_WARN = 120
SHOW_AFTER = timedelta(minutes=10)


def clean_leave_times(raw: Any) -> dict[str, str]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        from .manager import FamilyError  # noqa: PLC0415

        raise FamilyError("Leave times are one for each day")
    times = {}
    for day, value in raw.items():
        if str(day) not in {str(i) for i in range(7)}:
            continue
        clean = model.clean_time(value, "Leave at")
        if clean:
            times[str(day)] = clean
    return times


def leave_at(settings: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    """Today's time to leave, while it's still to come (or just passed)."""
    time = (settings.get("leave_times") or {}).get(str(now.weekday()))
    if not time:
        return None
    hour, minute = (int(x) for x in time.split(":")[:2])
    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now > at + SHOW_AFTER:
        return None
    warn = int(settings.get("leave_warn") or DEFAULT_WARN)
    return {"at": at.isoformat(), "warn_minutes": warn}
