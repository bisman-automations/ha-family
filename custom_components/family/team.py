"""Team chores: everyone on the chore ticks it before anyone's points count.

A chore with ``team`` set and two or more people picked is each of theirs to
tick, but the points wait: an entry made while someone is still to tick has
0 points, with the real points kept in ``team_points`` and ``team_wait``
set. When the last one ticks, every waiting entry of this period gets its
points. Pure, so it can be tested on its own.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import model


def period_entries(
    entries: list[dict[str, Any]], chore: dict[str, Any], now: datetime
) -> list[dict[str, Any]]:
    """This period's entries for the chore that didn't get rejected."""
    start = model.period_start(now, chore.get("repeat", model.REPEAT_DAILY))
    return [
        e
        for e in entries
        if e.get("kind") == model.KIND_CHORE
        and e.get("chore_id") == chore["id"]
        and e.get("review") != model.REVIEW_REJECTED
        and (start is None or datetime.fromisoformat(e["at"]) >= start)
    ]


def still_to_tick(
    entries: list[dict[str, Any]], chore: dict[str, Any], now: datetime
) -> list[str]:
    """Team members who haven't ticked it this period."""
    ticked = {e["member"] for e in period_entries(entries, chore, now)}
    return [m for m in chore.get("members") or [] if m not in ticked]


def settle(
    entries: list[dict[str, Any]], chore: dict[str, Any], now: datetime
) -> list[dict[str, Any]]:
    """Everyone ticked: give each waiting entry its points. Returns them."""
    if still_to_tick(entries, chore, now):
        return []
    paid = []
    for entry in period_entries(entries, chore, now):
        if entry.pop("team_wait", None):
            entry["points"] = int(entry.pop("team_points", 0))
            paid.append(entry)
    return paid
