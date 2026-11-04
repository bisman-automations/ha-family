"""Chores and rewards rules. Pure module: no Home Assistant imports.

Kept free of Home Assistant so the rules can be tested on their own:
when a chore can be done again, how points are read from a to-do item, and
what a member's balance is.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
import re
from typing import Any

REPEAT_ONCE = "once"
REPEAT_DAILY = "daily"
REPEAT_WEEKLY = "weekly"
REPEATS = (REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_ONCE)

# Ledger entry kinds
KIND_CHORE = "chore"
KIND_REWARD = "reward"
KIND_ADJUST = "adjust"

# Chore review: points are given straight away; a parent then checks.
REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"  # didn't happen: the points are taken back

# Rewards
REWARD_TV_TIME = "tv_time"
REWARD_CUSTOM = "custom"
REWARD_KINDS = (REWARD_TV_TIME, REWARD_CUSTOM)
GIVEN_PENDING = "to_give"  # a custom reward a parent still has to hand out
GIVEN_DONE = "given"

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
    """
    start = period_start(now, chore.get("repeat", REPEAT_DAILY))
    done: set[str] = set()
    for entry in entries:
        if (
            entry.get("kind") != KIND_CHORE
            or entry.get("chore_id") != chore["id"]
            or entry.get("review") == REVIEW_REJECTED
        ):
            continue
        if start is not None and datetime.fromisoformat(entry["at"]) < start:
            continue
        done.add(entry["member"])
    if done and not chore.get("members"):
        done.add("*")
    return done


def can_do(member_id: str, chore: dict[str, Any], done: set[str]) -> bool:
    """Whether this member can do the chore now."""
    if not chore.get("enabled", True):
        return False
    members = chore.get("members") or []
    if members and member_id not in members:
        return False
    if not members:
        return "*" not in done
    return member_id not in done


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
