"""The weekly report (and family meeting): a week (Monday to Sunday) for each family member.

Chores done (and which, most first), points earned, spent and kept, rewards
they got, bonuses, badges earned that week, and their streak now. The
Parents dashboard shows it to print or share; nothing is stored.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

MAX_WEEKS_AGO = 8
BONUS_KINDS = (model.KIND_BONUS, model.KIND_SAVING, model.KIND_BIRTHDAY)


def week_report(manager: FamilyManager, weeks_ago: int = 0) -> dict[str, Any]:
    weeks_ago = max(0, min(int(weeks_ago), MAX_WEEKS_AGO))
    today = dt_util.now().date()
    first = model.week_start(today) - timedelta(weeks=weeks_ago)
    last = first + timedelta(days=6)

    def in_week(entry: dict[str, Any]) -> bool:
        try:
            day = datetime.fromisoformat(entry["at"]).date()
        except KeyError, TypeError, ValueError:
            return False
        return first <= day <= last

    week = [
        e
        for e in manager.entries
        if in_week(e) and e.get("review") != model.REVIEW_REJECTED
    ]
    rejected = [
        e
        for e in manager.entries
        if in_week(e)
        and e.get("review") == model.REVIEW_REJECTED
        and e.get("kind") == model.KIND_CHORE
    ]
    members = []
    for member in manager.members:
        mine = [e for e in week if e.get("member") == member["id"]]
        chores = [e for e in mine if e.get("kind") == model.KIND_CHORE]
        counts = Counter(e["title"] for e in chores)
        rewards = [
            e["title"]
            for e in mine
            if e.get("kind") in (model.KIND_REWARD, model.KIND_CASHOUT)
        ]
        members.append(
            {
                "id": member["id"],
                "name": member["name"],
                "emoji": member.get("emoji"),
                "color": member.get("color"),
                "chores": len(chores),
                "top_chores": [
                    {"name": name, "times": times}
                    for name, times in counts.most_common(5)
                ],
                "earned": sum(
                    int(e.get("points", 0)) for e in mine if int(e.get("points", 0)) > 0
                ),
                "spent": -sum(
                    int(e.get("points", 0))
                    for e in mine
                    if e.get("kind") in (model.KIND_REWARD, model.KIND_CASHOUT)
                ),
                "bonuses": sum(
                    int(e.get("points", 0))
                    for e in mine
                    if e.get("kind") in BONUS_KINDS
                ),
                "rewards": rewards,
                "all_done_days": sum(
                    1
                    for e in mine
                    if e.get("kind") == model.KIND_BONUS
                    and e.get("bonus") == model.BONUS_ALL_DONE
                ),
                "badges": [
                    b
                    for b in model.badge_list(member.get("badges"))
                    if _between(b.get("at"), first, last)
                ],
                "points": manager.points(member["id"]),
                "streak": manager.streak(member["id"]),
                # For the family meeting: chores that didn't happen, and why.
                "didnt": [
                    {"title": e["title"], "reason": e.get("reason"), "at": e["at"]}
                    for e in rejected
                    if e.get("member") == member["id"]
                ],
                # And what's theirs next week: own chores, picks and turns.
                "next_week": manager.kids.next_week(member["id"]),
            }
        )
    days_away = sum(1 for i in range(7) if manager.away.on(first + timedelta(days=i)))
    return {
        "from": first.isoformat(),
        "until": last.isoformat(),
        "weeks_ago": weeks_ago,
        "members": members,
        "days_away": days_away,
        "money": {
            "value": manager.settings.get("point_value"),
            "currency": manager.settings.get("currency") or "",
        }
        if manager.settings.get("point_value")
        else None,
    }


def _between(value: Any, first: date, last: date) -> bool:
    try:
        day = date.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    return first <= day <= last
