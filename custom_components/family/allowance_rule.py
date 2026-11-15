"""Allowance rules: last week's chores change this week's allowance.

``settings.allowance_rule`` is {enabled, boost_at, boost, cut_below, cut}
(percentages). When the allowance is given, each member's share of last
week's days with all of their own chores done (days with none of their own
are left out) decides it: at or over ``boost_at`` the allowance goes up by
``boost`` percent, under ``cut_below`` it goes down by ``cut`` percent.
A week with no days of their own changes nothing. Pure.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

DEFAULT_RULE = {
    "enabled": False,
    "boost_at": 100,
    "boost": 20,
    "cut_below": 50,
    "cut": 25,
}


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def clean_rule(raw: Any) -> dict[str, Any]:
    if not raw:
        return dict(DEFAULT_RULE)
    if not isinstance(raw, dict):
        raise _error("The allowance rule needs its percentages")
    rule: dict[str, Any] = {"enabled": bool(raw.get("enabled"))}
    for key in ("boost_at", "boost", "cut_below", "cut"):
        value = int(raw.get(key) if raw.get(key) is not None else DEFAULT_RULE[key])
        if not 0 <= value <= 100:
            raise _error("Percentages are 0 to 100")
        rule[key] = value
    if rule["cut_below"] > rule["boost_at"]:
        raise _error("The cut has to start below the boost")
    return rule


def last_week_share(
    done_days: set[date], has_own: Callable[[date], bool], today: date
) -> float | None:
    """Share (0 to 1) of last week's days with own chores that were all done."""
    days = [today - timedelta(days=i) for i in range(1, 8)]
    counted = [d for d in days if has_own(d)]
    if not counted:
        return None
    return sum(1 for d in counted if d in done_days) / len(counted)


def adjusted(
    points: int, share: float | None, rule: dict[str, Any]
) -> tuple[int, str | None]:
    """This week's allowance, and what changed it (None: as set)."""
    if not rule.get("enabled") or share is None or points <= 0:
        return points, None
    percent = round(share * 100)
    if percent >= rule["boost_at"] and rule["boost"]:
        return round(
            points * (100 + rule["boost"]) / 100
        ), f"+{rule['boost']}%: {percent}% of days all done"
    if percent < rule["cut_below"] and rule["cut"]:
        return round(
            points * (100 - rule["cut"]) / 100
        ), f"-{rule['cut']}%: {percent}% of days all done"
    return points, None
