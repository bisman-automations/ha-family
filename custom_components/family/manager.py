"""Family's data: members, chores, rewards and the points ledger.

Everything is kept in one Store and edited from the Parents dashboard.
Chores come from two places: ones added on the dashboard, and the open items
of chosen to-do lists. Finishing a chore gives its points straight away and
leaves it waiting for a parent to check; "didn't happen" takes them back.
Points are spent on rewards: TV time (through TV Mgmt) or anything else, which
a parent then hands out.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
import logging
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import allowance_rule, extras, model, reading, savings, team
from .auctions import Auctions
from .away import Away
from .bank import ScreenBank
from .bingo import Bingo
from .boosts import Boosts
from .calendar_today import DAYS as CALENDAR_DAYS, CalendarToday, clean_calendars
from .challenges import Challenges
from .chore_ideas import ChoreIdeas
from .const import (
    DOMAIN,
    EVENT_BADGE_EARNED,
    EVENT_BONUS,
    EVENT_CHORE_DONE,
    EVENT_CHORE_REVIEWED,
    EVENT_REWARD_REDEEMED,
    EVENT_REWARDS_HELD,
    KEEP_HISTORY_DAYS,
    MEDIA_MGMT_DOMAIN,
    MEDIA_MGMT_GRANT,
    MEMBER_COLORS,
    SIGNAL_CHANGED,
    STORAGE_KEY,
    STORAGE_VERSION,
    TV_MGMT_DOMAIN,
    TV_MGMT_GRANT,
)
from .countdowns import Countdowns
from .dinner_vote import DinnerVote
from .done_when import DoneWhen
from .give import MAX_GIVE_PERCENT, Give, clean_goal as clean_give_goal
from .goals import FamilyGoals
from .kid_board import KidBoard
from .leave import clean_leave_times, leave_at
from .ledger import Ledger
from .live_activity import ChoreActivity
from .moods import Moods
from .parent_pass import ParentPasses
from .parents_notify import ParentNotices
from .pets import Pets
from .photos import Photos
from .picks import Picks
from .quests import Quests
from .reminders import ChoreReminders
from .reward_requests import RewardRequests
from .routines import Routines
from .statement import month_bounds, statement
from .todo_sync import TodoSync
from .trades import Trades
from .voice import Voice

_LOGGER = logging.getLogger(__name__)
# Seconds to wait before writing the Store, so a burst of changes (checking
# several chores, a chore with its bonuses) is one write. The whole family,
# history included, is one file; Home Assistant writes anything still waiting
# when it stops (2.16.0: 10 instead of 2, fewer writes on SD cards).
SAVE_DELAY = 10
# Seconds one family/state answer is shared by the screens that ask for the
# same thing (same login, admin and parent view) after the same change.
SNAPSHOT_SHARE_SECONDS = 1.0
TODO_PREFIX = "todo:"
HISTORY_PAGE = 200  # history entries sent at a time
BALANCE_DAYS = 28  # days in the points-over-time chart


class FamilyError(HomeAssistantError):
    """Something the person asked for can't be done; the message says why."""


class FamilyStore(Store[dict[str, Any]]):
    """The family's store.

    Version 2 records who each reward is for. Rewards from version 1 have no
    ``members`` key and were for everyone, so the migration writes None.
    An empty list is never written here: that means nobody can get the
    reward, which only happens later, when the last person it was for is
    removed or a parent clears the list. A list that already names every
    current member is not rewritten on load. Saving the reward with all of
    them selected stores None, so people added later are included.
    """

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Bring stored data up to the current version."""
        data = dict(old_data or {})
        if old_major_version < 2:
            data["rewards"] = [
                model.normalize_reward(dict(reward))
                for reward in data.get("rewards") or []
                if isinstance(reward, dict)
            ]
        return data


def _id() -> str:
    return uuid4().hex[:12]


def _set(entry: dict[str, Any], key: str, value: Any) -> None:
    """Set a field, or drop it when there's nothing to say."""
    if value:
        entry[key] = value
    else:
        entry.pop(key, None)


def _bank(raw: dict[str, Any]) -> dict[str, Any]:
    tv = raw.get("bank_tv") or None
    most = int(raw.get("bank_max") or 120)
    if not 15 <= most <= 600:
        raise FamilyError("A screen-time bank holds 15 to 600 minutes")
    return {"bank_tv": tv, "bank_max": most if tv else 120}


def _unlock(raw: dict[str, Any]) -> dict[str, Any]:
    tv = raw.get("unlock_tv") or None
    minutes = model.clean_points(raw.get("unlock_minutes") or 0, "Minutes")
    if tv and not minutes:
        raise FamilyError("Say how many minutes finishing their chores unlocks")
    return {
        "unlock_tv": tv if minutes else None,
        "unlock_minutes": min(minutes, 480) if tv else 0,
        "unlock_whole_home": bool(raw.get("unlock_whole_home")) and bool(tv),
    }


def _done_when(raw: Any) -> dict[str, str] | None:
    """A chore's device and the state that means it's done, or None."""
    if not isinstance(raw, dict) or not raw.get("entity_id"):
        return None
    entity_id = str(raw["entity_id"])
    state = str(raw.get("state") or "").strip()
    if "." not in entity_id:
        raise FamilyError("Pick the device that finishes the chore")
    if not state:
        raise FamilyError("Pick what the device shows when it's done")
    return {"entity_id": entity_id, "state": state[:60]}


KIND_FREEZE = "freeze"  # points spent so a sick day doesn't break a streak
FREEZE_EVERY_DAYS = 7  # at most one streak freeze a week
MAX_WISHES = 3
MAX_GIFT_IDEAS = 10

# What a chore's "when it's done, also start" can be, and how it's started.
ON_DONE_SERVICES = {
    "script": "turn_on",
    "scene": "turn_on",
    "button": "press",
    "input_button": "press",
}


def _only_when(raw: Any) -> dict[str, Any] | None:
    """A chore's "only when this shows": {entity_id, states}, or None."""
    if not isinstance(raw, dict) or not raw.get("entity_id"):
        return None
    entity_id = str(raw["entity_id"])
    states = raw.get("states")
    if isinstance(states, str):
        states = states.split(",")
    states = [str(s).strip()[:60] for s in states or [] if str(s).strip()]
    if "." not in entity_id:
        raise FamilyError("Pick what the chore waits for")
    if not states:
        raise FamilyError("Say what it shows when the chore is on")
    return {"entity_id": entity_id, "states": states[:10]}


def _on_done(raw: Any) -> str | None:
    entity_id = str(raw or "").strip()
    if not entity_id:
        return None
    if entity_id.split(".", 1)[0] not in ON_DONE_SERVICES:
        raise FamilyError("Pick a script, scene or button to start")
    return entity_id


def _now_iso() -> str:
    return dt_util.now().isoformat()


class FamilyManager:
    """Owns the family's data and everything that changes it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = FamilyStore(hass, STORAGE_VERSION, STORAGE_KEY)
        self.members: list[dict[str, Any]] = []
        self.chores: list[dict[str, Any]] = []
        self.rewards: list[dict[str, Any]] = []
        self.todo_lists: list[dict[str, Any]] = []
        # Entities shown on the Family dashboard to control or watch.
        self.controls: list[dict[str, Any]] = []
        # Family-wide settings from the Parents dashboard.
        self.settings: dict[str, Any] = {}
        self.entries: list[dict[str, Any]] = []
        # The ledger grouped by chore, member, day and kind (``ledger``).
        self._ledger = Ledger()
        # What the last badge check saw, so an unchanged ledger isn't rechecked.
        self._badges_seen: tuple[Any, ...] | None = None
        # One "changed" for everything done in the same moment.
        self._notify_pending = False
        # The parents' history numbers, kept until the history changes
        # (_cached): every open screen asks for them after every change.
        self._memo: dict[str, tuple[tuple[Any, ...], Any]] = {}
        # Points from entries older than KEEP_HISTORY_DAYS, per member.
        self.carried: dict[str, int] = {}
        # Open items of each chore to-do list: entity id -> items.
        self.todo_items: dict[str, list[dict[str, Any]]] = {}
        self._unsub_todo: Callable[[], None] | None = None
        # Dashboard chores Family keeps on a to-do list: chore id -> link.
        self.todo_links: dict[str, dict[str, Any]] = {}
        self.todo_sync = TodoSync(self)
        self.notices = ParentNotices(self)
        # Meals for each day (ISO date -> meal -> text), and notes on the board.
        self.meals: dict[str, dict[str, str]] = {}
        self.notes: list[dict[str, Any]] = []
        self.calendar = CalendarToday(self)
        self.reminders = ChoreReminders(self)
        self.routines = Routines(self)
        self.live = ChoreActivity(self)
        self.passes = ParentPasses(self)
        self.trades = Trades(self)
        self.countdowns = Countdowns(self)
        self.kids = KidBoard(self)
        self.requests = RewardRequests(self)
        self.vote = DinnerVote(self)
        self.away = Away(self)
        self.boosts = Boosts(self)
        self.photos = Photos(self)
        self.picks = Picks(self)
        self.done_when = DoneWhen(self)
        self.bingo = Bingo(self)
        self.give = Give(self)
        self.chore_ideas = ChoreIdeas(self)
        self.challenges = Challenges(self)
        self.goals = FamilyGoals(self)
        # Members whose person is a Home Assistant admin (async_refresh_parents).
        self.parent_ids: set[str] = set()
        self.auctions = Auctions(self)
        self.bank = ScreenBank(self)
        self.moods = Moods(self)
        self.quests = Quests(self)
        self.pets = Pets(self)
        self.new_badges: list[dict[str, Any]] = []
        self.voice = Voice(self)
        self._seen_chores: tuple | None = None
        self._member_listeners: list[Callable[[], None]] = []
        # Goes up with every change told to the dashboards (``_notify``). The
        # snapshot carries it and so does the "changed" push, so a screen
        # that already has this revision doesn't load it again.
        self.revision = 0
        # Goes up whenever the family's data changes (``_changed``, ``save``):
        # with the ledger's version, the key of the per-member caches below.
        self._data_version = 0
        # Each member's streak: (member, done_today) -> (key, days).
        self._streaks: dict[tuple[str, bool], tuple[tuple[Any, ...], int]] = {}
        # family/state answers shared for a moment: (who, view) -> (key, at, answer).
        self._snapshots: dict[tuple[Any, ...], tuple[tuple[Any, ...], float, Any]] = {}
        # To-do lists Family is ticking or unticking an item on right now. The
        # state change that causes is skipped: Family reads the list once
        # its update is done (``_async_set_todo``), which also picks up
        # anything else that changed on it meanwhile.
        self._todo_writing: dict[str, int] = {}

    # ---- storage --------------------------------------------------------------

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.members = list(data.get("members") or [])
        self.chores = list(data.get("chores") or [])
        # Version 2 always stores ``members``. A file that is already version
        # 2 but missing the key (hand-edited, or saved by something older)
        # is filled in the same way as the migration: missing means everyone,
        # and an empty list stays empty.
        raw_rewards = [r for r in data.get("rewards") or [] if isinstance(r, dict)]
        self.rewards = [model.normalize_reward(dict(r)) for r in raw_rewards]
        if self.rewards != raw_rewards:
            self.save()
        self.todo_lists = list(data.get("todo_lists") or [])
        self.controls = list(data.get("controls") or [])
        self.settings = dict(data.get("settings") or {})
        self.todo_links = dict(data.get("todo_links") or {})
        self.entries = list(data.get("entries") or [])
        self.carried = {k: int(v) for k, v in (data.get("carried") or {}).items()}
        self.meals = {
            k: dict(v)
            for k, v in (data.get("meals") or {}).items()
            if isinstance(v, dict)
        }
        self.notes = [n for n in data.get("notes") or [] if isinstance(n, dict)]
        self.routines.load(data)
        self.trades.load(data)
        self.countdowns.load(data)
        self.requests.load(data)
        self.vote.load(data)
        self.picks.load(data)
        self.done_when.load(data)
        self.chore_ideas.load(data)
        self.challenges.load(data)
        self.goals.load()
        await self.async_refresh_parents()
        self.auctions.load(data)
        self.bank.load(data)
        self.moods.load(data)
        self.quests.load(data)
        self.pets.load(data)
        # Streaks count days with all of one's own chores done from this day;
        # before it, any chore, as they used to.
        if "streak_rule_from" not in self.settings:
            self.settings["streak_rule_from"] = dt_util.now().date().isoformat()
            self.save()
        self._prune()
        self._prune_board()
        # Badges the history already earns, without telling anyone: an
        # update shouldn't throw a party for last month's chores.
        self._check_badges(quiet=True)
        self.async_auto_check()
        self._watch_todo_lists()
        self.calendar.watch()
        self.done_when.watch()
        self.kids.watch_weather()
        self.async_allowance()
        # To-do lists, calendars and Assist talk to other integrations, which
        # may still be starting: read them once Home Assistant has started
        # (straight away when it already has), so they don't hold up setup.
        self.entry.async_on_unload(async_at_started(self.hass, self._async_after_start))

    async def _async_after_start(self, _hass: HomeAssistant | None = None) -> None:
        """The reads that need other integrations, after Home Assistant started."""
        await self.async_refresh_todo()
        await self.calendar.async_refresh()
        await self.voice.async_start()
        self._notify()

    def _data(self) -> dict[str, Any]:
        return {
            "members": self.members,
            "chores": self.chores,
            "rewards": self.rewards,
            "todo_lists": self.todo_lists,
            "controls": self.controls,
            "settings": self.settings,
            "todo_links": self.todo_links,
            "entries": self.entries,
            "carried": self.carried,
            "meals": self.meals,
            "notes": self.notes,
            **self.routines.data(),
            **self.trades.data(),
            **self.countdowns.data(),
            **self.requests.data(),
            **self.vote.data(),
            **self.picks.data(),
            **self.done_when.data(),
            **self.chore_ideas.data(),
            **self.challenges.data(),
            **self.auctions.data(),
            **self.bank.data(),
            **self.moods.data(),
            **self.quests.data(),
            **self.pets.data(),
        }

    @callback
    def _changed(self, members: bool = False) -> None:
        self._data_version += 1
        self.goals.check()
        self._check_badges()
        self._store.async_delay_save(self._data, SAVE_DELAY)
        self._notify()
        # A chore done, back, renamed or removed: its to-do item follows.
        self.todo_sync.schedule()
        self.live.schedule()
        if members:
            for listener in list(self._member_listeners):
                listener()

    def _history_key(self) -> tuple[Any, ...]:
        """Everything the history numbers depend on: the ledger's entries,
        which were marked as didn't happen, every entry's points (a team
        chore fills its points in when everyone's done), the day, the people
        and the points carried from old history."""
        rejected = 0
        points = 0
        for entry in self.entries:
            points += int(entry.get("points", 0) or 0)
            if entry.get("review") == model.REVIEW_REJECTED:
                rejected += 1
        return (
            self.ledger.version,
            rejected,
            points,
            dt_util.now().date(),
            tuple(m["id"] for m in self.members),
            tuple(sorted(self.carried.items())),
        )

    def _cached(
        self,
        name: str,
        build: Callable[[], Any],
        key: tuple[Any, ...] | None = None,
    ) -> Any:
        """``build()``, or what it gave last time if the history is the same.
        Callers must not change what comes back (it's shared). ``key``: the
        ``_history_key()`` already worked out by the caller (the snapshot
        asks for several numbers and works it out once)."""
        if key is None:
            key = self._history_key()
        hit = self._memo.get(name)
        if hit is not None and hit[0] == key:
            return hit[1]
        value = build()
        self._memo[name] = (key, value)
        return value

    @property
    def ledger(self) -> Ledger:
        """The ledger grouped by chore, member, day and kind (see ledger.py)."""
        return self._ledger.current(self.entries)

    @callback
    def _notify(self) -> None:
        """Tell the dashboards and sensors once, however many changes the
        same moment made (checking them all, a bonus with its chore).

        The revision goes up straight away, so a snapshot read after this
        change (the tap's own reload) already carries the revision the push
        will say, and that screen doesn't load it a second time.
        """
        self.revision += 1
        self._snapshots.clear()
        if self._notify_pending:
            return
        self._notify_pending = True
        self.hass.loop.call_soon(self._send_changed)

    @callback
    def _send_changed(self) -> None:
        self._notify_pending = False
        async_dispatcher_send(self.hass, SIGNAL_CHANGED)

    @callback
    def changed(self) -> None:
        """Save and tell the dashboards (for the family tools in other modules)."""
        self._changed()

    @callback
    def changed_view(self) -> None:
        """Tell the dashboards and sensors that something they show changed
        (today's calendar, for example) without saving anything. Folded into
        one update with anything else that changed in the same moment."""
        self._notify()

    def known_members(self, raw: Any) -> list[str]:
        return self._known_members(raw)

    def own_today(self, member_id: str) -> tuple[int, int]:
        return self._own_today(member_id)

    async def is_parent(self, member: dict[str, Any]) -> bool:
        return await self._is_parent(member)

    async def async_refresh_parents(self) -> None:
        """Who the parents are (admins), kept for kids-only goals."""
        found = {m["id"] for m in self.members if await self._is_parent(m)}
        if found != self.parent_ids:
            self.parent_ids = found
            self._notify()

    def kid_ids(self) -> list[str]:
        """Everyone in the family who isn't a parent."""
        return [m["id"] for m in self.members if m["id"] not in self.parent_ids]

    @callback
    def save(self) -> None:
        """Save without telling the dashboards (nothing they show changed)."""
        self._data_version += 1
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def chore_open(self, chore: dict[str, Any]) -> bool:
        """Whether anyone can still do this dashboard chore today.

        A chore picked for other days isn't open; its hours don't matter here,
        so its to-do item stays put all day.
        """
        now = dt_util.now()
        if not model.on_day(chore, now.date()):
            return False
        chore = self._effective(chore, now)
        done = self._done(chore, now)
        known = {m["id"] for m in self.members}
        members = [m for m in chore.get("members") or [] if m in known]
        if not members:
            return "*" not in done
        return any(m not in done for m in members)

    def still_to_do(self, chore: dict[str, Any], now) -> list[str] | None:
        """Who still has a dashboard chore to do today, whatever its hours.

        None when it's done (or not one of its days); an empty list when
        anyone can do it and nobody has yet.
        """
        if (
            not chore.get("enabled", True)
            or not model.on_day(chore, now.date())
            or self.away.on(now.date())
        ):
            return None
        chore = self._effective(chore, now)
        done = self._done(chore, now)
        can = [m["id"] for m in self.members if model.can_do(m["id"], chore, done)]
        if not can:
            return None
        return can if chore.get("members") else []

    # ---- family goal ----------------------------------------------------------

    def family_goal(self) -> dict[str, Any] | None:
        """The first family goal (closest to done), or None; see goals.py."""
        return self.goals.first()

    def _check_badges(self, quiet: bool = False) -> None:
        """Badges just earned: kept on the member, with an event, and told
        to the dashboard in ``new_badges`` (for the screen that earned them)."""
        today = dt_util.now().date().isoformat()
        ledger = self.ledger
        # Badges come from the ledger and the streak; with the same ledger,
        # reviews, people and day there's nothing new to find.
        seen = (
            ledger.version,
            today,
            tuple(m["id"] for m in self.members),
            sum(1 for e in self.entries if e.get("review") == model.REVIEW_REJECTED),
            self.settings.get("streak_rule_from"),
        )
        if seen == self._badges_seen:
            return
        self._badges_seen = seen
        for member in self.members:
            stored = member.setdefault("badges", {})
            earned = model.badges_earned(
                ledger.member(member["id"]), member["id"], self.streak(member["id"])
            )
            for key in [k for k, *_rest in model.BADGES if k in earned - set(stored)]:
                stored[key] = today
                if quiet:
                    continue
                emoji, name, _text = model.BADGE_INFO[key]
                self.new_badges.append(
                    {"member": member["id"], "key": key, "emoji": emoji, "name": name}
                )
                self.hass.bus.async_fire(
                    EVENT_BADGE_EARNED,
                    {
                        "member_id": member["id"],
                        "member": member["name"],
                        "badge": key,
                        "name": name,
                    },
                )

    def take_new_badges(self, member_id: str | None = None) -> list[dict[str, Any]]:
        """Badges earned since last asked (for one member, or all)."""
        taken = [b for b in self.new_badges if member_id in (None, b["member"])]
        self.new_badges = [b for b in self.new_badges if b not in taken]
        return taken

    @callback
    def async_tick(self, _now: Any = None) -> None:
        """Every minute: tell the dashboards when a chore's hours start or end,
        or a new day or week brings someone else's turn. Says chore reminders
        whose time it is."""
        now = dt_util.now()
        if self.reminders.wanted and not self.away.on(now.date()):
            self.reminders.check(now)
        self.live.tick(now)
        self.vote.tick(now)
        self.auctions.tick(now)
        self.bank.tick(now)
        if (
            not any(
                c.get("days")
                or c.get("from_time")
                or c.get("until_time")
                or c.get("turns")
                or c.get("from_date")
                for c in self.chores
            )
            and not any(t.get("due_only") for t in self.todo_lists)
            and not self.away.periods
            and not self.boosts.items
        ):
            return
        seen = tuple(
            (c["id"], c.get("turn"), c.get("boost")) for c in self.chores_for(None)
        )
        if seen != self._seen_chores:
            self._seen_chores = seen
            self._notify()
            self.todo_sync.schedule()
            self.live.schedule()

    def linked_uids(self, entity_id: str) -> set[str]:
        """Items Family put on this list for its own chores."""
        return {
            link["uid"]
            for link in self.todo_links.values()
            if link["list"] == entity_id
        }

    @callback
    def add_member_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._member_listeners.append(listener)
        return lambda: self._member_listeners.remove(listener)

    async def async_unload(self) -> None:
        self.voice.stop()
        self.calendar.stop()
        self.kids.stop_weather()
        self.live.stop()
        self.done_when.stop()
        if self._unsub_todo:
            self._unsub_todo()
            self._unsub_todo = None
        await self._store.async_save(self._data())

    def _prune(self) -> bool:
        """Fold entries older than KEEP_HISTORY_DAYS into the balances.

        Done when loading and every hour (``async_allowance``), so history
        doesn't keep growing while Home Assistant runs for months. The list
        is replaced (and the ledger regrouped) only when some go. True when
        some were folded in.
        """
        cutoff = dt_util.now() - timedelta(days=KEEP_HISTORY_DAYS)
        old = [
            entry
            for entry in self.entries
            if (at := dt_util.parse_datetime(entry["at"])) is not None and at < cutoff
        ]
        if not old:
            return False
        gone = {id(entry) for entry in old}
        for entry in old:
            if entry.get("review") != model.REVIEW_REJECTED:
                member = entry["member"]
                self.carried[member] = self.carried.get(member, 0) + int(
                    entry.get("points", 0)
                )
        self.entries = [entry for entry in self.entries if id(entry) not in gone]
        return True

    def _prune_board(self) -> bool:
        """Drop notes past their last day, and meals older than a week."""
        today = dt_util.now().date()
        oldest = (today - timedelta(days=model.KEEP_MEAL_DAYS)).isoformat()
        notes = [n for n in self.notes if model.note_current(n, today)]
        meals = {d: m for d, m in self.meals.items() if d >= oldest and m}
        changed = len(notes) != len(self.notes) or len(meals) != len(self.meals)
        self.notes, self.meals = notes, meals
        now = dt_util.now()
        for pruned in (
            self.countdowns.prune(today),
            self.requests.prune(now),
            self.away.prune(today),
            self.boosts.prune(now),
            self.chore_ideas.prune(now),
            self.challenges.prune(today),
            self.moods.prune(today),
        ):
            changed = changed or pruned
        return changed

    # ---- allowance ------------------------------------------------------------

    @callback
    def async_allowance(self, _now: Any = None) -> None:
        """Give each member their weekly allowance, once a week (hourly check)."""
        self.hass.async_create_background_task(
            self.photos.async_prune(), "family photo prune"
        )
        changed = self._prune_board()
        # History older than a year and a bit goes into the balances.
        if self._prune():
            changed = True
        self.hass.async_create_background_task(
            self.async_refresh_parents(), "family parents"
        )
        now = dt_util.now()
        if savings.give_birthday_bonus(self, now):
            changed = True
        if savings.give_saving_bonus(self, now):
            changed = True
        if changed:
            self._changed()
        if not any(int(m.get("allowance") or 0) for m in self.members):
            return
        key = model.allowance_due(
            now,
            int(self.settings.get("allowance_day", model.DEFAULT_ALLOWANCE_DAY)),
            int(self.settings.get("allowance_hour", model.DEFAULT_ALLOWANCE_HOUR)),
            self.settings.get("allowance_week"),
        )
        if key is None:
            return
        # Away: no allowance this week (it isn't made up later).
        away = self.away.on(now.date())
        rule = self.settings.get("allowance_rule") or allowance_rule.DEFAULT_RULE
        for member in [] if away else self.members:
            points = int(member.get("allowance") or 0)
            if points <= 0:
                continue
            share = allowance_rule.last_week_share(
                model.all_done_days(self.ledger.member(member["id"]), member["id"]),
                self._has_own(member["id"]),
                now.date(),
            )
            points, why = allowance_rule.adjusted(points, share, rule)
            allowance = {
                "id": _id(),
                "at": now.isoformat(),
                "kind": model.KIND_ALLOWANCE,
                "member": member["id"],
                "title": f"Weekly allowance ({why})" if why else "Weekly allowance",
                "points": points,
            }
            if why:
                allowance["base_points"] = int(member.get("allowance") or 0)
            self.entries.append(allowance)
            # The give jar's share of it, if a parent set one.
            if gift := self.give.from_allowance(member["id"], points):
                self.entries.append(gift)
        self.settings["allowance_week"] = key
        self._changed()

    # ---- meals and notes ------------------------------------------------------

    @callback
    def save_meals(self, day: str, raw: dict[str, Any]) -> dict[str, str]:
        """A day's meals from the Parents dashboard (empty ones are cleared)."""
        day = model.clean_day(day) or ""
        if not day:
            raise FamilyError("Pick the day")
        meals = model.clean_meals(raw)
        if meals:
            self.meals[day] = meals
        else:
            self.meals.pop(day, None)
        self._changed()
        return meals

    @callback
    def add_note(
        self,
        text: str,
        member_id: str | None,
        until: str | None,
        *,
        by_admin: bool,
        by: str | None = None,
    ) -> dict[str, Any]:
        """Put a note on the board. Anyone can, from the shared screen too."""
        if member_id:
            self.member(member_id)
        today = dt_util.now().date().isoformat()
        until = model.clean_day(until, "Show it until")
        if until and until < today:
            raise FamilyError("Show it until today or a later day")
        current = [n for n in self.notes if model.note_current(n, dt_util.now().date())]
        if len(current) >= model.MAX_NOTES:
            raise FamilyError("The board is full. Take a note down first.")
        note = {
            "id": _id(),
            "text": model.clean_note(text),
            "member": member_id or None,
            "until": until,
            "at": _now_iso(),
            # A parent's note can only be taken down by a parent.
            "parent": by_admin,
            "by": by,
        }
        self.notes.append(note)
        self._changed()
        return note

    @callback
    def remove_note(self, note_id: str, *, by_admin: bool) -> None:
        note = next((n for n in self.notes if n["id"] == note_id), None)
        if note is None:
            raise FamilyError("That note is already gone")
        if note.get("parent") and not by_admin:
            raise FamilyError("Only a parent can take down a parent's note")
        self.notes.remove(note)
        self._changed()

    # ---- lookups --------------------------------------------------------------

    def member(self, member_id: str) -> dict[str, Any]:
        for member in self.members:
            if member["id"] == member_id:
                return member
        raise FamilyError("That family member isn't set up")

    def points(self, member_id: str) -> int:
        return self.carried.get(member_id, 0) + model.balance(
            self.ledger.member(member_id), member_id
        )

    def member_for_user(self, user_id: str | None) -> str | None:
        """The member a Home Assistant login belongs to, through their person."""
        if not user_id:
            return None
        for member in self.members:
            person = member.get("person")
            state = self.hass.states.get(person) if person else None
            if state is not None and state.attributes.get("user_id") == user_id:
                return member["id"]
        return None

    def picture(self, member: dict[str, Any]) -> str | None:
        person = member.get("person")
        state = self.hass.states.get(person) if person else None
        return state.attributes.get("entity_picture") if state else None

    # ---- chores ---------------------------------------------------------------

    def all_chores(self) -> list[dict[str, Any]]:
        """Dashboard chores and the open items of every chore to-do list."""
        now = dt_util.now()
        chores = [
            self._effective(model.for_ages(c, self.members, now.date()), now)
            for c in self.chores
            # Kept on a to-do list and set to show only when due: its item's
            # due date decides (no date, or not linked yet: it shows).
            if not c.get("due_only")
            or model.todo_due(
                _local_due((self.todo_links.get(c["id"]) or {}).get("due")), now
            )
        ]
        # A dashboard chore kept on a to-do list shows that list, like a
        # to-do chore does.
        for chore in chores:
            if chore.get("todo_list"):
                state = self.hass.states.get(chore["todo_list"])
                chore["on_list"] = state.name if state else chore["todo_list"]
        # One tile per chore: a to-do item named like a dashboard chore, or
        # like an item already listed, isn't shown again. Dashboard chores
        # come first, then to-do items.
        seen = {
            model.item_key(c.get("name", ""))
            for c in self.chores
            if c.get("enabled", True)
        }
        for todo in self.todo_lists:
            entity_id = todo["entity_id"]
            state = self.hass.states.get(entity_id)
            list_name = state.name if state else entity_id
            mine = self.linked_uids(entity_id)
            for item in self.todo_items.get(entity_id, []):
                # Only due (today, by its time) or overdue items, when set.
                if todo.get("due_only") and not model.todo_due(
                    _local_due(item.get("due")), now
                ):
                    continue
                if item.get("uid") in mine:
                    continue  # a dashboard chore Family keeps on this list
                name, points, _rated = model.todo_item_points(
                    item.get("summary", ""),
                    int(todo.get("points", 0)),
                    todo.get("item_points"),
                )
                if model.item_key(name) in seen:
                    continue
                if model.item_key(name) in (todo.get("item_skip") or []):
                    continue  # left out of the chores by a parent
                seen.add(model.item_key(name))
                chores.append(
                    {
                        "id": f"{TODO_PREFIX}{entity_id}:{item['uid']}",
                        "name": name,
                        "points": points,
                        "members": _item_members(todo, name),
                        "emoji": (todo.get("item_emojis") or {}).get(
                            model.item_key(name)
                        ),
                        "grab": model.is_grab(
                            {**todo, "members": _item_members(todo, name)}
                        ),
                        # A to-do item is done once; the list decides if it comes back.
                        "repeat": model.REPEAT_ONCE,
                        "enabled": True,
                        "source": "todo",
                        "list": list_name,
                        "todo_entity": entity_id,
                        "todo_uid": item["uid"],
                        "penalty": todo.get("penalty"),
                    }
                )
        return chores

    def _effective(self, chore: dict[str, Any], now) -> dict[str, Any]:
        """A dashboard chore as it is now: one taken in turns is only for
        whoever's turn it is (``turn``), and keeps its people as ``rotation``."""
        turn = model.turn_member(chore, self.entries, now)
        if turn is None:
            chore = dict(chore, source="family", grab=model.is_grab(chore))
        else:
            chore = dict(
                chore,
                source="family",
                grab=False,
                rotation=list(chore.get("members") or []),
                members=[turn],
                turn=turn,
            )
        # In the pick-your-chores pool: whoever picked it this week does it.
        chore = self.picks.apply(chore)
        # Traded today, with a parent's yes: whoever took it does it.
        chore = chore if chore["grab"] else self.trades.apply(chore)
        if chore.get("repeat") == model.REPEAT_ON_DEMAND:
            # Out only while a parent has put it out and it isn't done.
            since = model.done_since(chore, now)
            chore = dict(
                chore,
                showing=since is not None
                and model.demand_showing(
                    chore, self.ledger.chore_since(chore["id"], since), now
                ),
            )
        return chore

    def chore(self, chore_id: str) -> dict[str, Any]:
        for chore in self.all_chores():
            if chore["id"] == chore_id:
                return chore
        raise FamilyError("That chore isn't on the list any more")

    def chores_for(self, member_id: str | None) -> list[dict[str, Any]]:
        """Chores with who can still do each now."""
        now = dt_util.now()
        if self.away.on(now.date()):
            return []  # away: nothing to do
        result = []
        for chore in self.all_chores():
            if (
                not chore.get("enabled", True)
                or chore.get("unpicked")
                or not model.available(chore, now)
                or not self.only_when_ok(chore)
            ):
                continue
            done = self._done(chore, now)
            can = [m["id"] for m in self.members if model.can_do(m["id"], chore, done)]
            if member_id is not None and member_id not in can:
                continue
            if not can:
                continue
            row = {**chore, "can": can}
            if chore.get("team"):
                row["team_done"] = [m for m in chore.get("members") or [] if m in done]
            # Double points: shown as what it's worth now.
            if (factor := self.boosts.factor(chore["id"], now)) > 1:
                row.update(
                    boost=factor,
                    base_points=int(chore.get("points", 0)),
                    points=int(chore.get("points", 0)) * factor,
                )
            result.append(row)
        return result

    def _done(self, chore: dict[str, Any], now) -> set[str]:
        """Who has done it. A to-do item is open until it's done, so the list
        alone decides; a recurring reminder that comes back can be done again."""
        if chore.get("source") == "todo":
            return set()
        # Only completions since the period began can count: read just those.
        recent = self.ledger.chore_since(chore["id"], model.done_since(chore, now))
        return model.done_by(chore, recent, now)

    async def async_complete(
        self,
        member_id: str,
        chore_id: str,
        timer_started: str | None = None,
        photo: str | None = None,
        helpers: list[str] | None = None,
    ) -> dict[str, Any]:
        """A member did a chore: points straight away, a parent checks later.

        ``photo``: a JPEG data URL, for chores that ask for one. ``helpers``:
        others who did it with them; the points are split between them."""
        member = self.member(member_id)
        helping = [
            self.member(h) for h in dict.fromkeys(helpers or []) if h != member_id
        ]
        chore = self.chore(chore_id)
        now = dt_util.now()
        if chore.get("team") and helping:
            raise FamilyError(f"{chore['name']} is a team chore: each one ticks it")
        if chore.get("unpicked"):
            raise FamilyError(f"Nobody picked {chore['name']} this week yet")
        picture = self.photos.decode(photo) if photo else None
        if picture is None and chore.get("photo") == "need":
            raise FamilyError(f"Take a photo to show {chore['name']} is done")
        if self.away.on(now.date()):
            raise FamilyError("Chores are off while the family is away")
        if not model.available(chore, now) or not self.only_when_ok(chore):
            raise FamilyError(f"{chore['name']} isn't for right now")
        done = self._done(chore, now)
        if not model.can_do(member_id, chore, done):
            raise FamilyError(
                f"{chore['name']} is already done or isn't {member['name']}'s"
            )
        factor = self.boosts.factor(chore_id, now)
        total = model.age_points(
            int(chore.get("points", 0)) * factor,
            model.age_on(member, now.date()),
            self.settings.get("age_points"),
        )
        shares = model.split_evenly(total, [member_id, *(h["id"] for h in helping)])
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": model.KIND_CHORE,
            "member": member_id,
            "title": chore["name"],
            "points": shares[member_id],
            "chore_id": chore_id,
            "review": model.REVIEW_PENDING,
            # The chore's own penalty if it has one; None: the family's.
            "penalty": chore.get("penalty"),
        }
        if factor > 1:
            entry["boost"] = factor
        if chore.get("team"):
            # The points wait until everyone on the team has ticked it.
            entry["team_points"] = entry["points"]
            entry["points"] = 0
            entry["team_wait"] = True
        if picture is not None:
            await self.photos.async_save(entry["id"], picture)
            entry["photo"] = True
        parent = await self._is_parent(member)
        if parent:
            # A parent's own chore: nobody needs to check it.
            entry["review"] = model.REVIEW_APPROVED
            entry["reviewed_at"] = entry["at"]
            entry["parent"] = True
        self.entries.append(entry)
        if helping:
            entry["together"] = [member_id, *(h["id"] for h in helping)]
        helper_bonus = int(self.settings.get("helper_bonus") or 0) if helping else 0
        for helper in helping:
            if helper_bonus:
                # Extra for helping a brother or sister finish.
                self.entries.append(
                    {
                        "id": _id(),
                        "at": entry["at"],
                        "kind": model.KIND_BONUS,
                        "bonus": model.BONUS_HELPER,
                        "member": helper["id"],
                        "title": f"Helped {member['name']} with {chore['name']}",
                        "points": helper_bonus,
                        "for_entry": entry["id"],
                    }
                )
            # Their share: checked like any chore, undone with it, and not
            # counted as their own chore done (it was the other one's).
            self.entries.append(
                {
                    "id": _id(),
                    "at": entry["at"],
                    "kind": model.KIND_CHORE,
                    "member": helper["id"],
                    "title": f"{chore['name']} (with {member['name']})",
                    "points": shares[helper["id"]],
                    "chore_id": f"helped:{chore_id}",
                    "review": model.REVIEW_PENDING,
                    "penalty": chore.get("penalty"),
                    "for_entry": entry["id"],
                }
            )
        if chore.get("source") == "todo":
            await self._async_set_todo(chore["todo_entity"], chore["todo_uid"], True)
        waiting: list[str] = []
        if chore.get("team") and not team.settle(self.entries, chore, now):
            waiting = [
                self._member_name(m)
                for m in team.still_to_tick(self.entries, chore, now)
            ]
        bonuses = self._earn_bonuses(member, entry)
        if model.beat_timer(chore, timer_started, now):
            timer = {
                "bonus": model.BONUS_TIMER,
                "title": "Beat the timer",
                "points": int(chore.get("timer_bonus") or 0),
            }
            self.entries.append(
                {
                    "id": _id(),
                    "at": _now_iso(),
                    "kind": model.KIND_BONUS,
                    "member": member_id,
                    "for_entry": entry["id"],
                    **timer,
                }
            )
            bonuses.append(timer)
        if streak := self._chore_streak_bonus(chore, entry, now):
            bonuses.append(streak)
        self._changed()
        if chore.get("on_done"):
            self._run_on_done(chore)
        for bonus in bonuses:
            if bonus.get("tv"):
                await self._async_unlock(bonus, member, int(bonus["minutes"]))
        if not parent:
            self.notices.chore_done(entry, member)
        self.hass.bus.async_fire(
            EVENT_CHORE_DONE,
            {
                "member": member["name"],
                "member_id": member_id,
                "chore": chore["name"],
                "points": entry["points"],
                "balance": self.points(member_id),
            },
        )
        for bonus in bonuses:
            self.hass.bus.async_fire(
                EVENT_BONUS,
                {
                    "member": member["name"],
                    "member_id": member_id,
                    "bonus": bonus["bonus"],
                    "title": bonus["title"],
                    "points": bonus["points"],
                    "balance": self.points(member_id),
                },
            )
        if bonuses:
            entry = {**entry, "bonuses": bonuses}
        if waiting:
            # Not stored: the points wait until these have ticked it too.
            entry = {**entry, "team_waiting": waiting}
        return entry

    @callback
    def _shop_for(self, reward: dict[str, Any], who: str) -> None:
        """A reward a parent hands out goes on the shopping list, if one is
        picked (``settings.reward_list``), such as "A new toy for Alex"."""
        todo = self.settings.get("reward_list")
        if not todo or self.hass.states.get(todo) is None:
            return

        async def _add() -> None:
            try:
                await self.hass.services.async_call(
                    "todo",
                    "add_item",
                    {"entity_id": todo, "item": f"{reward['name']} for {who}"},
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001 - the reward still counts
                _LOGGER.warning("Couldn't add %s to the list: %s", reward["name"], err)

        self.hass.async_create_background_task(_add(), "family reward list")

    def only_when_ok(self, chore: dict[str, Any]) -> bool:
        """A chore's "only when": a device (or Daily Routine's Kind of day)
        shows one of the states. Unknown: not now."""
        rule = chore.get("only_when")
        if not rule:
            return True
        state = self.hass.states.get(rule["entity_id"])
        return state is not None and state.state in rule["states"]

    @callback
    def _run_on_done(self, chore: dict[str, Any]) -> None:
        """Start what the chore's done starts: a script, scene or button."""
        entity_id = chore["on_done"]
        domain = entity_id.split(".", 1)[0]
        service = ON_DONE_SERVICES.get(domain)
        if service is None or self.hass.states.get(entity_id) is None:
            return

        async def _run() -> None:
            try:
                await self.hass.services.async_call(
                    domain, service, {"entity_id": entity_id}, blocking=True
                )
            except Exception as err:  # noqa: BLE001 - the chore still counts
                _LOGGER.warning(
                    "%s done: couldn't start %s: %s", chore["name"], entity_id, err
                )

        self.hass.async_create_background_task(_run(), f"family on done {entity_id}")

    @callback
    def offer_chore(self, chore_id: str, offer: bool = True) -> dict[str, Any]:
        """A parent puts a chore that only comes when added out now (Add
        now), or takes it back. Each time it's put out it can be done once:
        by anyone for a chore up for grabs, by each of its people otherwise."""
        chore = next((c for c in self.chores if c["id"] == chore_id), None)
        if chore is None:
            raise FamilyError("That chore isn't on the list any more")
        if chore.get("repeat") != model.REPEAT_ON_DEMAND:
            raise FamilyError(f"{chore['name']} comes back by itself")
        chore["offered"] = _now_iso() if offer else None
        self._changed()
        return chore

    def demand_showing_ids(self) -> list[str]:
        """Chores a parent puts out that are out now (for the Parents list)."""
        now = dt_util.now()
        return [
            c["id"]
            for c in self.chores
            if c.get("repeat") == model.REPEAT_ON_DEMAND
            and self._effective(c, now).get("showing")
        ]

    async def async_set_example(self, chore_id: str, photo: str | None) -> None:
        """A parent's photo of what a chore looks like done (None removes it)."""
        chore = next((c for c in self.chores if c["id"] == chore_id), None)
        if chore is None:
            raise FamilyError("That chore isn't on the list any more")
        key = f"example{chore_id}"
        if photo:
            await self.photos.async_save(key, self.photos.decode(photo), keep=True)
        else:
            await self.photos.async_delete(key, keep=True)
        chore["example"] = bool(photo)
        self._changed()

    async def async_example(self, chore_id: str) -> str | None:
        return await self.photos.async_read(f"example{chore_id}", keep=True)

    async def _async_unlock(
        self, bonus: dict[str, Any], member: dict[str, Any], minutes: int
    ) -> None:
        """Screen time a member's finished chores unlock (or, undone, take back).
        A failure is logged: the chore still counts."""
        try:
            await self._async_grant_tv_time(
                bonus["tv"],
                minutes,
                bool(bonus.get("whole_home")),
                f"{member['name']}'s chores are done",
            )
        except Exception as err:  # noqa: BLE001 - TV Mgmt away or refusing
            _LOGGER.warning("Couldn't unlock %s's screen time: %s", member["name"], err)

    def _chore_streak_bonus(
        self, chore: dict[str, Any], entry: dict[str, Any], now
    ) -> dict[str, Any] | None:
        """Points for doing the same chore so many days (or, for a weekly
        chore, weeks) in a row. Kept with the chore like the other bonuses."""
        every = int(chore.get("streak_days") or 0)
        points = int(chore.get("streak_bonus") or 0)
        if not every or not points:
            return None
        weekly = chore.get("repeat") == model.REPEAT_WEEKLY
        count = model.chore_streak(
            self.entries, entry["member"], chore["id"], now.date(), weekly
        )
        if not model.streak_bonus_due(count, every):
            return None
        unit = "weeks" if weekly else "days"
        bonus = {
            "bonus": model.BONUS_CHORE_STREAK,
            "title": f"{chore['name']}: {count} {unit} in a row",
            "points": points,
        }
        self.entries.append(
            {
                "id": _id(),
                "at": _now_iso(),
                "kind": model.KIND_BONUS,
                "member": entry["member"],
                "for_entry": entry["id"],
                **bonus,
            }
        )
        return bonus

    async def _is_parent(self, member: dict[str, Any]) -> bool:
        """Whether this member's person is a Home Assistant administrator:
        someone who can open the Parents dashboard."""
        person = member.get("person")
        state = self.hass.states.get(person) if person else None
        user_id = state.attributes.get("user_id") if state else None
        if not user_id:
            return False
        user = await self.hass.auth.async_get_user(user_id)
        return bool(user and user.is_admin)

    def _earn_bonuses(
        self, member: dict[str, Any], entry: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Bonus points this chore earned: all of today's chores done, or a
        streak. Kept with the chore, so undoing or rejecting it takes them back."""
        member_id = member["id"]
        today = dt_util.now().date()
        found: list[tuple[str, str, int]] = []
        all_done = int(self.settings.get("bonus_all_done") or 0)
        finished = False
        if not model.bonus_given(self.entries, member_id, model.BONUS_ALL_DONE, today):
            # Only their own chores count (not ones up for grabs), and they
            # need to have some.
            total, left = self._own_today(member_id, entry["chore_id"])
            if total and not left:
                finished = True
                # Even with no points: it marks the day for their streak.
                found.append((model.BONUS_ALL_DONE, "All done today!", all_done))
        every = int(self.settings.get("streak_days") or 0)
        streak_points = int(self.settings.get("streak_bonus") or 0)
        # A streak grows only by finishing a day's own chores.
        if (
            finished
            and every
            and streak_points
            and not model.bonus_given(
                self.entries, member_id, model.BONUS_STREAK, today
            )
        ):
            days = self.streak(member_id, done_today=True)
            if model.streak_bonus_due(days, every):
                found.append(
                    (model.BONUS_STREAK, f"{days} days in a row!", streak_points)
                )
        bonuses = [
            {
                "id": _id(),
                "at": _now_iso(),
                "kind": model.KIND_BONUS,
                "member": member_id,
                "title": title,
                "points": points,
                "bonus": kind,
                "for_entry": entry["id"],
            }
            for kind, title, points in found
        ]
        # Chore bingo: lines and the full card on this week's board.
        for kind, title, points in self.bingo.bonuses(member_id, entry):
            bonuses.append(
                {
                    "id": _id(),
                    "at": _now_iso(),
                    "kind": model.KIND_BONUS,
                    "member": member_id,
                    "title": title,
                    "points": points,
                    "bonus": kind,
                    "for_entry": entry["id"],
                }
            )
        # First to finish their own chores: the races they win.
        if finished:
            for kind, title, points, challenge in self.challenges.wins(
                member_id, today
            ):
                bonuses.append(
                    {
                        "id": _id(),
                        "at": _now_iso(),
                        "kind": model.KIND_BONUS,
                        "member": member_id,
                        "title": title,
                        "points": points,
                        "bonus": kind,
                        "challenge": challenge,
                        "for_entry": entry["id"],
                    }
                )
        # Their own chores done: the screen time they unlock.
        member_tv = member.get("unlock_tv")
        minutes = int(member.get("unlock_minutes") or 0)
        for bonus in bonuses:
            if bonus["bonus"] == model.BONUS_ALL_DONE and member_tv and minutes:
                bonus.update(
                    tv=member_tv,
                    minutes=minutes,
                    whole_home=bool(member.get("unlock_whole_home")),
                    title=f"{bonus['title']} 📺 +{minutes} min",
                )
        self.entries.extend(bonuses)
        return bonuses

    def _own_today(
        self, member_id: str, just_done: str | None = None
    ) -> tuple[int, int]:
        """How many of their own chores today, and how many are left.

        Today's, whatever their hours: a bedtime chore still to do means not
        all done yet. ``just_done``: a chore being done right now.
        """
        now = dt_util.now()
        today = now.date()
        if self.away.on(today):
            return 0, 0
        own = [
            c
            for c in self.all_chores()
            if model.is_own(c, member_id) and model.on_day(c, today)
        ]
        return len(own), len(self._own_left(member_id, own, now, just_done))

    def _own_left(
        self,
        member_id: str,
        own: list[dict[str, Any]],
        now: datetime,
        just_done: str | None = None,
    ) -> list[dict[str, Any]]:
        """Their own chores still to do today. One they did today counts as
        done for the day, even one that came back (once a parent checked it,
        or always there)."""
        did = {
            e["chore_id"]
            for e in model.chores_done_on(
                self.ledger.day(now.date()), now.date(), member_id
            )
            if e.get("review") != model.REVIEW_REJECTED
        }
        return [
            c
            for c in own
            if c["id"] != just_done
            and c["id"] not in did
            and model.can_do(member_id, c, self._done(c, now))
        ]

    def _own_status(
        self, member_id: str, chores: list[dict[str, Any]], now: datetime
    ) -> tuple[int, int, int]:
        """Their own chores today: how many, how many are left and how many of
        those are missed (hours over), from one look (``chores``: all_chores)."""
        today = now.date()
        if self.away.on(today):
            return 0, 0, 0
        own = [
            c for c in chores if model.is_own(c, member_id) and model.on_day(c, today)
        ]
        left = self._own_left(member_id, own, now)
        return len(own), len(left), sum(1 for c in left if model.hours_over(c, now))

    def _own_missed(self, member_id: str) -> int:
        """Their own chores left today whose hours are over: missed."""
        now = dt_util.now()
        own = [
            c
            for c in self.all_chores()
            if model.is_own(c, member_id) and model.on_day(c, now.date())
        ]
        return sum(
            1 for c in self._own_left(member_id, own, now) if model.hours_over(c, now)
        )

    def has_own(self, member_id: str) -> Callable[[date], bool]:
        """Public for the family streak (``kid_board``)."""
        return self._has_own(member_id)

    def _has_own(self, member_id: str) -> Callable[[date], bool]:
        """Whether a day had any of this member's own dashboard chores (one
        taken in turns isn't counted: whose turn it was isn't kept)."""

        frozen = self.frozen_days(member_id)

        def has_own(day: date) -> bool:
            if self.away.on(day) or day in frozen:
                return False  # away, or a streak freeze: a day off
            return any(
                model.is_own(c, member_id)
                and not c.get("turns")
                and model.on_day(c, day)
                for c in (model.for_ages(c, self.members, day) for c in self.chores)
            )

        return has_own

    def frozen_days(self, member_id: str) -> set[date]:
        """Days this member froze their streak on (spent points for a sick day)."""
        return {
            date.fromisoformat(e["day"])
            for e in self.ledger.kind(KIND_FREEZE)
            if e.get("kind") == KIND_FREEZE
            and e["member"] == member_id
            and e.get("day")
            and e.get("review") != model.REVIEW_REJECTED
        }

    def freeze_offers(self, member_id: str) -> list[str]:
        """Days a freeze would save their streak: yesterday if it was missed,
        and today while it isn't done. None while freezes are off, or one was
        used in the last week."""
        cost = int(self.settings.get("freeze_cost") or 0)
        if not cost:
            return []
        today = dt_util.now().date()
        frozen = self.frozen_days(member_id)
        if any(today - day < timedelta(days=FREEZE_EVERY_DAYS) for day in frozen):
            return []
        has_own = self._has_own(member_id)
        done = model.all_done_days(self.ledger.member(member_id), member_id)
        return [
            day.isoformat()
            for day in (today - timedelta(days=1), today)
            if has_own(day) and day not in done
        ]

    @callback
    def freeze(self, member_id: str, day: str) -> dict[str, Any]:
        """Spend points so a sick day doesn't break their streak."""
        member = self.member(member_id)
        if day not in self.freeze_offers(member_id):
            raise FamilyError("A streak freeze can't be used for that day")
        cost = int(self.settings.get("freeze_cost") or 0)
        if self.points(member_id) < cost:
            raise FamilyError(f"{member['name']} needs {cost} points for a freeze")
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": KIND_FREEZE,
            "member": member_id,
            "title": "Streak freeze ("
            + f"{date.fromisoformat(day):%a %b} {date.fromisoformat(day).day})",
            "points": -cost,
            "day": day,
        }
        self.entries.append(entry)
        self._changed()
        return entry

    @callback
    def set_wish(self, member_id: str, reward_id: str, on: bool) -> list[str]:
        """Add a reward to someone's wishlist (up to MAX_WISHES), or take it off."""
        member = self.member(member_id)
        reward = self.reward(reward_id)
        wishes = [w for w in member.get("wishes") or [] if w != reward_id]
        if on:
            if not model.reward_for(reward, member_id):
                raise FamilyError(f"{reward['name']} isn't for {member['name']}")
            if len(wishes) >= MAX_WISHES:
                raise FamilyError(f"Up to {MAX_WISHES} wishes: take one off first")
            wishes.append(reward_id)
        member["wishes"] = wishes
        self._changed()
        return wishes

    @callback
    def gift_idea(self, member_id: str, text: Any, add: bool) -> list[str]:
        """Add a gift idea to someone's list (up to MAX_GIFT_IDEAS), or take
        one off. Shared with family as text (``gift_text``)."""
        member = self.member(member_id)
        idea = str(text or "").strip()[:80]
        if not idea:
            raise FamilyError("Write the gift idea")
        ideas = [i for i in member.get("gift_ideas") or [] if i.lower() != idea.lower()]
        if add:
            if len(ideas) >= MAX_GIFT_IDEAS:
                raise FamilyError(
                    f"Up to {MAX_GIFT_IDEAS} gift ideas: take one off first"
                )
            ideas.append(idea)
        member["gift_ideas"] = ideas
        self._changed()
        return ideas

    def month_photos(self, months_ago: int) -> list[dict[str, Any]]:
        """Chores with a photo in a month (0: this one), oldest first."""
        start, end = month_bounds(dt_util.now().date(), months_ago)
        return [
            {
                "entry_id": e["id"],
                "title": e.get("title", ""),
                "member": e["member"],
                "at": e["at"],
            }
            for e in self.entries
            if e.get("photo")
            and e.get("review") != model.REVIEW_REJECTED
            and start <= model.entry_day(e) < end
        ]

    def gift_text(self, member_id: str) -> str:
        """Gift ideas and wishlist for grandparents and friends, as text."""
        member = self.member(member_id)
        names = {r["id"]: r["name"] for r in self.rewards}
        lines = [f"Gift ideas for {member['name']}"]
        if member.get("birthday"):
            month, day = (int(x) for x in member["birthday"].split("-"))
            lines.append(f"Birthday: {date(2000, month, day):%B} {day}")
        ideas = list(member.get("gift_ideas") or [])
        ideas += [names[w] for w in member.get("wishes") or [] if w in names]
        lines += [f"- {i}" for i in ideas] or ["(nothing on the list yet)"]
        return "\n".join(lines)

    def most_wanted(self) -> list[dict[str, Any]]:
        """Rewards on the wishlists, the most wished for first."""
        counts: dict[str, list[str]] = {}
        known = {r["id"] for r in self.rewards}
        for member in self.members:
            for wish in member.get("wishes") or []:
                if wish in known:
                    counts.setdefault(wish, []).append(member["id"])
        return sorted(
            ({"reward_id": rid, "members": who} for rid, who in counts.items()),
            key=lambda w: -len(w["members"]),
        )

    def statement(self, member_id: str, months_ago: int) -> dict[str, Any]:
        member = self.member(member_id)
        start, end = month_bounds(dt_util.now().date(), months_ago)
        result = statement(
            self.entries, member_id, int(self.carried.get(member_id, 0)), start, end
        )
        result["member"] = member["name"]
        result["money"] = (
            {
                "value": self.settings.get("point_value"),
                "currency": self.settings.get("currency") or "",
            }
            if self.settings.get("point_value")
            else None
        )
        return result

    def streak(self, member_id: str, done_today: bool = False) -> int:
        """Days in a row this member did all of their own chores.

        Worked out once and kept until something it depends on changes: the
        ledger (``version``), the family's data (chores, people, days away:
        ``_data_version``), the day or the streak rule. The badge check and
        every open screen ask for it after each change.
        """
        since = self.settings.get("streak_rule_from")
        today = dt_util.now().date()
        ledger = self.ledger
        key = (ledger.version, self._data_version, today, since)
        hit = self._streaks.get((member_id, done_today))
        if hit is not None and hit[0] == key:
            return hit[1]
        days = model.streak(
            ledger.member(member_id),
            member_id,
            today,
            self._has_own(member_id),
            date.fromisoformat(since) if since else None,
            done_today,
        )
        self._streaks[(member_id, done_today)] = (key, days)
        return days

    async def async_review(
        self,
        entry_id: str,
        approved: bool,
        penalty: int | None = None,
        *,
        reason: str | None = None,
        by: str | None = None,
    ) -> dict[str, Any]:
        """A parent checked a chore. Not done: its points are taken back, and
        a penalty on top (``penalty``, else the chore's, else the family's).

        ``reason`` says why it didn't happen; ``by`` is the parent's name.
        """
        entry = self._entry(entry_id)
        if entry.get("kind") != model.KIND_CHORE:
            raise FamilyError("Only chores are checked")
        entry.pop("auto", None)  # a parent checked it now
        entry["review"] = model.REVIEW_APPROVED if approved else model.REVIEW_REJECTED
        entry["reviewed_at"] = _now_iso()
        _set(entry, "reviewed_by", by)
        _set(entry, "reason", None if approved else model.clean_reason(reason))
        # A bonus this chore earned goes (or comes back) with it.
        for bonus in self.entries:
            if bonus.get("for_entry") == entry_id and bonus["kind"] == model.KIND_BONUS:
                if approved:
                    bonus.pop("review", None)
                else:
                    bonus["review"] = model.REVIEW_REJECTED
        # A penalty from an earlier check is replaced.
        self.entries[:] = [
            e
            for e in self.entries
            if not (e.get("for_entry") == entry_id and e["kind"] == model.KIND_PENALTY)
        ]
        taken = 0
        if not approved:
            taken = model.penalty_points(
                penalty, entry.get("penalty"), self.settings.get("penalty")
            )
            if taken:
                self.entries.append(
                    {
                        "id": _id(),
                        "at": _now_iso(),
                        "kind": model.KIND_PENALTY,
                        "member": entry["member"],
                        "title": entry["title"],
                        "points": -taken,
                        "for_entry": entry_id,
                    }
                    | ({"reason": entry["reason"]} if entry.get("reason") else {})
                    | ({"by": by} if by else {})
                )
        chore_id = entry.get("chore_id", "")
        if chore_id.startswith(TODO_PREFIX):
            # Didn't happen: put the to-do item back on the list.
            entity_id, _, uid = chore_id.removeprefix(TODO_PREFIX).rpartition(":")
            if not approved:
                await self._async_set_todo(entity_id, uid, False)
        self._changed()
        self.notices.clear(entry_id)
        self.hass.bus.async_fire(
            EVENT_CHORE_REVIEWED,
            {
                "member": self.member(entry["member"])["name"],
                "member_id": entry["member"],
                "chore": entry["title"],
                "approved": approved,
                "points": entry["points"],
                "penalty": taken,
                "balance": self.points(entry["member"]),
            },
        )
        return entry

    async def async_review_many(
        self,
        entry_ids: list[str],
        approved: bool,
        penalties: dict[str, int] | None = None,
        *,
        reason: str | None = None,
        by: str | None = None,
    ) -> int:
        """Check every chore in the list at once, as Done right or Didn't
        happen. Ones already checked (by another parent, or automatically) or
        gone are left alone. ``penalties`` holds a penalty per chore typed in
        its box; the others take their usual one. Returns how many were checked.
        """
        penalties = penalties or {}
        checked = 0
        for entry_id in dict.fromkeys(entry_ids):
            entry = next((e for e in self.entries if e["id"] == entry_id), None)
            if (
                entry is None
                or entry.get("kind") != model.KIND_CHORE
                or entry.get("review") != model.REVIEW_PENDING
            ):
                continue
            await self.async_review(
                entry_id, approved, penalties.get(entry_id), reason=reason, by=by
            )
            checked += 1
        return checked

    @callback
    def async_auto_check(self, _now: Any = None) -> None:
        """Count chores nobody checked as done right, after a day or a week."""
        due = model.due_for_auto_check(
            self.entries, dt_util.now(), self.settings.get("auto_check")
        )
        if not due:
            return
        for entry in due:
            entry["review"] = model.REVIEW_APPROVED
            entry["reviewed_at"] = _now_iso()
            entry["auto"] = True
        self._changed()
        for entry in due:
            self.notices.clear(entry["id"])
        for entry in due:
            self.hass.bus.async_fire(
                EVENT_CHORE_REVIEWED,
                {
                    "member": self._member_name(entry["member"]),
                    "member_id": entry["member"],
                    "chore": entry["title"],
                    "approved": True,
                    "automatic": True,
                    "points": entry["points"],
                    "balance": self.points(entry["member"]),
                },
            )

    def _member_name(self, member_id: str) -> str:
        return next(
            (m["name"] for m in self.members if m["id"] == member_id), "Someone"
        )

    def save_settings(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Change the settings that were sent; the rest stay."""
        if "auto_check" in raw:
            auto = raw.get("auto_check") or None
            if auto is not None and auto not in model.AUTO_CHECK:
                raise FamilyError("Pick when chores are checked automatically")
            self.settings["auto_check"] = auto
        for key, label in (
            ("bonus_all_done", "The all-done bonus"),
            ("streak_bonus", "The streak bonus"),
        ):
            if key in raw:
                self.settings[key] = model.clean_points(raw.get(key) or 0, label)
        if "penalty" in raw:
            self.settings["penalty"] = model.clean_points(
                raw.get("penalty") or 0, "The penalty"
            )
        if "streak_days" in raw:
            days = model.clean_points(raw.get("streak_days") or 0, "Days in a row")
            self.settings["streak_days"] = min(days, 365)
        if "family_goal" in raw:
            try:
                self.goals.save_legacy(
                    raw["family_goal"], bool(raw.get("restart_goal"))
                )
            except FamilyError:
                raise
            except ValueError as err:
                raise FamilyError(str(err)) from err
        if "reading" in raw:
            self.settings["reading"] = reading.clean_reading(raw.get("reading"))
        if "allowance_rule" in raw:
            self.settings["allowance_rule"] = allowance_rule.clean_rule(
                raw.get("allowance_rule")
            )
        if "helper_bonus" in raw:
            self.settings["helper_bonus"] = model.clean_points(
                raw.get("helper_bonus") or 0, "The helper bonus"
            )
        if "grade_points" in raw:
            self.settings["grade_points"] = extras.clean_grade_points(
                raw.get("grade_points")
            )
        if "theme_week" in raw:
            self.settings["theme_week"] = extras.clean_theme(raw.get("theme_week"))
        if "reward_list" in raw:
            todo = raw.get("reward_list") or None
            if todo is not None and not str(todo).startswith("todo."):
                raise FamilyError("Pick a to-do list for rewards to buy")
            self.settings["reward_list"] = todo
        if "age_points" in raw:
            self.settings["age_points"] = model.clean_age_points(raw.get("age_points"))
        if "homework" in raw:
            self.settings["homework"] = reading.clean_reading(raw.get("homework"))
        if "beat_clock_points" in raw:
            self.settings["beat_clock_points"] = model.clean_points(
                raw.get("beat_clock_points") or 0, "Beat the clock"
            )
        if "reminder_tts" in raw:
            tts = raw.get("reminder_tts") or None
            if tts is not None and not str(tts).startswith("tts."):
                raise FamilyError("Pick a text-to-speech voice")
            self.settings["reminder_tts"] = tts
        if "links" in raw:
            try:
                self.settings["links"] = model.clean_links(
                    raw.get("links") or [], {m["id"] for m in self.members}
                )
            except ValueError as err:
                raise FamilyError(str(err)) from err
        if "weather_entity" in raw:
            weather = raw.get("weather_entity") or None
            if weather is not None and not str(weather).startswith("weather."):
                raise FamilyError("Pick a weather entity")
            self.settings["weather_entity"] = weather
        if "live_from" in raw:
            self.settings["live_from"] = model.clean_time(raw["live_from"], "Show from")
        if "quick_points" in raw:
            family = [m["id"] for m in self.members]
            buttons = model.quick_points(raw["quick_points"])
            for button in buttons:
                if button["members"] is not None:
                    button["members"] = model.reward_selection(
                        self._known_members(button["members"]), family
                    )
            self.settings["quick_points"] = buttons
        if "hide_empty_sections" in raw:
            self.settings["hide_empty_sections"] = bool(raw["hide_empty_sections"])
        if "section_order" in raw:
            self.settings["section_order"] = model.section_order(raw["section_order"])
        if "notify_targets" in raw:
            targets = [str(t) for t in raw.get("notify_targets") or [] if t]
            unknown = [
                t for t in targets if not self.hass.services.has_service("notify", t)
            ]
            if unknown:
                raise FamilyError(f"There's no notify action called {unknown[0]}")
            self.settings["notify_targets"] = list(dict.fromkeys(targets))
        for key in (
            "notify_done",
            "notify_rewards",
            "weekly_summary",
            "live_activity",
            "live_per_child",
        ):
            if key in raw:
                self.settings[key] = bool(raw.get(key))
        if "allowance_day" in raw:
            day = int(raw.get("allowance_day") or 0)
            if not 0 <= day <= 6:
                raise FamilyError("Pick the day the allowance is given")
            self.settings["allowance_day"] = day
        if "allowance_hour" in raw:
            hour = int(raw.get("allowance_hour") or 0)
            if not 0 <= hour <= 23:
                raise FamilyError("Pick the hour the allowance is given")
            self.settings["allowance_hour"] = hour
        if "point_value" in raw:
            self.settings["point_value"] = model.clean_point_value(
                raw.get("point_value")
            )
        if "currency" in raw:
            self.settings["currency"] = str(raw.get("currency") or "").strip()[:4]
        if "saving_percent" in raw:
            percent = model.clean_points(raw.get("saving_percent") or 0, "Saving bonus")
            if percent > model.MAX_SAVING_PERCENT:
                raise FamilyError(
                    f"Keep the saving bonus at {model.MAX_SAVING_PERCENT}% or less"
                )
            self.settings["saving_percent"] = percent
        if "saving_max" in raw:
            self.settings["saving_max"] = model.clean_points(
                raw.get("saving_max") or 0, "Most a week"
            )
        if "goal_match" in raw:
            self.settings["goal_match"] = min(
                model.clean_points(raw.get("goal_match") or 0, "The match"), 100
            )
        if "bingo_line" in raw:
            self.settings["bingo_line"] = model.clean_points(
                raw.get("bingo_line") or 0, "Points for a line"
            )
        if "bingo_full" in raw:
            self.settings["bingo_full"] = model.clean_points(
                raw.get("bingo_full") or 0, "Points for the whole card"
            )
        if "give_percent" in raw:
            percent = model.clean_points(raw.get("give_percent") or 0, "Give share")
            if percent > MAX_GIVE_PERCENT:
                raise FamilyError(f"Keep the give share at {MAX_GIVE_PERCENT}% or less")
            self.settings["give_percent"] = percent
        if "give_goal" in raw:
            self.settings["give_goal"] = clean_give_goal(
                raw.get("give_goal"),
                self.settings.get("give_goal"),
                bool(raw.get("restart_give")),
            )
        if "leave_times" in raw:
            self.settings["leave_times"] = clean_leave_times(raw.get("leave_times"))
        if "leave_warn" in raw:
            self.settings["leave_warn"] = max(
                1, min(model.clean_points(raw.get("leave_warn") or 30, "Show it"), 120)
            )
        if "challenge_points" in raw:
            self.settings["challenge_points"] = model.clean_points(
                raw.get("challenge_points") or 0, "Points for winning a race"
            )
        if "freeze_cost" in raw:
            self.settings["freeze_cost"] = model.clean_points(
                raw.get("freeze_cost") or 0, "A streak freeze"
            )
        for key in ("quiet_from", "quiet_until"):
            if key in raw:
                self.settings[key] = model.clean_time(raw.get(key), "Quiet hours")
        if "mood_check" in raw:
            self.settings["mood_check"] = bool(raw.get("mood_check"))
        if "pick_points" in raw:
            self.settings["pick_points"] = model.clean_points(
                raw.get("pick_points") or 0, "Points each picks"
            )
        if "birthday_points" in raw:
            self.settings["birthday_points"] = model.clean_points(
                raw.get("birthday_points") or 0, "Birthday points"
            )
        if "calendars" in raw:
            self.settings["calendars"] = clean_calendars(
                raw.get("calendars"), {m["id"] for m in self.members}
            )
            self.calendar.watch()
            self.calendar.schedule()
        if "weather_entity" in raw:
            self.kids.watch_weather()
        self._changed()
        self.async_auto_check()
        if "allowance_day" in raw or "allowance_hour" in raw:
            self.async_allowance()
        return dict(self.settings)

    async def async_undo(self, entry_id: str) -> None:
        """Undo a tap on the shared screen: a chore or a reward, just now."""
        entry = self._entry(entry_id)
        if not model.can_undo(entry, dt_util.now()):
            raise FamilyError("That can't be undone any more. Ask a parent.")
        if entry["kind"] == model.KIND_REWARD and entry.get("tv"):
            # Take the TV time back first: if that fails, nothing changes.
            await self._async_grant_tv_time(
                entry["tv"],
                -int(entry.get("minutes", 0)),
                bool(entry.get("whole_home")),
                f"Undone: {entry['title']}",
            )
        if entry["kind"] == model.KIND_REWARD and entry.get("speaker"):
            await self._async_grant_music_time(
                entry["speaker"],
                -int(entry.get("minutes", 0)),
                f"Undone: {entry['title']}",
                bool(entry.get("whole_home")),
            )
        chore_id = entry.get("chore_id", "")
        if chore_id.startswith(TODO_PREFIX):
            entity_id, _, uid = chore_id.removeprefix(TODO_PREFIX).rpartition(":")
            await self._async_set_todo(entity_id, uid, False)
        # Screen time this chore unlocked goes back too.
        for bonus in [e for e in self.entries if e.get("for_entry") == entry_id]:
            if bonus.get("tv"):
                await self._async_unlock(
                    bonus, self.member(entry["member"]), -int(bonus["minutes"])
                )
        group = entry.get("group")
        self.entries[:] = [
            e
            for e in self.entries
            if e is not entry
            and e.get("for_entry") != entry_id
            and not (group and e.get("group") == group)
        ]
        self._changed()
        self.notices.clear(group or entry_id)
        if entry.get("photo"):
            await self.photos.async_delete(entry_id)

    # ---- rewards --------------------------------------------------------------

    def reward(self, reward_id: str) -> dict[str, Any]:
        for reward in self.rewards:
            if reward["id"] == reward_id:
                return reward
        raise FamilyError("That reward isn't on the list any more")

    def reward_eligible(self, reward: dict[str, Any]) -> str | list[str]:
        """Who can get this reward, for events and the points sensor.

        ``"everyone"``, or the names of the people a parent picked. An empty
        list means nobody can get it.
        """
        members = model.reward_members(reward)
        if members is None:
            return "everyone"
        return [self._member_name(member_id) for member_id in members]

    def _require_not_held(self, member: dict[str, Any]) -> None:
        """Refuse a redeem or a cash out while a parent has put rewards on hold."""
        until = model.held_until(member, dt_util.now())
        if until is None:
            return
        when = dt_util.as_local(until).strftime("%a %-d %b, %-I:%M %p")
        reason = f" ({member['hold_reason']})" if member.get("hold_reason") else ""
        raise FamilyError(
            f"{member['name']}'s rewards are on hold until {when}{reason}"
        )

    @callback
    def hold_rewards(
        self,
        member_id: str,
        *,
        days: int | None = None,
        until: str | None = None,
        reason: str | None = None,
        lift: bool = False,
    ) -> dict[str, Any]:
        """Put a hold on someone's rewards (and cashing out) for a while, or lift it.

        Chores still earn points and they can still save up; only spending waits.
        """
        member = self.member(member_id)
        if lift:
            member["rewards_held_until"] = None
            member["hold_reason"] = None
        else:
            try:
                day = date.fromisoformat(until) if until else None
                end = model.hold_end(dt_util.now(), days, day)
            except ValueError as err:
                raise FamilyError(str(err)) from err
            member["rewards_held_until"] = end.isoformat()
            member["hold_reason"] = (reason or "").strip()[:80] or None
        self._changed()
        self.hass.bus.async_fire(
            EVENT_REWARDS_HELD,
            {
                "member_id": member_id,
                "member": member["name"],
                "until": member["rewards_held_until"],
                "reason": member["hold_reason"],
            },
        )
        return member

    def _require_shop_day(self, reward: dict[str, Any]) -> None:
        """A reward with shop days can only be bought on those days."""
        days = reward.get("shop_days") or []
        if days and dt_util.now().weekday() not in days:
            raise FamilyError(
                f"{reward['name']} can only be bought on {model.weekday_names(days)}"
            )

    def _require_eligible(self, member: dict[str, Any], reward: dict[str, Any]) -> None:
        """Refuse a redeem or a goal when this reward isn't for them."""
        if model.reward_for(reward, member["id"]):
            return
        # The sentence comes from strings.json, so it can be translated.
        # Home Assistant drops the final period when it builds the message.
        key = (
            "reward_unavailable"
            if model.reward_members(reward) == []
            else "reward_not_for_member"
        )
        raise FamilyError(
            translation_domain=DOMAIN,
            translation_key=key,
            translation_placeholders={
                "name": str(member["name"]),
                "reward": str(reward["name"]),
            },
        )

    def _redeemed_event(
        self,
        member_name: str,
        member_id: str,
        reward: dict[str, Any],
        points: int,
        balance: int,
        together: str | None = None,
    ) -> dict[str, Any]:
        """Event data for a reward that was redeemed."""
        data: dict[str, Any] = {
            "member": member_name,
            "member_id": member_id,
            "reward": reward["name"],
            "points": points,
            "balance": balance,
            "eligible": self.reward_eligible(reward),
        }
        if together is not None:
            data["together"] = together
        return data

    async def async_redeem(
        self, member_id: str, reward_id: str, together: list[str] | None = None
    ) -> dict[str, Any]:
        """Spend points on a reward. TV time is given straight away.

        With ``together``, the others share the points, and a parent says yes
        first (``async_approve``). Anyone the reward isn't for is refused,
        here and in the shared redeem, before any points are taken.
        """
        if together:
            return self._redeem_together(member_id, reward_id, together)
        member = self.member(member_id)
        reward = self.reward(reward_id)
        self._require_eligible(member, reward)
        self._require_not_held(member)
        self._require_shop_day(reward)
        cost = int(reward.get("points", 0))
        # Saved up for it: a parent's match pays part of it.
        match = (
            model.match_points(cost, int(self.settings.get("goal_match") or 0))
            if member.get("goal") == reward_id
            else 0
        )
        if self.points(member_id) + match < cost:
            raise FamilyError(
                f"{member['name']} needs {cost - match} points for {reward['name']}"
            )
        if member_id in model.reward_used_by(reward, self.entries, dt_util.now()):
            when = "today" if reward.get("limit") == model.REPEAT_DAILY else "this week"
            raise FamilyError(f"{member['name']} already had {reward['name']} {when}")
        tv, given_now = await self._async_give_now(reward, member)
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": model.KIND_REWARD,
            "member": member_id,
            "title": reward["name"],
            "points": -cost,
            "reward_id": reward_id,
            "given": model.GIVEN_DONE if given_now else model.GIVEN_PENDING,
            **tv,
        }
        self.entries.append(entry)
        if match:
            self.entries.append(
                {
                    "id": _id(),
                    "at": _now_iso(),
                    "kind": model.KIND_BONUS,
                    "member": member_id,
                    "title": f"Matched for saving up: {reward['name']}",
                    "points": match,
                    "bonus": model.BONUS_MATCH,
                    "for_entry": entry["id"],
                }
            )
            entry = {**entry, "match": match}
        if member.get("goal") == reward_id:
            member["goal"] = None  # saved up and spent: the goal's done
        self._changed()
        if not given_now:
            self.notices.reward_to_give(entry, member)
            self._shop_for(reward, member["name"])
        self.hass.bus.async_fire(
            EVENT_REWARD_REDEEMED,
            self._redeemed_event(
                member["name"], member_id, reward, cost, self.points(member_id)
            ),
        )
        return entry

    async def _async_give_now(
        self, reward: dict[str, Any], member: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Give TV or music time straight away; other rewards wait for a parent.

        Returns what the entry keeps so an undo can take the time back, and
        whether it's already given.
        """
        kind = reward.get("kind")
        if kind == model.REWARD_TV_TIME:
            await self._async_give_tv_time(reward, member)
            return {
                "tv": reward["tv"],
                "minutes": int(reward.get("minutes", 0)),
                "whole_home": bool(reward.get("whole_home", False)),
            }, True
        if kind == model.REWARD_MUSIC_TIME:
            await self._async_give_music_time(reward, member)
            return {
                "speaker": reward["speaker"],
                "minutes": int(reward.get("minutes", 0)),
                "whole_home": bool(reward.get("whole_home", False)),
            }, True
        return {}, False

    async def async_claim_goal_reward(
        self, goal_id: str, member_id: str
    ) -> dict[str, Any]:
        """Use the reward a reached family goal unlocked: once, for no points.

        It's handed out like any reward (TV and music time straight away,
        anything else by a parent), and an undo puts it back.
        """
        member = self.member(member_id)
        goal, reward = self.goals.claimable(goal_id, member_id)
        tv, given_now = await self._async_give_now(reward, member)
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": model.KIND_REWARD,
            "member": member_id,
            "title": f"{reward['name']} ({goal['name']})",
            "points": 0,
            "reward_id": reward["id"],
            "goal_id": goal["id"],
            "goal_since": goal.get("since"),
            "given": model.GIVEN_DONE if given_now else model.GIVEN_PENDING,
            **tv,
        }
        self.entries.append(entry)
        self._changed()
        if not given_now:
            self.notices.reward_to_give(entry, member)
            self._shop_for(reward, member["name"])
        self.hass.bus.async_fire(
            EVENT_REWARD_REDEEMED,
            {
                **self._redeemed_event(
                    member["name"], member_id, reward, 0, self.points(member_id)
                ),
                "goal": goal["name"],
                "goal_id": goal["id"],
            },
        )
        return entry

    @callback
    def _redeem_together(
        self, member_id: str, reward_id: str, together: list[str]
    ) -> dict[str, Any]:
        """Hold each member's share of the points until a parent says yes."""
        ids = list(dict.fromkeys([member_id, *together]))
        if len(ids) < 2:
            raise FamilyError("Pick who's sharing it")
        members = [self.member(i) for i in ids]
        reward = self.reward(reward_id)
        self._require_shop_day(reward)
        for member in members:
            self._require_eligible(member, reward)
            self._require_not_held(member)
        cost = int(reward.get("points", 0))
        used = model.reward_used_by(reward, self.entries, dt_util.now())
        for member in members:
            if member["id"] in used:
                when = (
                    "today"
                    if reward.get("limit") == model.REPEAT_DAILY
                    else "this week"
                )
                raise FamilyError(
                    f"{member['name']} already had {reward['name']} {when}"
                )
        shares = model.split_points(cost, [(i, self.points(i)) for i in ids])
        if shares is None:
            have = sum(max(0, self.points(i)) for i in ids)
            raise FamilyError(
                f"Together they have {have} of the {cost} points for {reward['name']}"
            )
        for member in members:
            if cost and not shares[member["id"]]:
                raise FamilyError(f"{member['name']} has no points to put in")
        group = _id()
        at = _now_iso()
        entries = [
            {
                "id": _id(),
                "at": at,
                "kind": model.KIND_REWARD,
                "member": member["id"],
                "title": reward["name"],
                "points": -shares[member["id"]],
                "reward_id": reward_id,
                "given": model.GIVEN_APPROVAL,
                "group": group,
                "together": ids,
                "total": cost,
            }
            for member in members
        ]
        self.entries.extend(entries)
        self._changed()
        self.notices.reward_to_approve(
            group,
            model.names_text([m["name"] for m in members]),
            reward["name"],
            {m["name"]: shares[m["id"]] for m in members},
        )
        return entries[0]

    def _group(self, group_id: str) -> list[dict[str, Any]]:
        return [e for e in self.entries if e.get("group") == group_id]

    async def async_approve(self, group_id: str, approved: bool) -> None:
        """A parent says yes (the reward is given) or no (the points go back)."""
        entries = [
            e for e in self._group(group_id) if e.get("given") == model.GIVEN_APPROVAL
        ]
        if not entries:
            raise FamilyError("Someone dealt with that already")
        first = entries[0]
        names = model.names_text([self._member_name(e["member"]) for e in entries])
        if not approved:
            self.entries[:] = [e for e in self.entries if e.get("group") != group_id]
            self._changed()
            self.notices.clear(group_id)
            return
        reward = self.reward(first["reward_id"])
        kind = reward.get("kind")
        extra: dict[str, Any] = {}
        if kind == model.REWARD_TV_TIME:
            await self._async_give_tv_time(reward, {"name": names})
            extra = {"tv": reward["tv"]}
        elif kind == model.REWARD_MUSIC_TIME:
            await self._async_give_music_time(reward, {"name": names})
            extra = {"speaker": reward["speaker"]}
        if extra:
            # Kept once, on the first share, for History.
            first.update(
                extra,
                minutes=int(reward.get("minutes", 0)),
                whole_home=bool(reward.get("whole_home", False)),
            )
        given_now = bool(extra)
        for entry in entries:
            entry["given"] = model.GIVEN_DONE if given_now else model.GIVEN_PENDING
            entry["approved_at"] = _now_iso()
            if given_now:
                entry["given_at"] = entry["approved_at"]
        for member in self.members:
            if member["id"] in first["together"] and member.get("goal") == reward["id"]:
                member["goal"] = None
        self._changed()
        self.notices.clear(group_id)
        if not given_now:
            self.notices.reward_to_give(first, {"name": names})
            self._shop_for(reward, names)
        for entry in entries:
            self.hass.bus.async_fire(
                EVENT_REWARD_REDEEMED,
                self._redeemed_event(
                    self._member_name(entry["member"]),
                    entry["member"],
                    reward,
                    -int(entry["points"]),
                    self.points(entry["member"]),
                    names,
                ),
            )

    def _member_name(self, member_id: str) -> str:
        for member in self.members:
            if member["id"] == member_id:
                return str(member["name"])
        return "Someone"

    async def _async_give_tv_time(
        self, reward: dict[str, Any], member: dict[str, Any]
    ) -> None:
        if not self.hass.services.has_service(TV_MGMT_DOMAIN, TV_MGMT_GRANT):
            raise FamilyError("TV time needs TV Mgmt, which isn't set up")
        tv = reward.get("tv")
        if not tv or self.hass.config_entries.async_get_entry(tv) is None:
            raise FamilyError(f"The TV for {reward['name']} isn't set up any more")
        await self._async_grant_tv_time(
            tv,
            int(reward.get("minutes", 0)),
            bool(reward.get("whole_home", False)),
            f"{member['name']}'s reward: {reward['name']}",
        )

    async def async_grant_tv_time(
        self, tv: str, minutes: int, whole_home: bool, reason: str
    ) -> None:
        """For the screen-time bank (bank.py)."""
        await self._async_grant_tv_time(tv, minutes, whole_home, reason)

    async def _async_grant_tv_time(
        self, tv: str, minutes: int, whole_home: bool, reason: str
    ) -> None:
        """Give (or take back) minutes with ``tv_mgmt.grant_extension``.

        TV Mgmt 1.20.0 and newer takes ``profile_id`` (the TV's config
        entry) and ``minutes`` (extra time for today on that TV; negative
        takes it back; reset at midnight). ``whole_home`` adds the same
        minutes to the whole home's extra time for today. TV Mgmt itself
        counts every grant from this week toward the weekly limit. There is
        no day, week, or carry-over field. ``reason`` (Activity text, at
        most 100 characters) needs 1.21.0; older TV Mgmt is called again
        without it. A field the service doesn't know is rejected, so unused
        minutes the next day are left for TV Mgmt to keep available.
        """
        if not self.hass.services.has_service(TV_MGMT_DOMAIN, TV_MGMT_GRANT):
            raise FamilyError("TV time needs TV Mgmt, which isn't set up")
        data = {"profile_id": tv, "minutes": minutes, "whole_home": whole_home}
        try:
            try:
                await self.hass.services.async_call(
                    TV_MGMT_DOMAIN,
                    TV_MGMT_GRANT,
                    {**data, "reason": reason[:100]},
                    blocking=True,
                )
            except vol.Invalid:
                # TV Mgmt before 1.21.0 doesn't take a reason.
                await self.hass.services.async_call(
                    TV_MGMT_DOMAIN, TV_MGMT_GRANT, data, blocking=True
                )
        except (HomeAssistantError, vol.Invalid) as err:
            raise FamilyError(f"Couldn't give the TV time: {err}") from err

    async def _async_give_music_time(
        self, reward: dict[str, Any], member: dict[str, Any]
    ) -> None:
        speaker = reward.get("speaker")
        if not speaker or self.hass.config_entries.async_get_entry(speaker) is None:
            raise FamilyError(f"The speaker for {reward['name']} isn't set up any more")
        await self._async_grant_music_time(
            speaker,
            int(reward.get("minutes", 0)),
            f"{member['name']}'s reward: {reward['name']}",
            bool(reward.get("whole_home", False)),
        )

    async def _async_grant_music_time(
        self, speaker: str, minutes: int, reason: str, whole_home: bool = False
    ) -> None:
        """Give (or take back) listening time in Media Mgmt."""
        if not self.hass.services.has_service(MEDIA_MGMT_DOMAIN, MEDIA_MGMT_GRANT):
            raise FamilyError("Music time needs Media Mgmt, which isn't set up")
        data = {"profile_id": speaker, "minutes": minutes}
        extra: dict[str, Any] = {"reason": reason[:100]}
        if whole_home:
            extra["whole_home"] = True
        try:
            try:
                await self.hass.services.async_call(
                    MEDIA_MGMT_DOMAIN,
                    MEDIA_MGMT_GRANT,
                    {**data, **extra},
                    blocking=True,
                )
            except vol.Invalid:
                # Media Mgmt before 1.5.0 takes neither a reason nor the whole
                # home (it has no whole-home limit to give time to).
                await self.hass.services.async_call(
                    MEDIA_MGMT_DOMAIN, MEDIA_MGMT_GRANT, data, blocking=True
                )
        except (HomeAssistantError, vol.Invalid) as err:
            raise FamilyError(f"Couldn't give the music time: {err}") from err

    @callback
    def mark_given(self, entry_id: str, by: str | None = None) -> dict[str, Any]:
        entry = self._entry(entry_id)
        # Bought together: the whole group's handed out.
        for each in self._group(entry["group"]) if entry.get("group") else [entry]:
            each["given"] = model.GIVEN_DONE
            each["given_at"] = _now_iso()
            _set(each, "given_by", by)
        self._changed()
        self.notices.clear(entry_id)
        return entry

    @callback
    def mark_all_paid(self, member_id: str, by: str | None = None) -> int:
        """Every cash out a member is owed, paid."""
        self.member(member_id)
        paid = [
            e
            for e in self.entries
            if e.get("kind") == model.KIND_CASHOUT
            and e["member"] == member_id
            and e.get("given") == model.GIVEN_PENDING
        ]
        for entry in paid:
            entry["given"] = model.GIVEN_DONE
            entry["given_at"] = _now_iso()
            _set(entry, "given_by", by)
            self.notices.clear(entry["id"])
        if paid:
            self._changed()
        return len(paid)

    @callback
    def cash_out(self, member_id: str, points: Any) -> dict[str, Any]:
        """A member turns points into money; a parent pays it out.

        Needs a point value (Allowance and money). The points are taken now,
        like a reward, and the entry waits under To give until a parent marks
        it **Paid**, or cancels it and gives the points back.
        """
        member = self.member(member_id)
        self._require_not_held(member)
        value = self.settings.get("point_value")
        if not value:
            raise FamilyError(
                "Cashing out needs a point value. A parent sets it under Family."
            )
        try:
            points = model.cashout_points(points, self.points(member_id))
        except ValueError as err:
            raise FamilyError(str(err)) from err
        money = round(points * float(value), 2)
        currency = self.settings.get("currency") or ""
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": model.KIND_CASHOUT,
            "member": member_id,
            "title": f"Cash out {currency}{money:.2f}",
            "points": -points,
            "money": money,
            "given": model.GIVEN_PENDING,
        }
        self.entries.append(entry)
        self._changed()
        self.notices.reward_to_give(entry, member)
        return entry

    @callback
    def cancel_cash_out(self, entry_id: str) -> None:
        """A parent says no to a cash out: the points go back."""
        entry = self._entry(entry_id)
        if (
            entry.get("kind") != model.KIND_CASHOUT
            or entry.get("given") != model.GIVEN_PENDING
        ):
            raise FamilyError("That isn't a cash out waiting to be paid")
        self.entries.remove(entry)
        self.notices.clear(entry_id)
        self._changed()

    @callback
    def set_goal(self, member_id: str, reward_id: str | None) -> dict[str, Any]:
        """The reward a member is saving for, or None to stop.

        They can only save for a reward they are allowed to get.
        """
        member = self.member(member_id)
        if reward_id is not None:
            reward = self.reward(reward_id)
            self._require_eligible(member, reward)
        member["goal"] = reward_id
        self._changed()
        return member

    @callback
    def adjust(
        self,
        member_id: str,
        points: int,
        reason: str | None,
        by: str | None = None,
    ) -> dict[str, Any]:
        """Add or take away points by hand (or from an automation)."""
        member = self.member(member_id)
        points = model.clean_points(points, minimum=-model.MAX_POINTS)
        if points == 0:
            raise FamilyError("Give a number of points other than 0")
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": model.KIND_ADJUST,
            "member": member["id"],
            "title": (reason or "").strip()
            or ("Bonus points" if points > 0 else "Points taken away"),
            "points": points,
        }
        _set(entry, "by", by)
        self.entries.append(entry)
        self._changed()
        return entry

    def _entry(self, entry_id: str) -> dict[str, Any]:
        for entry in self.entries:
            if entry["id"] == entry_id:
                return entry
        raise FamilyError("That can't be found any more")

    # ---- editing (Parents dashboard) -------------------------------------------

    @callback
    def save_member(self, raw: dict[str, Any]) -> dict[str, Any]:
        member_id = raw.get("id") or _id()
        person = raw.get("person") or None
        if person and (
            other := next(
                (
                    m
                    for m in self.members
                    if m.get("person") == person and m["id"] != member_id
                ),
                None,
            )
        ):
            raise FamilyError(f"That person is already linked to {other['name']}")
        member = {
            "id": member_id,
            "name": model.clean_name(raw.get("name")),
            "person": person,
            "color": raw.get("color")
            or MEMBER_COLORS[len(self.members) % len(MEMBER_COLORS)],
            "emoji": model.clean_emoji(raw.get("emoji"), 4),
            # Big pictures and chores read aloud, for kids who can't read yet.
            "picture_mode": bool(raw.get("picture_mode")),
            # Points added every week (0: none).
            "allowance": model.clean_points(raw.get("allowance") or 0, "Allowance"),
            # "MM-DD": a countdown, a birthday bonus and a happy birthday.
            "birthday": model.clean_month_day(raw.get("birthday"), "Birthday"),
            # Optional: with the birthday, their age for age-based chores.
            "birth_year": model.clean_birth_year(
                raw.get("birth_year"), dt_util.now().year
            ),
            # Screen time their own chores unlock each day: minutes on a
            # TV Mgmt TV once all of their own chores are done.
            **_unlock(raw),
            # Unused minutes of this TV Mgmt TV are saved in their bank.
            **_bank(raw),
            # Added on the Family dashboard, not here: kept as they are.
            "gift_ideas": next(
                (m.get("gift_ideas") for m in self.members if m["id"] == member_id),
                None,
            )
            or [],
            # Chosen on the Family dashboard, not here: kept as they are.
            "wishes": next(
                (m.get("wishes") for m in self.members if m["id"] == member_id), None
            )
            or [],
            "goal": next(
                (m.get("goal") for m in self.members if m["id"] == member_id), None
            ),
            # Earned, not edited: kept as they are.
            "badges": next(
                (m.get("badges") for m in self.members if m["id"] == member_id), None
            )
            or {},
            # Set with Hold rewards, not here: kept as they are.
            **{
                key: next(
                    (m.get(key) for m in self.members if m["id"] == member_id), None
                )
                for key in ("rewards_held_until", "hold_reason", "birthday_year")
            },
        }
        new = self._upsert(self.members, member)
        self._changed(members=new)
        self.hass.async_create_background_task(
            self.async_refresh_parents(), "family parents"
        )
        return member

    @callback
    def save_chore(self, raw: dict[str, Any]) -> dict[str, Any]:
        repeat = raw.get("repeat") or model.REPEAT_DAILY
        if repeat not in model.REPEATS:
            raise FamilyError("Pick how often the chore can be done")
        todo_list = raw.get("todo_list") or None
        if todo_list is not None and not str(todo_list).startswith("todo."):
            raise FamilyError("Pick a to-do list")
        members = self._known_members(raw.get("members"))
        low = model.clean_age(raw.get("min_age"), "Youngest age")
        high = model.clean_age(raw.get("max_age"), "Oldest age")
        if low is not None and high is not None and low > high:
            raise FamilyError("The youngest age is more than the oldest")
        turns = bool(raw.get("turns"))
        turn_every = raw.get("turn_every") or model.TURN_EVERY_TIME
        if turns and len(members) < 2:
            raise FamilyError("Pick at least two people to take turns")
        if turn_every not in model.TURN_EVERY:
            raise FamilyError("Pick when the turn moves on")
        turn_first = raw.get("turn_first")
        if turns and turn_first not in members:
            turn_first = members[0]
        chore = {
            "id": raw.get("id") or _id(),
            "name": model.clean_name(raw.get("name"), "The chore's name"),
            "points": model.clean_points(raw.get("points", 0)),
            "members": members,
            # With people picked: up for grabs for them (whoever's first),
            # instead of each one's own chore. Nobody picked: always.
            "grab": bool(raw.get("grab")) and not turns,
            "repeat": repeat,
            # For "after_days": back this many days after it was done.
            "repeat_days": max(1, min(int(raw.get("repeat_days") or 1), 365))
            if repeat == model.REPEAT_AFTER_DAYS
            else None,
            "enabled": bool(raw.get("enabled", True)),
            "emoji": model.clean_emoji(raw.get("emoji"), 4),
            # Also kept on this to-do list; None: not on any list.
            "todo_list": todo_list,
            # With a to-do list: show only when its item is due today or
            # overdue (by the item's due date on the list).
            "due_only": bool(raw.get("due_only")) and bool(todo_list),
            # Extra points taken if it didn't happen; None: the family's.
            "penalty": model.optional_points(raw.get("penalty"), "The penalty"),
            # Only on these weekdays (Monday 0), and between these hours.
            "days": model.clean_days(raw.get("days")),
            "from_time": model.clean_time(raw.get("from_time"), "From"),
            "until_time": model.clean_time(raw.get("until_time"), "Until"),
            # Only in a season: from_date to until_date ("MM-DD"), both or neither.
            **_season(raw),
            # Its people take turns: turn_first's turn from now on.
            "turns": turns,
            "turn_every": turn_every if turns else None,
            "turn_first": turn_first if turns else None,
            "turn_from": _now_iso() if turns else None,
            # Said on these speakers at this time while it's still to do.
            "remind_time": model.clean_time(raw.get("remind_time"), "Remind at"),
            "remind_speakers": [
                str(e)
                for e in raw.get("remind_speakers") or []
                if str(e).startswith("media_player.")
            ],
            # Only for people this age (either may be left out).
            "min_age": low,
            "max_age": high,
            # A countdown on the tile (0: none), and points for beating it.
            "timer_minutes": model.clean_timer(raw.get("timer_minutes")),
            "timer_bonus": model.clean_points(
                raw.get("timer_bonus") or 0, "The timer bonus"
            ),
            # Ask for a photo when it's marked done ("", "ask", "need").
            "photo": model.clean_photo(raw.get("photo")),
            # Points for doing it so many days (weeks) in a row (0: none).
            "streak_days": min(
                model.clean_points(raw.get("streak_days") or 0, "Days in a row"),
                model.MAX_STREAK_DAYS,
            ),
            "streak_bonus": model.clean_points(
                raw.get("streak_bonus") or 0, "The streak bonus"
            ),
            # In the weekly pick-your-chores pool: nobody's until picked.
            "pool": bool(raw.get("pool")),
            # How to do it, shown when someone taps the chore, and whether
            # it has a photo of what done looks like (set with chore/example).
            "how": str(raw.get("how") or "").strip()[:1000],
            "example": bool(
                next(
                    (c.get("example") for c in self.chores if c["id"] == raw.get("id")),
                    False,
                )
            ),
            # Done when a device changes to a state (a robot vacuum docked).
            "done_when": _done_when(raw.get("done_when")),
            # Only while something shows a state (Daily Routine's Kind of
            # day is School day, the bins are out…).
            "only_when": _only_when(raw.get("only_when")),
            # When it's done, also start this script, scene or button.
            "on_done": _on_done(raw.get("on_done")),
            # How hard it is ("", easy, medium, hard): shown on the tile.
            "difficulty": raw.get("difficulty")
            if raw.get("difficulty") in model.DIFFICULTIES
            else "",
        }
        # Put out by a parent (Add now): kept through an edit.
        chore["offered"] = (
            next(
                (c.get("offered") for c in self.chores if c["id"] == chore["id"]),
                None,
            )
            if repeat == model.REPEAT_ON_DEMAND
            else None
        )
        if chore["pool"] and chore["turns"]:
            raise FamilyError(
                "A chore is either picked from the pool or taken in turns"
            )
        # A team chore: each of its people ticks it, and the points count
        # once they all have.
        chore["team"] = bool(raw.get("team"))
        if chore["team"]:
            if len(members) < 2:
                raise FamilyError("Pick at least two people for a team chore")
            if chore["grab"] or chore["turns"] or chore["pool"]:
                raise FamilyError(
                    "A team chore is done by everyone on it: not up for grabs, "
                    "in turns or from the pool"
                )
        self._upsert(self.chores, chore)
        self._changed()
        self.done_when.watch()
        return chore

    def _reward_members(
        self, raw: dict[str, Any], existing: dict[str, Any] | None
    ) -> list[str] | None:
        """Who the saved reward is for.

        None: everyone, including people added later. That is a new reward,
        an explicit null, or a list that names every current member. A
        shorter list: only those members, after unknown ids are dropped. An
        empty list: nobody, so the reward is unavailable. Leaving the key
        out keeps what was saved (everyone, for a new reward). A list saved
        earlier that happens to name every member stays as it is until this
        reward is saved again.
        """
        if "members" not in raw:
            if existing is None or existing.get("members") is None:
                return None
            return self._known_members(existing.get("members"))
        if raw["members"] is None:
            return None
        if not isinstance(raw["members"], list):
            raise FamilyError("Pick who can get it")
        picked = self._known_members(raw["members"])
        return model.reward_selection(picked, [m["id"] for m in self.members])

    def _clear_ineligible_goals(self, reward: dict[str, Any]) -> None:
        """Stop anyone saving for a reward they can no longer get."""
        for member in self.members:
            if member.get("goal") == reward["id"] and not model.reward_for(
                reward, member["id"]
            ):
                member["goal"] = None

    @callback
    def save_reward(self, raw: dict[str, Any]) -> dict[str, Any]:
        kind = raw.get("kind") or model.REWARD_CUSTOM
        if kind not in model.REWARD_KINDS:
            raise FamilyError("Pick what kind of reward it is")
        reward_id = raw.get("id") or _id()
        existing = next((r for r in self.rewards if r["id"] == reward_id), None)
        reward: dict[str, Any] = {
            "id": reward_id,
            "name": model.clean_name(raw.get("name"), "The reward's name"),
            "points": model.clean_points(raw.get("points", 0), "Its cost"),
            "kind": kind,
            "emoji": model.clean_emoji(raw.get("emoji"), 4),
            # Each person at most once a day or a week; None: any time.
            # Only for sale on these weekdays (Monday 0); none: any day.
            "shop_days": model.clean_days(raw.get("shop_days")),
            "limit": raw.get("limit")
            if raw.get("limit") in model.REWARD_LIMITS
            else None,
            # None: everyone. A list: only those people. []: nobody.
            "members": self._reward_members(raw, existing),
        }
        if kind == model.REWARD_MUSIC_TIME:
            if not raw.get("speaker"):
                raise FamilyError("Pick the speaker the time is for")
            minutes = model.clean_points(raw.get("minutes"), "Minutes", minimum=1)
            reward.update(
                speaker=raw["speaker"],
                minutes=min(minutes, 240),
                whole_home=bool(raw.get("whole_home")),
            )
        if kind == model.REWARD_TV_TIME:
            if not raw.get("tv"):
                raise FamilyError("Pick the TV the time is for")
            minutes = model.clean_points(raw.get("minutes"), "Minutes", minimum=1)
            reward.update(
                tv=raw["tv"],
                minutes=min(minutes, 240),
                whole_home=bool(raw.get("whole_home")),
            )
        self._upsert(self.rewards, reward)
        self._clear_ineligible_goals(reward)
        self._changed()
        return reward

    async def async_save_todo_list(self, raw: dict[str, Any]) -> dict[str, Any]:
        entity_id = raw.get("entity_id") or ""
        if not entity_id.startswith("todo."):
            raise FamilyError("Pick a to-do list")
        existing = next((t for t in self.todo_lists if t["id"] == entity_id), {})
        # Points for single items, by name. Kept for items not on the list
        # right now, so a repeating chore keeps its points when it's back.
        rated = dict(existing.get("item_points") or {})
        for name, value in (raw.get("item_points") or {}).items():
            if not (key := model.item_key(name)):
                continue
            if value is None or value == "":
                rated.pop(key, None)
            else:
                rated[key] = model.clean_points(value)
        # Who single items are for, by name, kept the same way. None or
        # nobody ticked: the list's people.
        assigned = dict(existing.get("item_members") or {})
        for name, ids in (raw.get("item_members") or {}).items():
            if not (key := model.item_key(name)):
                continue
            if picked := self._known_members(ids or []):
                assigned[key] = picked
            else:
                assigned.pop(key, None)
        # Emojis for single items, by name, kept the same way; empty removes.
        emojis = dict(existing.get("item_emojis") or {})
        for name, emoji in (raw.get("item_emojis") or {}).items():
            if not (key := model.item_key(name)):
                continue
            if text := model.clean_emoji(emoji):
                emojis[key] = text
            else:
                emojis.pop(key, None)
        # Items left out of the chores, by name, kept the same way.
        skipped = set(existing.get("item_skip") or [])
        for name, skip in (raw.get("item_skip") or {}).items():
            if not (key := model.item_key(name)):
                continue
            if skip:
                skipped.add(key)
            else:
                skipped.discard(key)
        todo = {
            "id": entity_id,
            "entity_id": entity_id,
            "points": model.clean_points(raw.get("points", 0)),
            "members": self._known_members(raw.get("members")),
            # Its items are up for grabs for its people, not their own chores.
            "grab": bool(raw.get("grab")),
            "item_points": rated,
            "item_members": assigned,
            "item_emojis": emojis,
            "item_skip": sorted(skipped),
            # Only items due now or overdue show as chores; ones with no due
            # date always do.
            "due_only": bool(raw.get("due_only")),
            "penalty": model.optional_points(raw.get("penalty"), "The penalty"),
        }
        self._upsert(self.todo_lists, todo)
        self._watch_todo_lists()
        await self.async_refresh_todo()
        self._changed()
        return todo

    @callback
    def save_control(self, raw: dict[str, Any]) -> dict[str, Any]:
        entity_id = raw.get("entity_id") or ""
        if model.control_kind(entity_id) is None:
            raise FamilyError("Pick something to show")
        control = {
            "id": raw.get("id") or _id(),
            "entity_id": entity_id,
            # Blank: use the entity's own name, and follow its renames.
            "name": (raw.get("name") or "").strip()[:60] or None,
            "emoji": model.clean_emoji(raw.get("emoji"), 4),
            "members": self._known_members(raw.get("members")),
            "confirm": bool(raw.get("confirm")),
        }
        self._upsert(self.controls, control)
        self._changed()
        return control

    @callback
    def move(self, collection: str, item_id: str, offset: int) -> None:
        """Move an item up (-1) or down (+1) in its list."""
        items = self._collection(collection)
        index = next((i for i, x in enumerate(items) if x["id"] == item_id), None)
        if index is None:
            raise FamilyError("That can't be found any more")
        target = max(0, min(len(items) - 1, index + offset))
        items.insert(target, items.pop(index))
        self._changed()

    def control(self, control_id: str) -> dict[str, Any]:
        for control in self.controls:
            if control["id"] == control_id:
                return control
        raise FamilyError("That isn't on the dashboard any more")

    async def async_control(
        self, control_id: str, action: str, context: Context | None = None
    ) -> None:
        """Run a dashboard control. Only entities a parent added can be used."""
        control = self.control(control_id)
        entity_id = control["entity_id"]
        try:
            domain, service = model.control_service(entity_id, action)
        except ValueError as err:
            raise FamilyError(f"{self._control_name(control)} can't do that") from err
        state = self.hass.states.get(entity_id)
        if state is None or state.state == "unavailable":
            raise FamilyError(f"{self._control_name(control)} isn't available")
        if not self.hass.services.has_service(domain, service):
            raise FamilyError(f"{self._control_name(control)} can't do that")
        await self.hass.services.async_call(
            domain, service, {"entity_id": entity_id}, blocking=True, context=context
        )

    def _control_name(self, control: dict[str, Any]) -> str:
        return control.get("name") or self._state_name(control["entity_id"])

    def _collection(self, collection: str) -> list[dict[str, Any]]:
        return {
            "members": self.members,
            "chores": self.chores,
            "rewards": self.rewards,
            "todo_lists": self.todo_lists,
            "controls": self.controls,
            "routines": self.routines.items,
        }[collection]

    async def async_delete(self, collection: str, item_id: str) -> None:
        items = self._collection(collection)
        items[:] = [i for i in items if i["id"] != item_id]
        if collection == "chores":
            self.done_when.forget_chore(item_id)
            self.done_when.watch()
        if collection == "members":
            self.routines.forget_member(item_id)
            self.countdowns.forget_member(item_id)
            self.requests.forget_member(item_id)
            self.vote.forget_member(item_id)
            self.picks.forget_member(item_id)
            self.chore_ideas.forget_member(item_id)
            self.auctions.forget_member(item_id)
            self.goals.forget_member(item_id)
            self.bank.forget_member(item_id)
            self.moods.forget_member(item_id)
            self.quests.forget_member(item_id)
            self.pets.forget_member(item_id)
            for chore in [*self.chores, *self.todo_lists, *self.controls]:
                chore["members"] = [m for m in chore.get("members", []) if m != item_id]
            # Drop them from rewards they were picked for. An empty list stays
            # empty: the reward is unavailable, it does not become everyone's.
            # A reward for everyone (None) is left as it is.
            for reward in self.rewards:
                picked = reward.get("members")
                if picked:
                    reward["members"] = [m for m in picked if m != item_id]
            for button in self.settings.get("quick_points") or []:
                if button.get("members"):
                    button["members"] = [m for m in button["members"] if m != item_id]
            for row in [*(self.settings.get("calendars") or []), *self.notes]:
                if row.get("member") == item_id:
                    row["member"] = None
            for member in self.members:
                goal = member.get("goal")
                if not goal:
                    continue
                try:
                    reward = self.reward(goal)
                except FamilyError:
                    member["goal"] = None
                else:
                    if not model.reward_for(reward, member["id"]):
                        member["goal"] = None
        if collection == "rewards":
            for member in self.members:
                if member.get("goal") == item_id:
                    member["goal"] = None
            self.goals.forget_reward(item_id)
        if collection == "todo_lists":
            self._watch_todo_lists()
            self.todo_items.pop(item_id, None)
        self._changed(members=collection == "members")

    def _known_members(self, raw: Any) -> list[str]:
        known = {m["id"] for m in self.members}
        return [m for m in dict.fromkeys(raw or []) if m in known]

    @staticmethod
    def _upsert(items: list[dict[str, Any]], item: dict[str, Any]) -> bool:
        """Replace by id, or add. Returns True when it was added."""
        for index, existing in enumerate(items):
            if existing["id"] == item["id"]:
                items[index] = item
                return False
        items.append(item)
        return True

    # ---- to-do lists ------------------------------------------------------------

    @callback
    def _watch_todo_lists(self) -> None:
        if self._unsub_todo:
            self._unsub_todo()
            self._unsub_todo = None
        entity_ids = [t["entity_id"] for t in self.todo_lists]
        if not entity_ids:
            return

        async def _on_change(event: Event) -> None:
            entity_id = event.data["entity_id"]
            # Family's own tick or untick: it reads the list itself after.
            if self._todo_writing.get(entity_id):
                return
            before = self.todo_items.get(entity_id)
            await self.async_refresh_todo(entity_id)
            # Only tell the dashboards when the open items really changed.
            if self.todo_items.get(entity_id) != before:
                self._notify()

        self._unsub_todo = async_track_state_change_event(
            self.hass, entity_ids, _on_change
        )

    async def async_refresh_todo(self, only: str | None = None) -> None:
        """Read the open items of the chore to-do lists."""
        for todo in self.todo_lists:
            entity_id = todo["entity_id"]
            if only and entity_id != only:
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unavailable", "unknown"):
                self.todo_items[entity_id] = []
                continue
            try:
                response = await self.hass.services.async_call(
                    "todo",
                    "get_items",
                    {"entity_id": entity_id, "status": ["needs_action"]},
                    blocking=True,
                    return_response=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Family: couldn't read %s: %s", entity_id, err)
                continue
            items = (response or {}).get(entity_id, {}).get("items", [])
            self.todo_items[entity_id] = [i for i in items if i.get("uid")]

    async def _async_set_todo(self, entity_id: str, uid: str, done: bool) -> None:
        """Tick an item off a chore list (or put it back), then read the list.

        The list's own state change for this is skipped (``_todo_writing``,
        see _watch_todo_lists): the read here is the one read, and it tells
        the dashboards when the open items changed.
        """
        before = self.todo_items.get(entity_id)
        self._todo_writing[entity_id] = self._todo_writing.get(entity_id, 0) + 1
        try:
            try:
                await self.hass.services.async_call(
                    "todo",
                    "update_item",
                    {
                        "entity_id": entity_id,
                        "item": uid,
                        "status": "completed" if done else "needs_action",
                    },
                    blocking=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Family: couldn't update %s: %s", entity_id, err)
            await self.async_refresh_todo(entity_id)
        finally:
            if (left := self._todo_writing.get(entity_id, 1) - 1) > 0:
                self._todo_writing[entity_id] = left
            else:
                self._todo_writing.pop(entity_id, None)
        if self.todo_items.get(entity_id) != before:
            self._notify()

    # ---- automations --------------------------------------------------------------

    async def async_handle_add_points(self, call: ServiceCall) -> None:
        name = str(call.data["member"]).strip().lower()
        member = next(
            (
                m
                for m in self.members
                if m["id"] == call.data["member"] or m["name"].lower() == name
            ),
            None,
        )
        if member is None:
            raise FamilyError(f"No family member called {call.data['member']}")
        self.adjust(member["id"], call.data["points"], call.data.get("reason"))

    # ---- what the dashboards show ------------------------------------------------------

    def snapshot(
        self, user_id: str | None, is_admin: bool, parent: bool | None = None
    ) -> dict[str, Any]:
        """Everything a Family dashboard shows, for this login and view.

        Every open screen asks again after each change. Screens that ask for
        the same thing (the same login, admin or not, parent view or not)
        within ``SNAPSHOT_SHARE_SECONDS`` of each other, in the same minute
        and with nothing changed in between (see the key below), get the same
        answer instead of each working it out. Callers must not change it.
        """
        now = dt_util.now()
        loop_now = self.hass.loop.time()
        who = (user_id, is_admin, parent)
        # Any change told to the dashboards (revision), any data saved
        # without telling them (_data_version: a setting, a to-do link) and
        # any new history (the ledger's version) means a new answer.
        key = (
            self.revision,
            self._data_version,
            self.ledger.version,
            now.date(),
            now.hour,
            now.minute,
        )
        hit = self._snapshots.get(who)
        if (
            hit is not None
            and hit[0] == key
            and loop_now - hit[1] < SNAPSHOT_SHARE_SECONDS
        ):
            return hit[2]
        result = self._snapshot(now, user_id, is_admin, parent)
        self._snapshots[who] = (key, loop_now, result)
        return result

    def _snapshot(
        self,
        now: datetime,
        user_id: str | None,
        is_admin: bool,
        parent: bool | None,
    ) -> dict[str, Any]:
        today = now.date()
        ledger = self.ledger
        chores_now = self.all_chores()
        own = {
            m["id"]: self._own_status(m["id"], chores_now, now) for m in self.members
        }
        members = [
            {
                **m,
                "points": self.points(m["id"]),
                "streak": self.streak(m["id"]),
                # Their own chores today (not ones up for grabs): how many,
                # how many are left, and whether they finished them all.
                "own_today": {
                    "total": own[m["id"]][0],
                    "left": own[m["id"]][1],
                    "done": model.bonus_given(
                        ledger.member(m["id"]), m["id"], model.BONUS_ALL_DONE, today
                    ),
                    # Left, but their hours are over for today.
                    "missed": own[m["id"]][2],
                },
                "done_today": len(
                    model.chores_done_on(ledger.day(today), today, m["id"])
                ),
                "picture": self.picture(m),
                "mood_today": self.moods.today(m["id"]),
                "freeze_offers": self.freeze_offers(m["id"]),
                "badges": model.badge_list(m.get("badges")),
                "birthday_today": savings.birthday_today(m),
                # While rewards are on hold: when that ends (None: not held).
                "held_until": (
                    held.isoformat()
                    if (held := model.held_until(m, dt_util.now()))
                    else None
                ),
                "to_check": sum(
                    1
                    for e in ledger.member(m["id"])
                    if e["member"] == m["id"]
                    and e.get("review") == model.REVIEW_PENDING
                ),
            }
            for m in self.members
        ]
        rewards = [
            {
                **r,
                "tv_name": self._tv_name(r.get("tv")),
                "speaker_name": self._tv_name(r.get("speaker")),
                "used_by": sorted(
                    model.reward_used_by(r, ledger.kind(model.KIND_REWARD), now)
                ),
            }
            for r in self.rewards
        ]
        # The 30 newest, from the ledger's time order (no sorting).
        recent = ledger.newest(30)
        controls = [
            {
                **c,
                "label": self._control_name(c),
                "kind": model.control_kind(c["entity_id"]),
            }
            for c in self.controls
        ]
        result: dict[str, Any] = {
            # The change this answer includes (see ``_notify``).
            "revision": self.revision,
            "members": members,
            "chores": self.chores_for(None),
            "routines": self.routines.today(),
            "rewards": rewards,
            "controls": controls,
            "done_today": sorted(
                model.chores_done_on(ledger.day(today), today),
                key=lambda e: e["at"],
                reverse=True,
            ),
            "bonus": {
                "all_done": int(self.settings.get("bonus_all_done") or 0),
                "streak_days": int(self.settings.get("streak_days") or 0),
                "streak": int(self.settings.get("streak_bonus") or 0),
            },
            "recent": recent,
            "today": self.calendar.on(today.isoformat()),
            # The Today section's "Next few days": today and the days after it.
            "upcoming": [
                {"date": day, "events": self.calendar.on(day)}
                for day in model.week_days(today, CALENDAR_DAYS)
            ],
            "has_calendars": bool(self.calendar.calendars),
            "meals": [
                {"date": day, **self.meals.get(day, {})}
                for day in model.week_days(today)
            ],
            "notes": sorted(
                (n for n in self.notes if model.note_current(n, today)),
                key=lambda n: n["at"],
                reverse=True,
            ),
            "money": {
                "value": self.settings.get("point_value"),
                "currency": self.settings.get("currency") or "",
            }
            if self.settings.get("point_value")
            else None,
            "trades": self.trades.snapshot(),
            "tomorrow": self.kids.tomorrow(),
            "screen": self.kids.screen(),
            "weather": self.kids.weather(),
            "family_streak": self.kids.family_streak(today),
            "links": self.settings.get("links") or [],
            "countdowns": self.countdowns.snapshot(today),
            "vote": self.vote.snapshot(),
            "requests": self.requests.snapshot(),
            "boosts": self.boosts.snapshot(),
            "away": self.away.snapshot(),
            "picks": self.picks.snapshot(),
            "claims": self.done_when.snapshot(),
            "me": self.member_for_user(user_id),
            "is_admin": is_admin,
            "parent": bool(is_admin if parent is None else parent),
            "pin_set": self.passes.pin_set,
            # Admins: which PINs are set, for the PIN card (never the PINs).
            "pins": self.passes.status(user_id) if is_admin else None,
            "undo_seconds": model.UNDO_SECONDS,
            # The Family dashboard's sections, in the order a parent set.
            "section_order": model.section_order(self.settings.get("section_order")),
            "hide_empty_sections": bool(self.settings.get("hide_empty_sections")),
            "family_goal": self.family_goal(),
            # A parent's match on what someone saves up for (percent).
            "goal_match": int(self.settings.get("goal_match") or 0),
            "bingo": self.bingo.snapshot(),
            "give": self.give.snapshot(),
            "leave": None if self.away.on(today) else leave_at(self.settings, now),
            "chore_ideas": self.chore_ideas.snapshot(),
            "challenges": self.challenges.snapshot(),
            "family_goals": self.goals.snapshot(),
            "auctions": self.auctions.snapshot(),
            "bank": self.bank.snapshot(),
            "reading": reading.public_rule(self.settings.get("reading")),
            "reading_today": {
                m["id"]: reading.minutes_today(ledger.day(today), m["id"], today)
                for m in self.members
            },
            "homework": reading.public_rule(self.settings.get("homework")),
            "homework_today": {
                m["id"]: reading.minutes_today(
                    ledger.day(today), m["id"], today, reading.HOMEWORK_CHORE
                )
                for m in self.members
            },
            "saving_next": savings.next_bonus(self),
            "theme": extras.theme_today(self, today),
            "grade_points": self.settings.get("grade_points") or extras.DEFAULT_GRADES,
            "beat_clock": int(self.settings.get("beat_clock_points") or 0),
            "challenge_points": int(self.settings.get("challenge_points") or 0),
            "mood_check": bool(self.settings.get("mood_check")),
            "quests": self.quests.snapshot(),
            "pets": self.pets.snapshot(),
            "freeze_cost": int(self.settings.get("freeze_cost") or 0),
            # The shared screen rests between these times (None: never).
            "quiet": {
                "from": self.settings.get("quiet_from"),
                "until": self.settings.get("quiet_until"),
            }
            if self.settings.get("quiet_from") and self.settings.get("quiet_until")
            else None,
        }
        if is_admin if parent is None else parent:
            result["owed"] = model.money_owed(self.entries)
            result["settings"] = {
                "auto_check": self.settings.get("auto_check"),
                "penalty": int(self.settings.get("penalty") or 0),
                "notify_targets": list(self.settings.get("notify_targets") or []),
                "notify_done": bool(self.settings.get("notify_done")),
                "notify_rewards": bool(self.settings.get("notify_rewards")),
                "weekly_summary": bool(self.settings.get("weekly_summary")),
                "live_activity": bool(self.settings.get("live_activity")),
                "live_per_child": bool(self.settings.get("live_per_child")),
                "live_from": self.settings.get("live_from"),
                "allowance_day": int(
                    self.settings.get("allowance_day", model.DEFAULT_ALLOWANCE_DAY)
                ),
                "allowance_hour": int(
                    self.settings.get("allowance_hour", model.DEFAULT_ALLOWANCE_HOUR)
                ),
                "point_value": self.settings.get("point_value"),
                "currency": self.settings.get("currency") or "",
                "calendars": list(self.settings.get("calendars") or []),
                "quick_points": list(self.settings.get("quick_points") or []),
                "reminder_tts": self.settings.get("reminder_tts"),
                "weather_entity": self.settings.get("weather_entity"),
                "saving_percent": int(self.settings.get("saving_percent") or 0),
                "saving_max": int(self.settings.get("saving_max") or 0),
                "birthday_points": int(self.settings.get("birthday_points") or 0),
                "pick_points": int(self.settings.get("pick_points") or 0),
                "goal_match": int(self.settings.get("goal_match") or 0),
                "shopping_list": self.settings.get("shopping_list"),
                "bingo_line": int(self.settings.get("bingo_line") or 0),
                "bingo_full": int(self.settings.get("bingo_full") or 0),
                "give_percent": int(self.settings.get("give_percent") or 0),
                "give_goal": self.settings.get("give_goal"),
                "leave_times": dict(self.settings.get("leave_times") or {}),
                "leave_warn": int(self.settings.get("leave_warn") or 30),
                "challenge_points": int(self.settings.get("challenge_points") or 0),
                "mood_check": bool(self.settings.get("mood_check")),
                "freeze_cost": int(self.settings.get("freeze_cost") or 0),
                "quiet_from": self.settings.get("quiet_from"),
                "quiet_until": self.settings.get("quiet_until"),
            }
            result["most_wanted"] = self.most_wanted()
            if self.settings.get("mood_check"):
                result["moods"] = self.moods.recent(today)
            # The history numbers' key, worked out once for all of them.
            history_key = self._history_key()
            result["weeks"] = self._cached(
                "weeks",
                lambda: model.weekly_stats(
                    self.entries, [m["id"] for m in self.members], today
                ),
                history_key,
            )
            result["all_chores"] = self.chores
            result["demand_showing"] = self.demand_showing_ids()
            result["all_routines"] = self.routines.items
            result["todo_lists"] = [
                {
                    **t,
                    "name": self._state_name(t["entity_id"]),
                    "items": self._todo_item_rows(t),
                }
                for t in self.todo_lists
            ]
            result["to_check"] = [
                e
                for e in reversed(self.entries)
                if e.get("review") == model.REVIEW_PENDING
            ]
            groups: set[str] = set()
            result["to_give"] = []
            for e in reversed(self.entries):
                if e.get("given") != model.GIVEN_PENDING:
                    continue
                if e.get("group"):
                    # A reward bought together is handed out once.
                    if e["group"] in groups:
                        continue
                    groups.add(e["group"])
                result["to_give"].append(e)
            approve: dict[str, dict[str, Any]] = {}
            for e in self.entries:
                if e.get("given") != model.GIVEN_APPROVAL:
                    continue
                request = approve.setdefault(
                    e["group"],
                    {
                        "group": e["group"],
                        "at": e["at"],
                        "title": e["title"],
                        "reward_id": e.get("reward_id"),
                        "points": int(e.get("total", 0)),
                        "shares": [],
                    },
                )
                request["shares"].append(
                    {"member": e["member"], "points": -int(e["points"])}
                )
            result["to_approve"] = sorted(
                approve.values(), key=lambda r: r["at"], reverse=True
            )
            result["history"], result["history_more"] = self.history(key=history_key)
            result["balance_days"] = self._cached(
                "balance_days",
                lambda: model.daily_balances(
                    self.entries,
                    self.carried,
                    [m["id"] for m in self.members],
                    dt_util.now().date(),
                    BALANCE_DAYS,
                ),
                history_key,
            )
        return result

    def history(
        self,
        before: str | None = None,
        limit: int = HISTORY_PAGE,
        key: tuple[Any, ...] | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Newest first, older than ``before`` (an entry's time), with each
        entry's points before and after it. Also whether there's more.
        ``key``: the ``_history_key()`` when the caller already has it."""
        if key is None:
            key = self._history_key()
        balances = self._cached(
            "running",
            lambda: model.running_balances(self.entries, self.carried),
            key,
        )
        newest = self._cached(
            "newest",
            lambda: sorted(self.entries, key=lambda e: e["at"], reverse=True),
            key,
        )
        if before:
            newest = [e for e in newest if e["at"] < before]
        page = [
            {**e, "before": balances[e["id"]][0], "after": balances[e["id"]][1]}
            if e.get("id") in balances
            else dict(e)
            for e in newest[:limit]
        ]
        return page, len(newest) > limit

    def _todo_item_rows(self, todo: dict[str, Any]) -> list[dict[str, Any]]:
        """The list's open items and their points, for the Parents dashboard."""
        rows = []
        for item in self.todo_items.get(todo["entity_id"], []):
            summary = item.get("summary", "")
            name, points, rated = model.todo_item_points(
                summary, int(todo.get("points", 0)), todo.get("item_points")
            )
            _name, unrated = model.todo_points(summary, int(todo.get("points", 0)))
            rows.append(
                {
                    "name": name,
                    "points": points,
                    "rated": rated,
                    "unrated": unrated,
                    # Who it's for when it has its own people, else empty.
                    "members": list(
                        (todo.get("item_members") or {}).get(model.item_key(name), [])
                    ),
                    "emoji": (todo.get("item_emojis") or {}).get(model.item_key(name)),
                    "skip": model.item_key(name) in (todo.get("item_skip") or []),
                }
            )
        return rows

    def _state_name(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id

    def _tv_name(self, entry_id: str | None) -> str | None:
        if not entry_id:
            return None
        entry = self.hass.config_entries.async_get_entry(entry_id)
        return entry.title if entry else None


def manager_of(hass: HomeAssistant) -> FamilyManager | None:
    """The loaded Family entry's manager (there's only ever one entry)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (manager := getattr(entry, "runtime_data", None)) is not None:
            return manager
    return None


def _season(raw: dict[str, Any]) -> dict[str, str | None]:
    """A chore's season: both days, or neither (all year)."""
    start = model.clean_month_day(raw.get("from_date"), "Season starts")
    end = model.clean_month_day(raw.get("until_date"), "Season ends")
    if bool(start) != bool(end):
        raise FamilyError("Give both the first and last day of the season, or neither")
    return {"from_date": start, "until_date": end}


def _item_members(todo: dict[str, Any], name: str) -> list[str]:
    """Who a to-do item is for: its own people, else the list's."""
    own = (todo.get("item_members") or {}).get(model.item_key(name))
    return list(own or todo.get("members") or [])


def _local_due(due: Any) -> date | datetime | None:
    """A to-do item's due date (all day) or time, in local time."""
    if not due:
        return None
    text = str(due)
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        return dt_util.as_local(datetime.fromisoformat(text))
    except ValueError:
        return None
