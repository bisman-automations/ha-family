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
