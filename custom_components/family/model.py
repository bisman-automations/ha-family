"""Chores and rewards rules. Pure module: no Home Assistant imports.

Kept free of Home Assistant so the rules can be tested on their own:
when a chore can be done again, how points are read from a to-do item, and
what a member's balance is.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
import re
from typing import Any

REPEAT_ONCE = "once"
REPEAT_DAILY = "daily"
REPEAT_WEEKLY = "weekly"
# Chores that come back once they're done, not on the calendar:
REPEAT_AFTER_DAYS = "after_days"  # some days after it was last done (repeat_days)
REPEAT_ALWAYS = "always"  # right away: always there
REPEAT_AFTER_CHECK = "after_check"  # once a parent has checked it
REPEATS = (
    REPEAT_DAILY,
    REPEAT_WEEKLY,
    REPEAT_ONCE,
    REPEAT_AFTER_DAYS,
    REPEAT_ALWAYS,
    REPEAT_AFTER_CHECK,
)

# Ledger entry kinds
KIND_CHORE = "chore"
KIND_REWARD = "reward"
KIND_ADJUST = "adjust"
KIND_PENALTY = "penalty"  # extra points taken when a chore didn't happen
KIND_BONUS = (
    "bonus"  # all chores done today, or a streak; kept with the chore that earned it
)

BONUS_ALL_DONE = "all_done"
BONUS_STREAK = "streak"

# Chore review: points are given straight away; a parent then checks.
REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"  # didn't happen: the points are taken back

# Rewards
REWARD_TV_TIME = "tv_time"
REWARD_MUSIC_TIME = "music_time"  # listening time on a speaker, through Media Mgmt
REWARD_CUSTOM = "custom"
REWARD_KINDS = (REWARD_TV_TIME, REWARD_MUSIC_TIME, REWARD_CUSTOM)
GIVEN_PENDING = "to_give"  # a custom reward a parent still has to hand out
GIVEN_DONE = "given"
# The Family dashboard's sections, in their usual order.
SECTIONS = (
    "going",
    "chores",
    "routines",
    "grabs",
    "notes",
    "today",
    "meals",
    "done",
    "rewards",
    "home",
    "lately",
)
# A reward bought together: the points are held until a parent says yes.
GIVEN_APPROVAL = "to_approve"

MAX_POINTS = 10000

# "Feed the dog [5]", "Feed the dog (5 points)", "Feed the dog - 5 pts"
_POINTS = re.compile(
    r"\s*(?:[\[(]\s*(\d{1,4})\s*(?:points?|pts?)?\s*[\])]|[-–:]\s*(\d{1,4})\s*(?:points?|pts?))\s*$",
    re.IGNORECASE,
)


def todo_points(summary: str, default: int) -> tuple[str, int]:
    """A to-do item's chore name and points.

    Points can be written at the end of the item, in brackets or after a
    dash: "Feed the dog [5]", "Feed the dog (5 points)", "Feed the dog - 5
    pts". Otherwise the list's default points apply.
    """
    text = (summary or "").strip()
    match = _POINTS.search(text)
    if not match:
        return text, default
    points = int(match.group(1) or match.group(2))
    name = text[: match.start()].strip() or text
    return name, min(points, MAX_POINTS)


def item_key(name: str) -> str:
    """How a to-do item's points are remembered: by its name, so an item a
    list brings back (a repeating chore) keeps them."""
    return " ".join((name or "").casefold().split())


def todo_item_points(
    summary: str, default: int, rated: dict[str, int] | None
) -> tuple[str, int, bool]:
    """A to-do item's name, points, and whether a parent set them for it.

    Points set for the item on the Parents dashboard win, then points
    written in the item, then the list's points.
    """
    name, points = todo_points(summary, default)
    key = item_key(name)
    if rated and key in rated:
        return name, int(rated[key]), True
    return name, points, False


def period_start(now: datetime, repeat: str) -> datetime | None:
    """When the current period began: today, this week (from Monday), or None
    for a one-off chore (done once, ever)."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if repeat == REPEAT_DAILY:
        return midnight
    if repeat == REPEAT_WEEKLY:
        return midnight - timedelta(days=now.weekday())
    return None


def done_by(
    chore: dict[str, Any], entries: Iterable[dict[str, Any]], now: datetime
) -> set[str]:
    """Members who've done this chore in its current period.

    A chore for anyone is done by whoever did it first; "*" stands for that.
    Completions a parent marked as didn't happen don't count.

    Chores that come back once they're done: ``always`` is never done,
    ``after_check`` is done until a parent checks it, and ``after_days`` is
    done until ``repeat_days`` days after the day it was done.
    """
    repeat = chore.get("repeat", REPEAT_DAILY)
    if repeat == REPEAT_ALWAYS:
        return set()
    start = None
    if repeat == REPEAT_AFTER_DAYS:
        days = max(1, int(chore.get("repeat_days") or 1))
        # Done on Monday with 3 days: back on Thursday.
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight - timedelta(days=days - 1)
    elif repeat != REPEAT_AFTER_CHECK:
        start = period_start(now, repeat)
    done: set[str] = set()
    for entry in entries:
        if (
            entry.get("kind") != KIND_CHORE
            or entry.get("chore_id") != chore["id"]
            or entry.get("review") == REVIEW_REJECTED
        ):
            continue
        if repeat == REPEAT_AFTER_CHECK and entry.get("review") != REVIEW_PENDING:
            continue
        if start is not None and datetime.fromisoformat(entry["at"]) < start:
            continue
        done.add(entry["member"])
    # Up for grabs, or taken in turns: one person does it each time.
    if done and (is_grab(chore) or chore.get("turns")):
        done.add("*")
    return done


def is_grab(chore: dict[str, Any]) -> bool:
    """Up for grabs: whoever's first does it, for extra points.

    Not one of anyone's own chores, so it doesn't count toward the all-done
    bonus or a streak. A chore for nobody in particular always is; one with
    people picked is when it says so (``grab``); one taken in turns never is.
    """
    if chore.get("turns"):
        return False
    if not chore.get("members"):
        return True
    return bool(chore.get("grab"))


def is_own(chore: dict[str, Any], member_id: str) -> bool:
    """One of this member's own chores: theirs to do, not up for grabs."""
    return (
        chore.get("enabled", True)
        and not is_grab(chore)
        and member_id in (chore.get("members") or [])
    )


def can_do(member_id: str, chore: dict[str, Any], done: set[str]) -> bool:
    """Whether this member can do the chore now."""
    if not chore.get("enabled", True):
        return False
    members = chore.get("members") or []
    if members and member_id not in members:
        return False
    if is_grab(chore) or chore.get("turns"):
        return "*" not in done
    return member_id not in done


# ---- set days, hours and turns ---------------------------------------------------


def _minutes(value: Any) -> int | None:
    """Minutes after midnight for "HH:MM", or None."""
    if not value:
        return None
    try:
        hours, _, minutes = str(value).partition(":")
        total = int(hours) * 60 + int(minutes or 0)
    except ValueError:
        return None
    return total if 0 <= total < 24 * 60 else None


def clean_time(value: Any, label: str) -> str | None:
    """ "HH:MM", or None for an empty box."""
    if value is None or value == "":
        return None
    minutes = _minutes(value)
    if minutes is None:
        raise ValueError(f"{label} must be a time like 07:30")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def clean_days(value: Any) -> list[int]:
    """Weekdays, Monday 0 to Sunday 6. Empty: every day."""
    days = sorted({int(d) for d in value or [] if str(d).lstrip("-").isdigit()})
    if any(not 0 <= d <= 6 for d in days):
        raise ValueError("Pick days from Monday to Sunday")
    return [] if len(days) == 7 else days


def on_day(chore: dict[str, Any], day: date) -> bool:
    """Whether the chore is on this day (no days picked: every day)."""
    days = chore.get("days") or []
    return not days or day.weekday() in days


def available(chore: dict[str, Any], now: datetime) -> bool:
    """Whether the chore shows now: on one of its days, between its hours.

    Hours can cross midnight (20:00 to 01:00); after midnight, the day it
    started counts. Only a start: from then on; only an end: until then.
    """
    start = _minutes(chore.get("from_time"))
    end = _minutes(chore.get("until_time"))
    minute = now.hour * 60 + now.minute
    day = now.date()
    if start is None and end is None:
        return on_day(chore, day)
    if start is not None and end is not None and end <= start:
        if minute >= start:
            return on_day(chore, day)
        if minute < end:
            return on_day(chore, day - timedelta(days=1))
        return False
    if start is not None and minute < start:
        return False
    if end is not None and minute >= end:
        return False
    return on_day(chore, day)


def hours_over(chore: dict[str, Any], now: datetime) -> bool:
    """Whether today's hours for the chore have ended (it can't be done
    again today). Hours that cross midnight end tomorrow, so never today."""
    start = _minutes(chore.get("from_time"))
    end = _minutes(chore.get("until_time"))
    if end is None or (start is not None and end <= start):
        return False
    return now.hour * 60 + now.minute >= end


TURN_EVERY_TIME = "time"  # the next person after each time it's done
TURN_EVERY_DAY = "day"
TURN_EVERY_WEEK = "week"
TURN_EVERY = (TURN_EVERY_TIME, TURN_EVERY_DAY, TURN_EVERY_WEEK)


def turn_member(
    chore: dict[str, Any], entries: Iterable[dict[str, Any]], now: datetime
) -> str | None:
    """Whose turn it is, for a chore its people take in turns.

    The turn starts with ``turn_first`` at ``turn_from`` (when it was saved)
    and moves down the list each time it's done, each day or each week. A
    chore that didn't happen doesn't move it on: it's still their turn.
    """
    members = list(chore.get("members") or [])
    if not chore.get("turns") or len(members) < 2:
        return None
    first = chore.get("turn_first")
    start = members.index(first) if first in members else 0
    try:
        since = datetime.fromisoformat(chore["turn_from"])
    except KeyError, TypeError, ValueError:
        since = now
    every = chore.get("turn_every") or TURN_EVERY_TIME
    if every == TURN_EVERY_DAY:
        steps = (now.date() - since.date()).days
    elif every == TURN_EVERY_WEEK:
        monday = now.date() - timedelta(days=now.weekday())
        first_monday = since.date() - timedelta(days=since.weekday())
        steps = (monday - first_monday).days // 7
    else:
        steps = sum(
            1
            for e in entries
            if e.get("kind") == KIND_CHORE
            and e.get("chore_id") == chore["id"]
            and e.get("review") != REVIEW_REJECTED
            and datetime.fromisoformat(e["at"]) >= since
        )
    return members[(start + max(0, steps)) % len(members)]


# How often each person can get a reward: any time, once a day or once a week.
REWARD_LIMITS = (REPEAT_DAILY, REPEAT_WEEKLY)


def reward_used_by(
    reward: dict[str, Any], entries: Iterable[dict[str, Any]], now: datetime
) -> set[str]:
    """Members who already got this reward today or this week (its limit)."""
    limit = reward.get("limit")
    if limit not in REWARD_LIMITS:
        return set()
    start = period_start(now, limit)
    return {
        entry["member"]
        for entry in entries
        if entry.get("kind") == KIND_REWARD
        and entry.get("reward_id") == reward["id"]
        and start is not None
        and datetime.fromisoformat(entry["at"]) >= start
    }


def reward_members(reward: dict[str, Any]) -> list[str] | None:
    """Who can get this reward.

    None means everyone. That is the default, what a reward saved before
    this was recorded becomes (it has no ``members`` key), and what a save
    stores when every current member is selected, so a person added later
    is included. A list of member ids means only those people. An empty
    list means nobody: the reward is unavailable. Removing the last person
    a reward was for leaves the list empty on purpose, so it does not
    quietly become everyone's.
    """
    if "members" not in reward or reward.get("members") is None:
        return None
    members = reward["members"]
    if not isinstance(members, list):
        # Something other than a list must not fall open to everyone.
        return []
    return [str(member_id) for member_id in members]


def reward_for(reward: dict[str, Any], member_id: str) -> bool:
    """Whether this member may redeem the reward or save up for it."""
    members = reward_members(reward)
    return members is None or member_id in members


def reward_visible(reward: dict[str, Any], member_id: str | None) -> bool:
    """Whether a kid-facing page shows this reward.

    On someone's page (``member_id`` set): rewards for everyone, and rewards
    that list them. On everyone's page (``member_id`` is None): only rewards
    for everyone. A reward for nobody is shown on neither.
    """
    members = reward_members(reward)
    if members is None:
        return True
    if member_id is None:
        return False
    return member_id in members


def rewards_for(rewards: Iterable[dict[str, Any]], member_id: str | None) -> list:
    """The rewards ``reward_visible`` keeps for this page."""
    return [reward for reward in rewards if reward_visible(reward, member_id)]


def reward_selection(picked: list[str], family_ids: list[str]) -> list[str] | None:
    """What to store for the people a parent ticked.

    Every current member ticked is everyone (``None``), so a person added
    later is included. A shorter list is only those people. An empty list
    is nobody, and stays empty: it does not become everyone. An empty
    family is not "all of them", so an empty pick stays empty. A new reward
    that leaves the key out is still everyone; that is the caller's job.
    """
    if family_ids and set(picked) == set(family_ids):
        return None
    return list(picked)


def normalize_reward(reward: dict[str, Any]) -> dict[str, Any]:
    """Fill in who a reward is for, for storage from version 2 on.

    A reward with no ``members`` key was saved when every reward was for
    everyone, so it becomes None. An empty list is kept: it means nobody,
    not everyone.
    """
    if "members" in reward:
        return reward
    return {**reward, "members": None}


# A tap on the shared screen can be undone for this long.
UNDO_SECONDS = 60


def can_undo(entry: dict[str, Any], now: datetime) -> bool:
    """A chore not checked yet, or a reward not handed out yet, just now."""
    if (now - datetime.fromisoformat(entry["at"])).total_seconds() > UNDO_SECONDS:
        return False
    if entry.get("group"):
        # Bought together: only while still waiting for a parent.
        return entry.get("given") == GIVEN_APPROVAL
    if entry.get("kind") == KIND_CHORE:
        return entry.get("review") == REVIEW_PENDING
    if entry.get("kind") == KIND_REWARD:
        return entry.get("given") != GIVEN_DONE or "tv" in entry or "speaker" in entry
    return False


# Chores still to check are counted as done right after this long.
AUTO_CHECK = {"day": timedelta(days=1), "week": timedelta(days=7)}


def due_for_auto_check(
    entries: Iterable[dict[str, Any]], now: datetime, after: str | None
) -> list[dict[str, Any]]:
    """Chores still to check that were done longer ago than ``after``."""
    wait = AUTO_CHECK.get(after or "")
    if wait is None:
        return []
    return [
        entry
        for entry in entries
        if entry.get("kind") == KIND_CHORE
        and entry.get("review") == REVIEW_PENDING
        and now - datetime.fromisoformat(entry["at"]) >= wait
    ]


def balance(entries: Iterable[dict[str, Any]], member_id: str) -> int:
    """A member's points: every entry for them, except chores that didn't
    happen."""
    return sum(
        int(e.get("points", 0))
        for e in entries
        if e.get("member") == member_id and e.get("review") != REVIEW_REJECTED
    )


def clean_name(value: Any, label: str = "Name") -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError(f"{label} can't be empty")
    if len(name) > 80:
        raise ValueError(f"{label} is too long")
    return name


def clean_points(value: Any, label: str = "Points", minimum: int = 0) -> int:
    try:
        points = int(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"{label} must be a whole number") from err
    if not minimum <= points <= MAX_POINTS:
        raise ValueError(f"{label} must be from {minimum} to {MAX_POINTS}")
    return points


MAX_QUICK_POINTS = 12


def quick_points(raw: Any) -> list[dict[str, Any]]:
    """Parents' one-tap points buttons: a label, an optional emoji, points
    to give (or, below 0, to take away), and who it's for (``members``:
    None is everyone, a list only those people, [] nobody). Blank or
    0-point rows are dropped."""
    result = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()[:40]
        points = clean_points(
            row.get("points") or 0, f"Points for {label or 'a button'}", -MAX_POINTS
        )
        if not label or not points:
            continue
        members = row.get("members")
        result.append(
            {
                "label": label,
                "emoji": str(row.get("emoji") or "").strip()[:8],
                "points": points,
                "members": (
                    None
                    if not isinstance(members, list)
                    else [str(m) for m in members if m]
                ),
            }
        )
    return result[:MAX_QUICK_POINTS]


def quick_for(button: dict[str, Any], member_id: str) -> bool:
    """Whether a quick points button is shown for that person."""
    members = button.get("members")
    return members is None or member_id in members


# ---- home controls ------------------------------------------------------------------
# Entities a parent puts on the Family dashboard: what each kind of entity does
# when it's tapped, and which actions it allows.

CONTROL_TOGGLE = "toggle"  # on and off
CONTROL_RUN = "run"  # scenes, scripts, buttons
CONTROL_OPEN = "open"  # covers and valves
CONTROL_LOCK = "lock"
CONTROL_MEDIA = "media"  # play and pause
CONTROL_VIEW = "view"  # shows its state only

_KINDS = {
    "light": CONTROL_TOGGLE,
    "switch": CONTROL_TOGGLE,
    "fan": CONTROL_TOGGLE,
    "input_boolean": CONTROL_TOGGLE,
    "humidifier": CONTROL_TOGGLE,
    "siren": CONTROL_TOGGLE,
    "scene": CONTROL_RUN,
    "script": CONTROL_RUN,
    "button": CONTROL_RUN,
    "input_button": CONTROL_RUN,
    "cover": CONTROL_OPEN,
    "valve": CONTROL_OPEN,
    "lock": CONTROL_LOCK,
    "media_player": CONTROL_MEDIA,
}

# Entities that can only be shown.
VIEW_DOMAINS = (
    "sensor",
    "binary_sensor",
    "climate",
    "weather",
    "person",
    "water_heater",
    "input_number",
    "input_select",
    "number",
    "select",
)

CONTROL_DOMAINS = (*_KINDS, *VIEW_DOMAINS)


def control_kind(entity_id: str) -> str | None:
    """What a tap on this entity does, or None when it can't be shown at all."""
    domain = entity_id.partition(".")[0]
    if domain in _KINDS:
        return _KINDS[domain]
    if domain in VIEW_DOMAINS:
        return CONTROL_VIEW
    return None


def control_service(entity_id: str, action: str) -> tuple[str, str]:
    """The (domain, service) an action on this entity calls.

    Raises ValueError for an action the entity doesn't allow.
    """
    domain = entity_id.partition(".")[0]
    kind = control_kind(entity_id)
    services: dict[str, str] = {}
    if kind == CONTROL_TOGGLE:
        services = {"toggle": "toggle", "on": "turn_on", "off": "turn_off"}
    elif kind == CONTROL_RUN:
        services = {"run": "press" if domain.endswith("button") else "turn_on"}
    elif kind == CONTROL_OPEN:
        thing = "cover" if domain == "cover" else "valve"
        services = {
            "open": f"open_{thing}",
            "close": f"close_{thing}",
            "stop": f"stop_{thing}",
        }
    elif kind == CONTROL_LOCK:
        services = {"lock": "lock", "unlock": "unlock"}
    elif kind == CONTROL_MEDIA:
        services = {"play_pause": "media_play_pause"}
    if action not in services:
        raise ValueError(f"{entity_id} can't do {action}")
    return domain, services[action]


# ---- done today, streaks and bonuses -----------------------------------------------


def entry_day(entry: dict[str, Any]) -> date:
    return datetime.fromisoformat(entry["at"]).date()


def chores_done_on(
    entries: Iterable[dict[str, Any]], day: date, member_id: str | None = None
) -> list[dict[str, Any]]:
    """Chores done that day (by one member, or anyone), except ones that
    didn't happen."""
    return [
        e
        for e in entries
        if e.get("kind") == KIND_CHORE
        and e.get("review") != REVIEW_REJECTED
        and (member_id is None or e.get("member") == member_id)
        and entry_day(e) == day
    ]


def all_done_days(entries: Iterable[dict[str, Any]], member_id: str) -> set[date]:
    """Days this member did all of their own chores (the all-done bonus,
    even one of 0 points, marks them; one a parent rejected doesn't count)."""
    return {
        entry_day(e)
        for e in entries
        if e.get("kind") == KIND_BONUS
        and e.get("bonus") == BONUS_ALL_DONE
        and e.get("member") == member_id
        and e.get("review") != REVIEW_REJECTED
    }


def streak(
    entries: Iterable[dict[str, Any]],
    member_id: str,
    today: date,
    has_own: Callable[[date], bool] | None = None,
    since: date | None = None,
    done_today: bool = False,
) -> int:
    """Days in a row this member did all of their own chores, up to today.

    A day with none of their own chores (``has_own`` says) doesn't break it
    and doesn't add to it. It isn't broken yet if today isn't done so far:
    it counts back from yesterday then. ``done_today``: today is done (the
    chore just finished it, before its bonus is saved).

    Before ``since`` (the day this rule began), a day with any chore done
    counts, as it used to, so a streak going on then carries over.
    """
    entries = list(entries)
    done = all_done_days(entries, member_id)
    if done_today:
        done.add(today)
    any_chore = {
        entry_day(e)
        for e in entries
        if e.get("kind") == KIND_CHORE
        and e.get("member") == member_id
        and e.get("review") != REVIEW_REJECTED
    }
    first = min(done | any_chore, default=today)
    since = since or first

    def kept(day: date) -> bool | None:
        """True: counts; False: breaks it; None: a day off."""
        if day < since:
            return day in any_chore
        if day in done:
            return True
        if has_own is not None and not has_own(day):
            return None
        return False

    day = today if kept(today) else today - timedelta(days=1)
    count = 0
    while day >= first:
        result = kept(day)
        if result is False:
            break
        if result:
            count += 1
        day -= timedelta(days=1)
    return count


def next_streak_bonus(days_in_a_row: int, every: int) -> int:
    """The streak's length when it earns its next bonus (7, 14… for 7)."""
    if every <= 0:
        return 0
    return (days_in_a_row // every + 1) * every


def bonus_given(
    entries: Iterable[dict[str, Any]], member_id: str, kind: str, day: date
) -> bool:
    return any(
        e.get("kind") == KIND_BONUS
        and e.get("bonus") == kind
        and e.get("member") == member_id
        and e.get("review") != REVIEW_REJECTED
        and entry_day(e) == day
        for e in entries
    )


def penalty_points(
    override: int | None, chore_penalty: int | None, default: int | None
) -> int:
    """Extra points taken when a chore didn't happen, on top of its own
    points: what the parent typed when checking, else the chore's (or its
    to-do list's), else the family's."""
    for value in (override, chore_penalty, default):
        if value is not None and value != "":
            return max(0, min(int(value), MAX_POINTS))
    return 0


def optional_points(value: Any, label: str) -> int | None:
    """Points, or None for "use the default" (an empty box)."""
    if value is None or value == "":
        return None
    return clean_points(value, label)


def streak_bonus_due(days_in_a_row: int, every: int) -> bool:
    """A streak bonus every ``every`` days in a row (3, 6, 9… for 3)."""
    return every > 0 and days_in_a_row > 0 and days_in_a_row % every == 0


# ---- the weekly summary for parents ---------------------------------------------------


def week_summary(
    members: Iterable[dict[str, Any]],
    entries: list[dict[str, Any]],
    balances: dict[str, int],
    now: datetime,
) -> list[str]:
    """One line per member for the last 7 days: chores done, points earned
    and spent, and their points now."""
    since = now - timedelta(days=7)
    lines = []
    for member in members:
        mine = [
            e
            for e in entries
            if e.get("member") == member["id"]
            and e.get("review") != REVIEW_REJECTED
            and datetime.fromisoformat(e["at"]) >= since
        ]
        chores = sum(1 for e in mine if e.get("kind") == KIND_CHORE)
        earned = sum(
            int(e.get("points", 0)) for e in mine if int(e.get("points", 0)) > 0
        )
        spent = -sum(
            int(e.get("points", 0)) for e in mine if e.get("kind") == KIND_REWARD
        )
        parts = [f"{chores} {'chore' if chores == 1 else 'chores'}", f"+{earned}"]
        if spent:
            parts.append(f"spent {spent}")
        parts.append(f"{balances.get(member['id'], 0)} now")
        lines.append(f"{member['name']}: {', '.join(parts)}")
    return lines


# ---- allowance and money ---------------------------------------------------------------

KIND_ALLOWANCE = "allowance"
DEFAULT_ALLOWANCE_DAY = 6  # Sunday
DEFAULT_ALLOWANCE_HOUR = 8
MAX_POINT_VALUE = 100.0


def week_key(day: date) -> str:
    """The ISO week a day is in, like '2026-W45'."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def allowance_due(
    now: datetime, weekday: int, hour: int, last_week: str | None
) -> str | None:
    """This week's key when its allowance is due and not given yet, else None.

    The allowance is given once a week, at ``hour`` on ``weekday`` (Monday 0)
    or the first check after it. A week missed (Home Assistant off all
    week) isn't made up.
    """
    monday = now.date() - timedelta(days=now.weekday())
    moment = datetime.combine(
        monday + timedelta(days=weekday), time(hour), tzinfo=now.tzinfo
    )
    key = week_key(now.date())
    if now < moment or last_week == key:
        return None
    return key


def clean_point_value(value: Any) -> float | None:
    """What one point is worth in money, or None for no money value."""
    if value is None or value == "":
        return None
    try:
        number = round(float(value), 4)
    except (TypeError, ValueError) as err:
        raise ValueError("What a point is worth needs a number") from err
    if not 0 < number <= MAX_POINT_VALUE:
        raise ValueError(
            f"What a point is worth must be above 0 and at most {MAX_POINT_VALUE:g}"
        )
    return number


# ---- meals and notes -------------------------------------------------------------------

MEALS = ("breakfast", "lunch", "dinner")
MAX_MEAL_LENGTH = 80
MAX_NOTE_LENGTH = 200
MAX_NOTES = 30
KEEP_MEAL_DAYS = 7  # past days kept, so last week's dinners can be looked back on


def clean_meals(raw: Any) -> dict[str, str]:
    """A day's meals: only the meals given, trimmed, empty ones left out."""
    raw = raw if isinstance(raw, dict) else {}
    meals = {}
    for meal in MEALS:
        text = " ".join(str(raw.get(meal) or "").split())
        if len(text) > MAX_MEAL_LENGTH:
            raise ValueError(f"Keep {meal} under {MAX_MEAL_LENGTH} characters")
        if text:
            meals[meal] = text
    return meals


def clean_note(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise ValueError("Write something for the note")
    if len(text) > MAX_NOTE_LENGTH:
        raise ValueError(f"Keep a note under {MAX_NOTE_LENGTH} characters")
    return text


def clean_day(value: Any, label: str = "The date") -> str | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError as err:
        raise ValueError(f"{label} needs a date") from err


def note_current(note: dict[str, Any], today: date) -> bool:
    """A note shows until the end of its last day (or until it's taken down)."""
    until = note.get("until")
    return not until or until >= today.isoformat()


def week_days(today: date, count: int = 7) -> list[str]:
    return [(today + timedelta(days=i)).isoformat() for i in range(count)]


def split_points(cost: int, balances: list[tuple[str, int]]) -> dict[str, int] | None:
    """Share a reward's points between members, as evenly as their points allow.

    Anyone short puts in what they have and the others cover the rest; any
    point left over from an uneven split goes to the first in the list. None
    when they don't have enough between them.
    """
    left = {member: max(0, points) for member, points in balances}
    shares = dict.fromkeys(left, 0)
    remaining = max(0, cost)
    while remaining > 0:
        able = [member for member, _points in balances if left[member] > 0]
        if not able:
            return None
        each, extra = divmod(remaining, len(able))
        for index, member in enumerate(able):
            give = min(left[member], each + (1 if index < extra else 0))
            shares[member] += give
            left[member] -= give
            remaining -= give
    return shares


def names_text(names: list[str]) -> str:
    """ "Alex", "Alex and Sam", "Alex, Sam and Riley"."""
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def event_days(first: date, last: date, today: date, days: int) -> list[str]:
    """The days in the next ``days`` (from today) that an event covers.

    ``first`` and ``last`` are the event's first and last local day.
    """
    end = today + timedelta(days=days - 1)
    start, stop = max(first, today), min(max(first, last), end)
    return [
        (start + timedelta(days=i)).isoformat() for i in range((stop - start).days + 1)
    ]


def todo_due(due: date | datetime | None, now: datetime) -> bool:
    """Whether a to-do item is due: no due date, a day up to today, or a
    time that has come (a time later today isn't due yet)."""
    if due is None:
        return True
    if isinstance(due, datetime):
        return due <= now
    return due <= now.date()


def section_order(order: Iterable[str] | None) -> list[str]:
    """A section order: known sections once each, any missing at the end."""
    seen = [key for key in dict.fromkeys(order or []) if key in SECTIONS]
    return seen + [key for key in SECTIONS if key not in seen]


# ---- family goal --------------------------------------------------------------------
# One target the whole family works toward together ("Pizza night at 200
# points"). It counts points earned from chores and their bonuses since the
# goal started; nothing is spent, so everyone keeps their own points.

GOAL_KINDS = (KIND_CHORE, KIND_BONUS)


def goal_progress(entries: list[dict[str, Any]], since: str | None) -> int:
    """Points earned together since ``since`` (an ISO time)."""
    if not since:
        return 0
    start = datetime.fromisoformat(since)
    total = 0
    for entry in entries:
        if entry.get("kind") not in GOAL_KINDS:
            continue
        if entry.get("review") == REVIEW_REJECTED:
            continue
        if datetime.fromisoformat(entry["at"]) < start:
            continue
        total += max(0, int(entry.get("points", 0)))
    return total


def clean_goal(raw: Any) -> dict[str, Any] | None:
    """A family goal as saved: a name and a target, or None for no goal."""
    if not raw:
        return None
    name = clean_name(raw.get("name"), "The goal's name")
    target = clean_points(raw.get("target") or 0, "The goal")
    if target < 1:
        raise ValueError("The goal must be at least 1 point")
    return {
        "name": name,
        "emoji": str(raw.get("emoji") or "").strip()[:8] or None,
        "target": target,
    }


# ---- speaker reminders --------------------------------------------------------------


def reminder_text(chore: str, names: list[str]) -> str:
    """What a speaker says for a chore still to do."""
    if not names:
        return f"Reminder: {chore}."
    return f"Reminder for {names_text(names)}: {chore}."


# ---- badges ---------------------------------------------------------------------------

KIND_CASHOUT = "cashout"  # points turned into money; a parent pays it out

# (key, emoji, name, what earns it). In the order they show.
BADGES: tuple[tuple[str, str, str, str], ...] = (
    ("first_chore", "🌱", "First chore", "Did a first chore"),
    ("chores_10", "⭐", "10 chores", "Did 10 chores"),
    ("chores_50", "🌟", "50 chores", "Did 50 chores"),
    ("chores_100", "🏆", "100 chores", "Did 100 chores"),
    ("all_done", "🎉", "All done", "Did all their own chores in a day"),
    ("streak_3", "🔥", "3-day streak", "All their own chores 3 days running"),
    ("streak_7", "🔥", "Week streak", "All their own chores 7 days running"),
    ("streak_30", "💎", "30-day streak", "All their own chores 30 days running"),
    ("first_reward", "🎁", "First reward", "Spent points on a first reward"),
    ("cashed_out", "💰", "Cashed out", "Turned points into money"),
)
BADGE_INFO = {key: (emoji, name, text) for key, emoji, name, text in BADGES}


def badges_earned(
    entries: Iterable[dict[str, Any]], member_id: str, streak: int
) -> set[str]:
    """The badges a member's history earns now.

    Chores count when they weren't marked as didn't happen. Badges are kept
    once earned (the caller stores them), so history that ages out doesn't
    take one away.
    """
    chores = 0
    all_done = rewards = cashed = False
    for e in entries:
        if e.get("member") != member_id or e.get("review") == REVIEW_REJECTED:
            continue
        kind = e.get("kind")
        if kind == KIND_CHORE:
            chores += 1
        elif kind == KIND_BONUS and e.get("bonus") == BONUS_ALL_DONE:
            all_done = True
        elif kind == KIND_REWARD and e.get("given") != GIVEN_APPROVAL:
            rewards = True
        elif kind == KIND_CASHOUT:
            cashed = True
    earned = {
        key
        for key, needed in (
            ("first_chore", 1),
            ("chores_10", 10),
            ("chores_50", 50),
            ("chores_100", 100),
        )
        if chores >= needed
    }
    earned |= {
        key
        for key, needed in (("streak_3", 3), ("streak_7", 7), ("streak_30", 30))
        if streak >= needed
    }
    if all_done:
        earned.add("all_done")
    if rewards:
        earned.add("first_reward")
    if cashed:
        earned.add("cashed_out")
    return earned


def badge_list(stored: dict[str, str] | None) -> list[dict[str, Any]]:
    """A member's stored badges ({key: date}) in display order."""
    stored = stored or {}
    return [
        {"key": key, "emoji": emoji, "name": name, "text": text, "at": stored[key]}
        for key, emoji, name, text in BADGES
        if key in stored
    ]


# ---- week by week ---------------------------------------------------------------------


def week_start(day: date) -> date:
    """The Monday of ``day``'s week."""
    return day - timedelta(days=day.weekday())


def weekly_stats(
    entries: Iterable[dict[str, Any]],
    member_ids: Iterable[str],
    today: date,
    weeks: int = 8,
) -> list[dict[str, Any]]:
    """Points earned and spent, and chores done, per member per week.

    The newest week (this one) last. Earned is every positive entry that
    wasn't marked as didn't happen; spent is rewards and cash outs (points
    held for a reward waiting for a yes count too); chores counts chore
    entries that weren't marked as didn't happen.
    """
    first = week_start(today) - timedelta(weeks=weeks - 1)
    ids = list(member_ids)
    table = [
        {
            "week": (first + timedelta(weeks=i)).isoformat(),
            "members": {m: {"earned": 0, "spent": 0, "chores": 0} for m in ids},
        }
        for i in range(weeks)
    ]
    for e in entries:
        member = e.get("member")
        if member not in ids or e.get("review") == REVIEW_REJECTED:
            continue
        try:
            day = datetime.fromisoformat(e["at"]).date()
        except KeyError, TypeError, ValueError:
            continue
        index = (week_start(day) - first).days // 7
        if not 0 <= index < weeks:
            continue
        row = table[index]["members"][member]
        points = int(e.get("points", 0))
        if e.get("kind") in (KIND_REWARD, KIND_CASHOUT):
            row["spent"] += -points
        elif points > 0:
            row["earned"] += points
        if e.get("kind") == KIND_CHORE:
            row["chores"] += 1
    return table


# A hold on someone's rewards lasts at most this long.
MAX_HOLD_DAYS = 90


def held_until(member: dict[str, Any], now: datetime) -> datetime | None:
    """When a hold on this person's rewards ends, or None when there's none now."""
    raw = member.get("rewards_held_until")
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except TypeError, ValueError:
        return None
    if until.tzinfo is None:
        return None
    return until if until > now else None


def hold_end(now: datetime, days: int | None, until: date | None) -> datetime:
    """When a new hold ends: the end of today (days 0), that many days from now,
    or the end of a chosen day. Raises ValueError when that's not ahead."""

    def end_of(day: date) -> datetime:
        return datetime.combine(day + timedelta(days=1), time.min, tzinfo=now.tzinfo)

    if until is not None:
        end = end_of(until)
    elif days is not None:
        if days < 0:
            raise ValueError("Pick how long")
        end = end_of(now.date()) if days == 0 else now + timedelta(days=days)
    else:
        raise ValueError("Pick how long")
    if end <= now:
        raise ValueError("Pick a day that hasn't passed")
    if end - now > timedelta(days=MAX_HOLD_DAYS):
        raise ValueError(f"A hold can last up to {MAX_HOLD_DAYS} days")
    return end


def cashout_points(points: Any, balance: int) -> int:
    """Points to cash out: a whole number from 1 to the member's balance."""
    try:
        value = int(points)
    except TypeError, ValueError:
        raise ValueError("Pick how many points to cash out") from None
    if value < 1:
        raise ValueError("Pick how many points to cash out")
    if value > balance:
        raise ValueError(f"Only {balance} points to cash out")
    return value
