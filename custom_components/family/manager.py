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
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import model
from .calendar_today import DAYS as CALENDAR_DAYS, CalendarToday, clean_calendars
from .const import (
    DOMAIN,
    EVENT_BONUS,
    EVENT_CHORE_DONE,
    EVENT_CHORE_REVIEWED,
    EVENT_REWARD_REDEEMED,
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
from .parents_notify import ParentNotices
from .todo_sync import TodoSync

_LOGGER = logging.getLogger(__name__)
SAVE_DELAY = 2
TODO_PREFIX = "todo:"


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
        self._seen_chores: tuple | None = None
        self._member_listeners: list[Callable[[], None]] = []

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
        # Streaks count days with all of one's own chores done from this day;
        # before it, any chore, as they used to.
        if "streak_rule_from" not in self.settings:
            self.settings["streak_rule_from"] = dt_util.now().date().isoformat()
            self.save()
        self._prune()
        self._prune_board()
        self.async_auto_check()
        self._watch_todo_lists()
        await self.async_refresh_todo()
        self.calendar.watch()
        await self.calendar.async_refresh()
        self.async_allowance()

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
        }

    @callback
    def _changed(self, members: bool = False) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)
        async_dispatcher_send(self.hass, SIGNAL_CHANGED)
        # A chore done, back, renamed or removed: its to-do item follows.
        self.todo_sync.schedule()
        if members:
            for listener in list(self._member_listeners):
                listener()

    @callback
    def save(self) -> None:
        """Save without telling the dashboards (nothing they show changed)."""
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

    @callback
    def async_tick(self, _now: Any = None) -> None:
        """Every minute: tell the dashboards when a chore's hours start or end,
        or a new day or week brings someone else's turn."""
        if not any(
            c.get("days") or c.get("from_time") or c.get("until_time") or c.get("turns")
            for c in self.chores
        ) and not any(t.get("due_only") for t in self.todo_lists):
            return
        seen = tuple((c["id"], c.get("turn")) for c in self.chores_for(None))
        if seen != self._seen_chores:
            self._seen_chores = seen
            async_dispatcher_send(self.hass, SIGNAL_CHANGED)
            self.todo_sync.schedule()

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
        self.calendar.stop()
        if self._unsub_todo:
            self._unsub_todo()
            self._unsub_todo = None
        await self._store.async_save(self._data())

    def _prune(self) -> None:
        """Fold entries older than KEEP_HISTORY_DAYS into the balances."""
        cutoff = dt_util.now() - timedelta(days=KEEP_HISTORY_DAYS)
        keep = []
        for entry in self.entries:
            if dt_util.parse_datetime(entry["at"]) >= cutoff:
                keep.append(entry)
            elif entry.get("review") != model.REVIEW_REJECTED:
                member = entry["member"]
                self.carried[member] = self.carried.get(member, 0) + int(
                    entry.get("points", 0)
                )
        self.entries = keep

    def _prune_board(self) -> bool:
        """Drop notes past their last day, and meals older than a week."""
        today = dt_util.now().date()
        oldest = (today - timedelta(days=model.KEEP_MEAL_DAYS)).isoformat()
        notes = [n for n in self.notes if model.note_current(n, today)]
        meals = {d: m for d, m in self.meals.items() if d >= oldest and m}
        changed = len(notes) != len(self.notes) or len(meals) != len(self.meals)
        self.notes, self.meals = notes, meals
        return changed

    # ---- allowance ------------------------------------------------------------

    @callback
    def async_allowance(self, _now: Any = None) -> None:
        """Give each member their weekly allowance, once a week (hourly check)."""
        if self._prune_board():
            self._changed()
        if not any(int(m.get("allowance") or 0) for m in self.members):
            return
        now = dt_util.now()
        key = model.allowance_due(
            now,
            int(self.settings.get("allowance_day", model.DEFAULT_ALLOWANCE_DAY)),
            int(self.settings.get("allowance_hour", model.DEFAULT_ALLOWANCE_HOUR)),
            self.settings.get("allowance_week"),
        )
        if key is None:
            return
        for member in self.members:
            points = int(member.get("allowance") or 0)
            if points <= 0:
                continue
            self.entries.append(
                {
                    "id": _id(),
                    "at": now.isoformat(),
                    "kind": model.KIND_ALLOWANCE,
                    "member": member["id"],
                    "title": "Weekly allowance",
                    "points": points,
                }
            )
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
        return self.carried.get(member_id, 0) + model.balance(self.entries, member_id)

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
        chores = [self._effective(c, now) for c in self.chores]
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
                chores.append(
                    {
                        "id": f"{TODO_PREFIX}{entity_id}:{item['uid']}",
                        "name": name,
                        "points": points,
                        "members": _item_members(todo, name),
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
            return dict(chore, source="family", grab=model.is_grab(chore))
        return dict(
            chore,
            source="family",
            grab=False,
            rotation=list(chore.get("members") or []),
            members=[turn],
            turn=turn,
        )

    def chore(self, chore_id: str) -> dict[str, Any]:
        for chore in self.all_chores():
            if chore["id"] == chore_id:
                return chore
        raise FamilyError("That chore isn't on the list any more")

    def chores_for(self, member_id: str | None) -> list[dict[str, Any]]:
        """Chores with who can still do each now."""
        now = dt_util.now()
        result = []
        for chore in self.all_chores():
            if not chore.get("enabled", True) or not model.available(chore, now):
                continue
            done = self._done(chore, now)
            can = [m["id"] for m in self.members if model.can_do(m["id"], chore, done)]
            if member_id is not None and member_id not in can:
                continue
            if not can:
                continue
            result.append({**chore, "can": can})
        return result

    def _done(self, chore: dict[str, Any], now) -> set[str]:
        """Who has done it. A to-do item is open until it's done, so the list
        alone decides; a recurring reminder that comes back can be done again."""
        if chore.get("source") == "todo":
            return set()
        return model.done_by(chore, self.entries, now)

    async def async_complete(self, member_id: str, chore_id: str) -> dict[str, Any]:
        """A member did a chore: points straight away, a parent checks later."""
        member = self.member(member_id)
        chore = self.chore(chore_id)
        now = dt_util.now()
        if not model.available(chore, now):
            raise FamilyError(f"{chore['name']} isn't for right now")
        done = self._done(chore, now)
        if not model.can_do(member_id, chore, done):
            raise FamilyError(
                f"{chore['name']} is already done or isn't {member['name']}'s"
            )
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": model.KIND_CHORE,
            "member": member_id,
            "title": chore["name"],
            "points": int(chore.get("points", 0)),
            "chore_id": chore_id,
            "review": model.REVIEW_PENDING,
            # The chore's own penalty if it has one; None: the family's.
            "penalty": chore.get("penalty"),
        }
        self.entries.append(entry)
        if chore.get("source") == "todo":
            await self._async_set_todo(chore["todo_entity"], chore["todo_uid"], True)
        bonuses = self._earn_bonuses(member, entry)
        self._changed()
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
        return entry

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
            for e in model.chores_done_on(self.entries, now.date(), member_id)
            if e.get("review") != model.REVIEW_REJECTED
        }
        return [
            c
            for c in own
            if c["id"] != just_done
            and c["id"] not in did
            and model.can_do(member_id, c, self._done(c, now))
        ]

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

    def _has_own(self, member_id: str) -> Callable[[date], bool]:
        """Whether a day had any of this member's own dashboard chores (one
        taken in turns isn't counted: whose turn it was isn't kept)."""

        def has_own(day: date) -> bool:
            return any(
                model.is_own(c, member_id)
                and not c.get("turns")
                and model.on_day(c, day)
                for c in self.chores
            )

        return has_own

    def streak(self, member_id: str, done_today: bool = False) -> int:
        """Days in a row this member did all of their own chores."""
        since = self.settings.get("streak_rule_from")
        return model.streak(
            self.entries,
            member_id,
            dt_util.now().date(),
            self._has_own(member_id),
            date.fromisoformat(since) if since else None,
            done_today,
        )

    async def async_review(
        self, entry_id: str, approved: bool, penalty: int | None = None
    ) -> dict[str, Any]:
        """A parent checked a chore. Not done: its points are taken back, and
        a penalty on top (``penalty``, else the chore's, else the family's)."""
        entry = self._entry(entry_id)
        if entry.get("kind") != model.KIND_CHORE:
            raise FamilyError("Only chores are checked")
        entry.pop("auto", None)  # a parent checked it now
        entry["review"] = model.REVIEW_APPROVED if approved else model.REVIEW_REJECTED
        entry["reviewed_at"] = _now_iso()
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

    @callback
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
        if "notify_targets" in raw:
            targets = [str(t) for t in raw.get("notify_targets") or [] if t]
            unknown = [
                t for t in targets if not self.hass.services.has_service("notify", t)
            ]
            if unknown:
                raise FamilyError(f"There's no notify action called {unknown[0]}")
            self.settings["notify_targets"] = list(dict.fromkeys(targets))
        for key in ("notify_done", "notify_rewards", "weekly_summary"):
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
        if "calendars" in raw:
            self.settings["calendars"] = clean_calendars(
                raw.get("calendars"), {m["id"] for m in self.members}
            )
            self.calendar.watch()
            self.calendar.schedule()
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
        cost = int(reward.get("points", 0))
        if self.points(member_id) < cost:
            raise FamilyError(
                f"{member['name']} needs {cost} points for {reward['name']}"
            )
        if member_id in model.reward_used_by(reward, self.entries, dt_util.now()):
            when = "today" if reward.get("limit") == model.REPEAT_DAILY else "this week"
            raise FamilyError(f"{member['name']} already had {reward['name']} {when}")
        tv: dict[str, Any] = {}
        kind = reward.get("kind")
        if kind == model.REWARD_TV_TIME:
            await self._async_give_tv_time(reward, member)
            tv = {
                "tv": reward["tv"],
                "minutes": int(reward.get("minutes", 0)),
                "whole_home": bool(reward.get("whole_home", False)),
            }
        elif kind == model.REWARD_MUSIC_TIME:
            await self._async_give_music_time(reward, member)
            tv = {
                "speaker": reward["speaker"],
                "minutes": int(reward.get("minutes", 0)),
                "whole_home": bool(reward.get("whole_home", False)),
            }
        given_now = kind in (model.REWARD_TV_TIME, model.REWARD_MUSIC_TIME)
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
        if member.get("goal") == reward_id:
            member["goal"] = None  # saved up and spent: the goal's done
        self._changed()
        if not given_now:
            self.notices.reward_to_give(entry, member)
        self.hass.bus.async_fire(
            EVENT_REWARD_REDEEMED,
            self._redeemed_event(
                member["name"], member_id, reward, cost, self.points(member_id)
            ),
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
        for member in members:
            self._require_eligible(member, reward)
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
    def mark_given(self, entry_id: str) -> dict[str, Any]:
        entry = self._entry(entry_id)
        # Bought together: the whole group's handed out.
        for each in self._group(entry["group"]) if entry.get("group") else [entry]:
            each["given"] = model.GIVEN_DONE
            each["given_at"] = _now_iso()
        self._changed()
        self.notices.clear(entry_id)
        return entry

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
    def adjust(self, member_id: str, points: int, reason: str | None) -> dict[str, Any]:
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
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
            # Points added every week (0: none).
            "allowance": model.clean_points(raw.get("allowance") or 0, "Allowance"),
            # Chosen on the Family dashboard, not here: kept as it is.
            "goal": next(
                (m.get("goal") for m in self.members if m["id"] == member_id), None
            ),
        }
        new = self._upsert(self.members, member)
        self._changed(members=new)
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
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
            # Also kept on this to-do list; None: not on any list.
            "todo_list": todo_list,
            # Extra points taken if it didn't happen; None: the family's.
            "penalty": model.optional_points(raw.get("penalty"), "The penalty"),
            # Only on these weekdays (Monday 0), and between these hours.
            "days": model.clean_days(raw.get("days")),
            "from_time": model.clean_time(raw.get("from_time"), "From"),
            "until_time": model.clean_time(raw.get("until_time"), "Until"),
            # Its people take turns: turn_first's turn from now on.
            "turns": turns,
            "turn_every": turn_every if turns else None,
            "turn_first": turn_first if turns else None,
            "turn_from": _now_iso() if turns else None,
        }
        self._upsert(self.chores, chore)
        self._changed()
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
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
            # Each person at most once a day or a week; None: any time.
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
        todo = {
            "id": entity_id,
            "entity_id": entity_id,
            "points": model.clean_points(raw.get("points", 0)),
            "members": self._known_members(raw.get("members")),
            # Its items are up for grabs for its people, not their own chores.
            "grab": bool(raw.get("grab")),
            "item_points": rated,
            "item_members": assigned,
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
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
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
        }[collection]

    async def async_delete(self, collection: str, item_id: str) -> None:
        items = self._collection(collection)
        items[:] = [i for i in items if i["id"] != item_id]
        if collection == "members":
            for chore in [*self.chores, *self.todo_lists, *self.controls]:
                chore["members"] = [m for m in chore.get("members", []) if m != item_id]
            # Drop them from rewards they were picked for. An empty list stays
            # empty: the reward is unavailable, it does not become everyone's.
            # A reward for everyone (None) is left as it is.
            for reward in self.rewards:
                picked = reward.get("members")
                if picked:
                    reward["members"] = [m for m in picked if m != item_id]
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
            await self.async_refresh_todo(event.data["entity_id"])
            async_dispatcher_send(self.hass, SIGNAL_CHANGED)

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

    def snapshot(self, user_id: str | None, is_admin: bool) -> dict[str, Any]:
        today = dt_util.now().date()
        members = [
            {
                **m,
                "points": self.points(m["id"]),
                "streak": self.streak(m["id"]),
                # Their own chores today (not ones up for grabs): how many,
                # how many are left, and whether they finished them all.
                "own_today": dict(
                    zip(("total", "left"), self._own_today(m["id"]), strict=True),
                    done=model.bonus_given(
                        self.entries, m["id"], model.BONUS_ALL_DONE, today
                    ),
                    # Left, but their hours are over for today.
                    missed=self._own_missed(m["id"]),
                ),
                "done_today": len(model.chores_done_on(self.entries, today, m["id"])),
                "picture": self.picture(m),
                "to_check": sum(
                    1
                    for e in self.entries
                    if e["member"] == m["id"]
                    and e.get("review") == model.REVIEW_PENDING
                ),
            }
            for m in self.members
        ]
        now = dt_util.now()
        rewards = [
            {
                **r,
                "tv_name": self._tv_name(r.get("tv")),
                "speaker_name": self._tv_name(r.get("speaker")),
                "used_by": sorted(model.reward_used_by(r, self.entries, now)),
            }
            for r in self.rewards
        ]
        recent = sorted(self.entries, key=lambda e: e["at"], reverse=True)[:30]
        controls = [
            {
                **c,
                "label": self._control_name(c),
                "kind": model.control_kind(c["entity_id"]),
            }
            for c in self.controls
        ]
        result: dict[str, Any] = {
            "members": members,
            "chores": self.chores_for(None),
            "rewards": rewards,
            "controls": controls,
            "done_today": sorted(
                model.chores_done_on(self.entries, today),
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
            "me": self.member_for_user(user_id),
            "is_admin": is_admin,
            "undo_seconds": model.UNDO_SECONDS,
        }
        if is_admin:
            result["settings"] = {
                "auto_check": self.settings.get("auto_check"),
                "penalty": int(self.settings.get("penalty") or 0),
                "notify_targets": list(self.settings.get("notify_targets") or []),
                "notify_done": bool(self.settings.get("notify_done")),
                "notify_rewards": bool(self.settings.get("notify_rewards")),
                "weekly_summary": bool(self.settings.get("weekly_summary")),
                "allowance_day": int(
                    self.settings.get("allowance_day", model.DEFAULT_ALLOWANCE_DAY)
                ),
                "allowance_hour": int(
                    self.settings.get("allowance_hour", model.DEFAULT_ALLOWANCE_HOUR)
                ),
                "point_value": self.settings.get("point_value"),
                "currency": self.settings.get("currency") or "",
                "calendars": list(self.settings.get("calendars") or []),
            }
            result["all_chores"] = self.chores
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
            result["history"] = sorted(
                self.entries, key=lambda e: e["at"], reverse=True
            )[:200]
        return result

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
