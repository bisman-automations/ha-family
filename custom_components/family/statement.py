"""A pocket money statement: one person's month, like a bank statement.

Points at the start of the month, every entry in it (earned, spent, given,
taken away), totals, and the points at the end. Rejected entries don't
count. Pure: no Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from . import model

SPENT_KINDS = {model.KIND_REWARD, model.KIND_CASHOUT}
GIVE_KIND = "give"


def month_bounds(today: date, months_ago: int) -> tuple[date, date]:
    """The first day of the month, and the first day of the next."""
    year, month = today.year, today.month - months_ago
    while month < 1:
        month += 12
        year -= 1
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def statement(
    entries: list[dict[str, Any]],
    member_id: str,
    carried: int,
    start: date,
    end: date,
) -> dict[str, Any]:
    counted = [
        e
        for e in entries
        if e.get("member") == member_id and e.get("review") != model.REVIEW_REJECTED
    ]
    first, last = start.isoformat(), end.isoformat()
    opening = carried + sum(int(e["points"]) for e in counted if e["at"][:10] < first)
    lines = sorted(
        (e for e in counted if first <= e["at"][:10] < last), key=lambda e: e["at"]
    )
    earned = sum(int(e["points"]) for e in lines if int(e["points"]) > 0)
    spent = -sum(
        int(e["points"])
        for e in lines
        if e.get("kind") in SPENT_KINDS and int(e["points"]) < 0
    )
    given = -sum(int(e["points"]) for e in lines if e.get("kind") == GIVE_KIND)
    other = -sum(
        int(e["points"])
        for e in lines
        if int(e["points"]) < 0 and e.get("kind") not in SPENT_KINDS | {GIVE_KIND}
    )
    return {
        "start": first,
        "end": last,
        "opening": opening,
        "earned": earned,
        "spent": spent,
        "given": given,
        "taken": other,
        "closing": opening + sum(int(e["points"]) for e in lines),
        "lines": [
            {
                "at": e["at"],
                "title": e.get("title", ""),
                "kind": e.get("kind"),
                "points": int(e["points"]),
            }
            for e in lines
        ],
    }
