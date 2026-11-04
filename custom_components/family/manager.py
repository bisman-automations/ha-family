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
from datetime import timedelta
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
from .const import (
    DOMAIN,
    EVENT_CHORE_DONE,
    EVENT_CHORE_REVIEWED,
    EVENT_REWARD_REDEEMED,
    KEEP_HISTORY_DAYS,
    MEMBER_COLORS,
    SIGNAL_CHANGED,
    STORAGE_KEY,
    STORAGE_VERSION,
    TV_MGMT_DOMAIN,
    TV_MGMT_GRANT,
)

_LOGGER = logging.getLogger(__name__)
SAVE_DELAY = 2
TODO_PREFIX = "todo:"


class FamilyError(HomeAssistantError):
    """Something the person asked for can't be done; the message says why."""


def _id() -> str:
    return uuid4().hex[:12]


def _now_iso() -> str:
    return dt_util.now().isoformat()


class FamilyManager:
    """Owns the family's data and everything that changes it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
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
        self._member_listeners: list[Callable[[], None]] = []

    # ---- storage --------------------------------------------------------------

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.members = list(data.get("members") or [])
        self.chores = list(data.get("chores") or [])
        self.rewards = list(data.get("rewards") or [])
        self.todo_lists = list(data.get("todo_lists") or [])
        self.controls = list(data.get("controls") or [])
        self.settings = dict(data.get("settings") or {})
        self.entries = list(data.get("entries") or [])
        self.carried = {k: int(v) for k, v in (data.get("carried") or {}).items()}
        self._prune()
        self.async_auto_check()
        self._watch_todo_lists()
        await self.async_refresh_todo()

    def _data(self) -> dict[str, Any]:
        return {
            "members": self.members,
            "chores": self.chores,
            "rewards": self.rewards,
            "todo_lists": self.todo_lists,
            "controls": self.controls,
            "settings": self.settings,
            "entries": self.entries,
            "carried": self.carried,
        }

    @callback
    def _changed(self, members: bool = False) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)
        async_dispatcher_send(self.hass, SIGNAL_CHANGED)
        if members:
            for listener in list(self._member_listeners):
                listener()

    @callback
    def add_member_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._member_listeners.append(listener)
        return lambda: self._member_listeners.remove(listener)

    async def async_unload(self) -> None:
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
        chores = [dict(c, source="family") for c in self.chores]
        for todo in self.todo_lists:
            entity_id = todo["entity_id"]
            state = self.hass.states.get(entity_id)
            list_name = state.name if state else entity_id
            for item in self.todo_items.get(entity_id, []):
                name, points = model.todo_points(
                    item.get("summary", ""), int(todo.get("points", 0))
                )
                chores.append(
                    {
                        "id": f"{TODO_PREFIX}{entity_id}:{item['uid']}",
                        "name": name,
                        "points": points,
                        "members": list(todo.get("members") or []),
                        # A to-do item is done once; the list decides if it comes back.
                        "repeat": model.REPEAT_ONCE,
                        "enabled": True,
                        "source": "todo",
                        "list": list_name,
                        "todo_entity": entity_id,
                        "todo_uid": item["uid"],
                    }
                )
        return chores

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
            if not chore.get("enabled", True):
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
        done = self._done(chore, dt_util.now())
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
        }
        self.entries.append(entry)
        if chore.get("source") == "todo":
            await self._async_set_todo(chore["todo_entity"], chore["todo_uid"], True)
        self._changed()
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
        return entry

    async def async_review(self, entry_id: str, approved: bool) -> dict[str, Any]:
        """A parent checked a chore. Not done: its points are taken back."""
        entry = self._entry(entry_id)
        if entry.get("kind") != model.KIND_CHORE:
            raise FamilyError("Only chores are checked")
        entry.pop("auto", None)  # a parent checked it now
        entry["review"] = model.REVIEW_APPROVED if approved else model.REVIEW_REJECTED
        entry["reviewed_at"] = _now_iso()
        chore_id = entry.get("chore_id", "")
        if chore_id.startswith(TODO_PREFIX):
            # Didn't happen: put the to-do item back on the list.
            entity_id, _, uid = chore_id.removeprefix(TODO_PREFIX).rpartition(":")
            if not approved:
                await self._async_set_todo(entity_id, uid, False)
        self._changed()
        self.hass.bus.async_fire(
            EVENT_CHORE_REVIEWED,
            {
                "member": self.member(entry["member"])["name"],
                "member_id": entry["member"],
                "chore": entry["title"],
                "approved": approved,
                "points": entry["points"],
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
        auto = raw.get("auto_check") or None
        if auto is not None and auto not in model.AUTO_CHECK:
            raise FamilyError("Pick when chores are checked automatically")
        self.settings["auto_check"] = auto
        self._changed()
        self.async_auto_check()
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
        chore_id = entry.get("chore_id", "")
        if chore_id.startswith(TODO_PREFIX):
            entity_id, _, uid = chore_id.removeprefix(TODO_PREFIX).rpartition(":")
            await self._async_set_todo(entity_id, uid, False)
        self.entries.remove(entry)
        self._changed()

    # ---- rewards --------------------------------------------------------------

    def reward(self, reward_id: str) -> dict[str, Any]:
        for reward in self.rewards:
            if reward["id"] == reward_id:
                return reward
        raise FamilyError("That reward isn't on the list any more")

    async def async_redeem(self, member_id: str, reward_id: str) -> dict[str, Any]:
        """Spend points on a reward. TV time is given straight away."""
        member = self.member(member_id)
        reward = self.reward(reward_id)
        cost = int(reward.get("points", 0))
        if self.points(member_id) < cost:
            raise FamilyError(
                f"{member['name']} needs {cost} points for {reward['name']}"
            )
        if member_id in model.reward_used_by(reward, self.entries, dt_util.now()):
            when = "today" if reward.get("limit") == model.REPEAT_DAILY else "this week"
            raise FamilyError(f"{member['name']} already had {reward['name']} {when}")
        tv: dict[str, Any] = {}
        if reward.get("kind") == model.REWARD_TV_TIME:
            await self._async_give_tv_time(reward, member)
            tv = {
                "tv": reward["tv"],
                "minutes": int(reward.get("minutes", 0)),
                "whole_home": bool(reward.get("whole_home", False)),
            }
        entry = {
            "id": _id(),
            "at": _now_iso(),
            "kind": model.KIND_REWARD,
            "member": member_id,
            "title": reward["name"],
            "points": -cost,
            "reward_id": reward_id,
            "given": model.GIVEN_DONE
            if reward.get("kind") == model.REWARD_TV_TIME
            else model.GIVEN_PENDING,
            **tv,
        }
        self.entries.append(entry)
        self._changed()
        self.hass.bus.async_fire(
            EVENT_REWARD_REDEEMED,
            {
                "member": member["name"],
                "member_id": member_id,
                "reward": reward["name"],
                "points": cost,
                "balance": self.points(member_id),
            },
        )
        return entry

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
        """Give (or take back) TV time in TV Mgmt, with why in its Activity."""
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

    @callback
    def mark_given(self, entry_id: str) -> dict[str, Any]:
        entry = self._entry(entry_id)
        entry["given"] = model.GIVEN_DONE
        entry["given_at"] = _now_iso()
        self._changed()
        return entry

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
        member = {
            "id": raw.get("id") or _id(),
            "name": model.clean_name(raw.get("name")),
            "person": raw.get("person") or None,
            "color": raw.get("color")
            or MEMBER_COLORS[len(self.members) % len(MEMBER_COLORS)],
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
        }
        new = self._upsert(self.members, member)
        self._changed(members=new)
        return member

    @callback
    def save_chore(self, raw: dict[str, Any]) -> dict[str, Any]:
        repeat = raw.get("repeat") or model.REPEAT_DAILY
        if repeat not in model.REPEATS:
            raise FamilyError("Pick how often the chore can be done")
        chore = {
            "id": raw.get("id") or _id(),
            "name": model.clean_name(raw.get("name"), "The chore's name"),
            "points": model.clean_points(raw.get("points", 0)),
            "members": self._known_members(raw.get("members")),
            "repeat": repeat,
            "enabled": bool(raw.get("enabled", True)),
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
        }
        self._upsert(self.chores, chore)
        self._changed()
        return chore

    @callback
    def save_reward(self, raw: dict[str, Any]) -> dict[str, Any]:
        kind = raw.get("kind") or model.REWARD_CUSTOM
        if kind not in model.REWARD_KINDS:
            raise FamilyError("Pick what kind of reward it is")
        reward: dict[str, Any] = {
            "id": raw.get("id") or _id(),
            "name": model.clean_name(raw.get("name"), "The reward's name"),
            "points": model.clean_points(raw.get("points", 0), "Its cost"),
            "kind": kind,
            "emoji": (raw.get("emoji") or "").strip()[:4] or None,
            # Each person at most once a day or a week; None: any time.
            "limit": raw.get("limit")
            if raw.get("limit") in model.REWARD_LIMITS
            else None,
        }
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
        self._changed()
        return reward

    async def async_save_todo_list(self, raw: dict[str, Any]) -> dict[str, Any]:
        entity_id = raw.get("entity_id") or ""
        if not entity_id.startswith("todo."):
            raise FamilyError("Pick a to-do list")
        todo = {
            "id": entity_id,
            "entity_id": entity_id,
            "points": model.clean_points(raw.get("points", 0)),
            "members": self._known_members(raw.get("members")),
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
        members = [
            {
                **m,
                "points": self.points(m["id"]),
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
            "recent": recent,
            "me": self.member_for_user(user_id),
            "is_admin": is_admin,
            "undo_seconds": model.UNDO_SECONDS,
        }
        if is_admin:
            result["settings"] = {"auto_check": self.settings.get("auto_check")}
            result["all_chores"] = self.chores
            result["todo_lists"] = [
                {**t, "name": self._state_name(t["entity_id"])} for t in self.todo_lists
            ]
            result["to_check"] = [
                e
                for e in reversed(self.entries)
                if e.get("review") == model.REVIEW_PENDING
            ]
            result["to_give"] = [
                e
                for e in reversed(self.entries)
                if e.get("given") == model.GIVEN_PENDING
            ]
            result["history"] = sorted(
                self.entries, key=lambda e: e["at"], reverse=True
            )[:200]
        return result

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
