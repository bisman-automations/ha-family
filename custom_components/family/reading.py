"""Reading log: points for time spent reading.

``settings.reading`` is {block_minutes, points, max_minutes}: every
``block_minutes`` read earns ``points``, up to ``max_minutes`` a day (0: no
limit). A child logs minutes (and, if they like, the book) on the Family
dashboard; it's a chore entry (``chore_id`` "reading") that a parent checks
like any chore, so undo and Didn't happen work as usual. It doesn't count
as one of their own chores for the day. Pure helpers plus ``log``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

READING_CHORE = "reading"
HOMEWORK_CHORE = "homework"
# What each log is called, and the setting its rule is in.
LOGS = {READING_CHORE: ("Read", "reading"), HOMEWORK_CHORE: ("Homework", "homework")}
DEFAULT_READING = {"block_minutes": 0, "points": 0, "max_minutes": 120}
MAX_LOG_MINUTES = 600


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def clean_reading(raw: Any) -> dict[str, int]:
    if not raw:
        return dict(DEFAULT_READING)
    if not isinstance(raw, dict):
        raise _error("Reading points need minutes and points")
    block = int(raw.get("block_minutes") or 0)
    points = model.clean_points(raw.get("points") or 0, "Reading points")
    most = int(raw.get("max_minutes") or 0)
    if not 0 <= block <= 240:
        raise _error("Points for every 0 to 240 minutes read")
    if not 0 <= most <= MAX_LOG_MINUTES:
        raise _error(f"At most 0 to {MAX_LOG_MINUTES} minutes a day")
    return {"block_minutes": block, "points": points, "max_minutes": most}


def public_rule(raw: Any) -> dict[str, int] | None:
    """The rule for the dashboards, or None while reading isn't set up."""
    rule = raw or DEFAULT_READING
    return dict(rule) if rule.get("block_minutes") else None


def reading_points(minutes: int, rule: dict[str, int]) -> int:
    """Points for this many minutes: whole blocks only."""
    block = int(rule.get("block_minutes") or 0)
    if block <= 0:
        return 0
    return (minutes // block) * int(rule.get("points") or 0)


def minutes_today(
    entries: Iterable[dict[str, Any]], member_id: str, day, kind: str = READING_CHORE
) -> int:
    return sum(
        int(e.get("minutes") or 0)
        for e in entries
        if e.get("chore_id") == kind
        and e.get("member") == member_id
        and e.get("review") != model.REVIEW_REJECTED
        and model.entry_day(e) == day
    )


def log(
    manager: FamilyManager,
    member_id: str,
    minutes: Any,
    book: Any = None,
    kind: str = READING_CHORE,
) -> dict[str, Any]:
    """Minutes read (or of homework, timed on the dashboard): a chore entry
    worth its whole blocks, checked later."""
    if kind not in LOGS:
        raise _error("Log reading or homework")
    verb, setting = LOGS[kind]
    member = manager.member(member_id)
    rule = manager.settings.get(setting) or DEFAULT_READING
    if not rule.get("block_minutes"):
        raise _error(f"{verb} points aren't set up")
    read = int(minutes or 0)
    if not 1 <= read <= MAX_LOG_MINUTES:
        raise _error(f"Log 1 to {MAX_LOG_MINUTES} minutes")
    now = dt_util.now()
    if manager.away.on(now.date()):
        raise _error("Chores are off while the family is away")
    before = minutes_today(manager.ledger.day(now.date()), member_id, now.date(), kind)
    most = int(rule.get("max_minutes") or 0)
    if most:
        read = min(read, most - before)
        if read <= 0:
            raise _error(f"{member['name']} already logged {most} minutes today")
    # Points for the day's whole blocks, less what earlier logs already got.
    points = reading_points(before + read, rule) - reading_points(before, rule)
    title_book = str(book or "").strip()[:60]
    entry = {
        "id": uuid4().hex[:12],
        "at": now.isoformat(),
        "kind": model.KIND_CHORE,
        "member": member_id,
        "title": f"{verb} {read} minutes" + (f": {title_book}" if title_book else ""),
        "points": points,
        "chore_id": kind,
        "minutes": read,
        "review": model.REVIEW_PENDING,
        "penalty": 0,
    }
    if title_book:
        entry["book"] = title_book
    manager.entries.append(entry)
    manager.changed()
    manager.notices.chore_done(entry, member)
    return entry
