"""2.15.0's smaller family tools: points for grades, a theme week, and the
money paid out each month.

**Grades** (``settings.grade_points``: {grade: points}): a parent logs a
report card or test (``grade/add``), and the grade's points are given as a
``grade`` entry, approved straight away.

**Theme week** (``settings.theme_week``: {name, emoji, points, from, until},
ISO days): a week with a theme, such as "No screens before chores". Each
day, each child taps that they kept it (``theme/keep``); it's a chore-like
entry (chore id ``theme``) a parent checks, once a day per child.

**Payouts** (``payouts``): per month and person, the money cashed out and
how much of it was paid. Pure apart from ``theme_today``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

KIND_GRADE = "grade"
THEME_CHORE = "theme"
DEFAULT_GRADES = {"A": 10, "B": 6, "C": 2}
MAX_GRADES = 12
MAX_THEME_DAYS = 14


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def clean_grade_points(raw: Any) -> dict[str, int]:
    if not raw:
        return dict(DEFAULT_GRADES)
    if not isinstance(raw, dict):
        raise _error("Grades need their points")
    grades = {}
    for grade, points in raw.items():
        name = " ".join(str(grade).split())[:12]
        if name:
            grades[name] = model.clean_points(points or 0, f"Points for {name}")
    if not grades or len(grades) > MAX_GRADES:
        raise _error(f"Give 1 to {MAX_GRADES} grades")
    return grades


def add_grade(
    manager: FamilyManager, member_id: str, subject: Any, grade: str, by: str | None
) -> dict[str, Any]:
    member = manager.member(member_id)
    table = manager.settings.get("grade_points") or DEFAULT_GRADES
    if grade not in table:
        raise _error("Pick one of the grades")
    what = " ".join(str(subject or "").split())[:40]
    entry = {
        "id": uuid4().hex[:12],
        "at": dt_util.now().isoformat(),
        "kind": KIND_GRADE,
        "member": member_id,
        "title": f"{grade} in {what}" if what else f"Got an {grade}",
        "points": int(table[grade]),
        "grade": grade,
    }
    if by:
        entry["by"] = by
    manager.entries.append(entry)
    manager.changed()
    manager.hass.bus.async_fire(
        "family_grade_added",
        {
            "member": member["name"],
            "member_id": member_id,
            "grade": grade,
            "points": entry["points"],
        },
    )
    return entry


def clean_theme(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise _error("A theme week needs a name and its days")
    try:
        start = date.fromisoformat(str(raw.get("from")))
        end = date.fromisoformat(str(raw.get("until")))
    except ValueError as err:
        raise _error("Give the theme week's first and last day") from err
    if end < start or (end - start).days >= MAX_THEME_DAYS:
        raise _error(f"A theme week is 1 to {MAX_THEME_DAYS} days")
    return {
        "name": model.clean_name(raw.get("name"), "The theme"),
        "emoji": model.clean_emoji(raw.get("emoji"), 4),
        "points": model.clean_points(raw.get("points") or 0, "Points a day"),
        "from": start.isoformat(),
        "until": end.isoformat(),
    }


def kept_today(entries: list[dict[str, Any]], day: date) -> list[str]:
    return [
        e["member"]
        for e in entries
        if e.get("chore_id") == THEME_CHORE
        and e.get("review") != model.REVIEW_REJECTED
        and model.entry_day(e) == day
    ]


def theme_today(manager: FamilyManager, day: date) -> dict[str, Any] | None:
    """Today's theme, while its week is on, with who kept it today."""
    theme = manager.settings.get("theme_week")
    if not theme or not theme["from"] <= day.isoformat() <= theme["until"]:
        return None
    return {**theme, "kept": kept_today(manager.entries, day)}


def keep_theme(manager: FamilyManager, member_id: str) -> dict[str, Any]:
    """A child kept today's theme: a chore-like entry a parent checks."""
    member = manager.member(member_id)
    now = dt_util.now()
    theme = theme_today(manager, now.date())
    if theme is None:
        raise _error("There's no theme week on")
    if member_id in theme["kept"]:
        raise _error(f"{member['name']} already kept it today")
    entry = {
        "id": uuid4().hex[:12],
        "at": now.isoformat(),
        "kind": model.KIND_CHORE,
        "member": member_id,
        "title": f"Kept the theme: {theme['name']}",
        "points": int(theme["points"]),
        "chore_id": THEME_CHORE,
        "review": model.REVIEW_PENDING,
        "penalty": 0,
    }
    manager.entries.append(entry)
    manager.changed()
    manager.notices.chore_done(entry, member)
    return entry


def payouts(
    entries: list[dict[str, Any]],
    members: list[dict[str, Any]],
    today: date,
    months: int = 6,
) -> list[dict[str, Any]]:
    """Per month (newest first) and person: money cashed out, and paid."""
    rows = []
    for back in range(months):
        year, month = today.year, today.month - back
        while month < 1:
            month += 12
            year -= 1
        people = []
        for member in members:
            asked = paid = 0.0
            for e in entries:
                if (
                    e.get("kind") != model.KIND_CASHOUT
                    or e.get("member") != member["id"]
                ):
                    continue
                at = datetime.fromisoformat(e["at"])
                if (at.year, at.month) != (year, month):
                    continue
                asked += float(e.get("money") or 0)
                if e.get("given") == model.GIVEN_DONE:
                    paid += float(e.get("money") or 0)
            people.append(
                {
                    "member": member["id"],
                    "asked": round(asked, 2),
                    "paid": round(paid, 2),
                }
            )
        rows.append({"month": f"{year}-{month:02d}", "people": people})
    return rows
