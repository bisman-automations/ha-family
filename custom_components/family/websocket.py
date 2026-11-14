"""The dashboards' API.

Everyone (the shared screen included) can see chores and rewards, mark a
chore done, spend points and use the home controls a parent put on the
dashboard (only those): the Family dashboard runs on a shared display that
kids tap. Checking chores, editing the lists and changing points are for
parents: an admin login, or a login holding a pass from the parent PIN
(``parent_pass.py``), sent as ``pass`` with each command. Setting the PIN
itself is for admins only.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import model
from .const import DOMAIN, MEDIA_MGMT_DOMAIN, SIGNAL_CHANGED, TV_MGMT_DOMAIN
from .manager import FamilyError, FamilyManager, manager_of
from .parent_pass import PIN_KEY, PINS_KEY
from .parents_notify import target_name

PIN_KEYS = (PIN_KEY, PINS_KEY)

# The parent pass, sent with any command (only parent commands use it).
PASS = "pass"

COLLECTIONS = ("members", "chores", "rewards", "todo_lists", "controls", "routines")


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    for command in (
        ws_state,
        ws_subscribe,
        ws_complete,
        ws_routine_step,
        ws_redeem,
        ws_control,
        ws_undo,
        ws_goal,
        ws_note_add,
        ws_note_remove,
        ws_review,
        ws_meals,
        ws_given,
        ws_approve,
        ws_adjust,
        ws_save,
        ws_delete,
        ws_move,
        ws_settings,
        ws_choices,
        ws_unlock,
        ws_lock,
        ws_pin,
        ws_trade_offer,
        ws_trade_take,
        ws_trade_cancel,
        ws_trade_decide,
        ws_cash_out,
        ws_cash_out_cancel,
    ):
        websocket_api.async_register_command(hass, command)


def _handler(
    func: Callable[
        [HomeAssistant, websocket_api.ActiveConnection, dict, FamilyManager],
        Coroutine[Any, Any, Any],
    ],
):
    """Find the manager, run the command, and turn FamilyError into a message."""

    @wraps(func)
    async def wrapper(hass, connection, msg) -> None:
        manager = manager_of(hass)
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Family isn't set up")
            return
        try:
            result = await func(hass, connection, msg, manager)
        except FamilyError as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        except ValueError as err:
            connection.send_error(msg["id"], "invalid_format", str(err))
            return
        connection.send_result(msg["id"], result)

    return wrapper


def _user(connection) -> tuple[str | None, bool]:
    user = connection.user
    return (user.id if user else None, bool(user and user.is_admin))


def _is_parent(hass: HomeAssistant, connection, msg: dict) -> bool:
    """An admin login, or a live parent pass for this login."""
    user = connection.user
    if user and user.is_admin:
        return True
    manager = manager_of(hass)
    return bool(
        manager and manager.passes.valid(msg.get(PASS), user.id if user else None)
    )


def _require_parent(func):
    """Like require_admin, but a parent pass from the PIN counts too."""

    @wraps(func)
    def wrapper(hass, connection, msg):
        if not _is_parent(hass, connection, msg):
            raise Unauthorized
        return func(hass, connection, msg)

    return wrapper


# ---- everyone ------------------------------------------------------------------------


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/state", vol.Optional(PASS): str}
)
@websocket_api.async_response
@_handler
async def ws_state(hass, connection, msg, manager) -> dict[str, Any]:
    user_id, is_admin = _user(connection)
    return manager.snapshot(user_id, is_admin, _is_parent(hass, connection, msg))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/unlock",
        vol.Optional(PASS): str,
        vol.Required("pin"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_unlock(hass, connection, msg, manager) -> dict[str, Any]:
    """Swap the parent PIN for a pass (open to everyone: it's the PIN pad)."""
    return await manager.passes.unlock(msg["pin"], _user(connection)[0])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/lock", vol.Optional(PASS): str}
)
@websocket_api.async_response
@_handler
async def ws_lock(hass, connection, msg, manager) -> dict[str, Any]:
    """End a pass: Back to Family, or the screen went idle."""
    manager.passes.lock(msg.get(PASS))
    return {}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/subscribe", vol.Optional(PASS): str}
)
@callback
def ws_subscribe(hass: HomeAssistant, connection, msg) -> None:
    """Tell the dashboard when anything changes, so it reloads."""

    @callback
    def changed() -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"changed": True})
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_CHANGED, changed
    )
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/routine/step",
        vol.Optional(PASS): str,
        vol.Required("routine_id"): str,
        vol.Required("member_id"): str,
        vol.Required("step"): int,
        vol.Required("done"): bool,
    }
)
@websocket_api.async_response
@_handler
async def ws_routine_step(hass, connection, msg, manager) -> dict[str, Any]:
    """Tick a routine's step: open to everyone, like ticking off a chore."""
    return await manager.routines.async_step(
        msg["routine_id"], msg["member_id"], msg["step"], msg["done"]
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/complete",
        vol.Optional(PASS): str,
        vol.Required("member_id"): str,
        vol.Required("chore_id"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_complete(hass, connection, msg, manager) -> dict[str, Any]:
    entry = await manager.async_complete(msg["member_id"], msg["chore_id"])
    return {
        "entry": entry,
        "points": manager.points(msg["member_id"]),
        "badges": manager.take_new_badges(msg["member_id"]),
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/redeem",
        vol.Optional(PASS): str,
        vol.Required("member_id"): str,
        vol.Required("reward_id"): str,
        # Others sharing the points; a parent says yes first.
        vol.Optional("together"): [str],
    }
)
@websocket_api.async_response
@_handler
async def ws_redeem(hass, connection, msg, manager) -> dict[str, Any]:
    entry = await manager.async_redeem(
        msg["member_id"], msg["reward_id"], msg.get("together")
    )
    return {
        "entry": entry,
        "points": manager.points(msg["member_id"]),
        "badges": manager.take_new_badges(msg["member_id"]),
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/control",
        vol.Optional(PASS): str,
        vol.Required("control_id"): str,
        vol.Required("action"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_control(hass, connection, msg, manager) -> dict[str, Any]:
    await manager.async_control(
        msg["control_id"], msg["action"], connection.context(msg)
    )
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/undo",
        vol.Optional(PASS): str,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_undo(hass, connection, msg, manager) -> dict[str, Any]:
    """Undo a chore or reward tapped by mistake, within a minute."""
    await manager.async_undo(msg["entry_id"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/goal",
        vol.Optional(PASS): str,
        vol.Required("member_id"): str,
        vol.Required("reward_id"): vol.Any(None, str),
    }
)
@websocket_api.async_response
@_handler
async def ws_goal(hass, connection, msg, manager) -> dict[str, Any]:
    """The reward someone is saving for (None: not saving for one)."""
    return {"member": manager.set_goal(msg["member_id"], msg["reward_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/note/add",
        vol.Optional(PASS): str,
        vol.Required("text"): str,
        vol.Optional("member_id"): vol.Any(None, str),
        vol.Optional("until"): vol.Any(None, str),
    }
)
@websocket_api.async_response
@_handler
async def ws_note_add(hass, connection, msg, manager) -> dict[str, Any]:
    """Put a note on the board (anyone, the shared screen too)."""
    user = connection.user
    return {
        "note": manager.add_note(
            msg["text"],
            msg.get("member_id"),
            msg.get("until"),
            by_admin=bool(user and user.is_admin),
            by=user.name if user else None,
        )
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/note/remove",
        vol.Optional(PASS): str,
        vol.Required("note_id"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_note_remove(hass, connection, msg, manager) -> dict[str, Any]:
    """Take a note down. A parent's note only by a parent."""
    manager.remove_note(msg["note_id"], by_admin=_user(connection)[1])
    return {}


# ---- parents (admins, or the parent PIN) ----------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/review",
        vol.Optional(PASS): str,
        vol.Required("entry_id"): str,
        vol.Required("approved"): bool,
        # Points taken on top when it didn't happen; leave out for the default.
        vol.Optional("penalty"): vol.Any(
            None, vol.All(int, vol.Range(min=0, max=10000))
        ),
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_review(hass, connection, msg, manager) -> dict[str, Any]:
    return {
        "entry": await manager.async_review(
            msg["entry_id"], msg["approved"], msg.get("penalty")
        )
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/given",
        vol.Optional(PASS): str,
        vol.Required("entry_id"): str,
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_given(hass, connection, msg, manager) -> dict[str, Any]:
    return {"entry": manager.mark_given(msg["entry_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/approve",
        vol.Optional(PASS): str,
        vol.Required("group_id"): str,
        vol.Required("approved"): bool,
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_approve(hass, connection, msg, manager) -> dict[str, Any]:
    await manager.async_approve(msg["group_id"], msg["approved"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/adjust",
        vol.Optional(PASS): str,
        vol.Required("member_id"): str,
        vol.Required("points"): int,
        vol.Optional("reason"): str,
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_adjust(hass, connection, msg, manager) -> dict[str, Any]:
    entry = manager.adjust(msg["member_id"], msg["points"], msg.get("reason"))
    return {"entry": entry, "points": manager.points(msg["member_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/save",
        vol.Optional(PASS): str,
        vol.Required("collection"): vol.In(COLLECTIONS),
        vol.Required("item"): dict,
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_save(hass, connection, msg, manager) -> dict[str, Any]:
    item = msg["item"]
    collection = msg["collection"]
    if collection == "members":
        saved = manager.save_member(item)
    elif collection == "chores":
        saved = manager.save_chore(item)
    elif collection == "rewards":
        saved = manager.save_reward(item)
    elif collection == "controls":
        saved = manager.save_control(item)
    elif collection == "routines":
        saved = manager.routines.save(item)
        manager.changed()
    else:
        saved = await manager.async_save_todo_list(item)
    return {"item": saved}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/delete",
        vol.Optional(PASS): str,
        vol.Required("collection"): vol.In(COLLECTIONS),
        # Not "id": that's the websocket message's own id.
        vol.Required("item_id"): str,
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_delete(hass, connection, msg, manager) -> dict[str, Any]:
    await manager.async_delete(msg["collection"], msg["item_id"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/move",
        vol.Optional(PASS): str,
        vol.Required("collection"): vol.In(COLLECTIONS),
        vol.Required("item_id"): str,
        vol.Required("offset"): vol.In((-1, 1)),
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_move(hass, connection, msg, manager) -> dict[str, Any]:
    manager.move(msg["collection"], msg["item_id"], msg["offset"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/settings",
        vol.Optional(PASS): str,
        vol.Optional("auto_check"): vol.Any(None, str),
        vol.Optional("bonus_all_done"): vol.Any(None, int),
        vol.Optional("streak_days"): vol.Any(None, int),
        vol.Optional("streak_bonus"): vol.Any(None, int),
        vol.Optional("penalty"): vol.Any(None, int),
        vol.Optional("notify_targets"): [str],
        vol.Optional("notify_done"): bool,
        vol.Optional("notify_rewards"): bool,
        vol.Optional("weekly_summary"): bool,
        vol.Optional("live_activity"): bool,
        vol.Optional("live_per_child"): bool,
        vol.Optional("live_from"): vol.Any(None, str),
        vol.Optional("allowance_day"): vol.All(int, vol.Range(min=0, max=6)),
        vol.Optional("allowance_hour"): vol.All(int, vol.Range(min=0, max=23)),
        vol.Optional("point_value"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("currency"): vol.Any(None, str),
        vol.Optional("section_order"): [str],
        vol.Optional("hide_empty_sections"): bool,
        vol.Optional("family_goal"): vol.Any(
            None,
            {
                vol.Required("name"): str,
                vol.Optional("emoji"): vol.Any(None, str),
                vol.Required("target"): vol.Coerce(int),
            },
        ),
        vol.Optional("restart_goal"): bool,
        vol.Optional("reminder_tts"): vol.Any(None, str),
        vol.Optional("quick_points"): [
            {
                vol.Required("label"): str,
                vol.Optional("emoji"): vol.Any(None, str),
                vol.Required("points"): vol.Coerce(int),
                vol.Optional("members"): vol.Any(None, [str]),
            }
        ],
        vol.Optional("calendars"): [
            {vol.Required("entity_id"): str, vol.Optional("member"): vol.Any(None, str)}
        ],
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_settings(hass, connection, msg, manager) -> dict[str, Any]:
    settings = manager.save_settings(msg)
    # The PINs' hashes stay in Home Assistant.
    return {"settings": {k: v for k, v in settings.items() if k not in PIN_KEYS}}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/meals",
        vol.Optional(PASS): str,
        vol.Required("date"): str,
        **{vol.Optional(meal): vol.Any(None, str) for meal in model.MEALS},
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_meals(hass, connection, msg, manager) -> dict[str, Any]:
    """A day's meals (empty clears them)."""
    return {"meals": manager.save_meals(msg["date"], msg)}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/choices", vol.Optional(PASS): str}
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_choices(hass, connection, msg, manager) -> dict[str, Any]:
    """What the Parents dashboard can pick from: people, to-do lists, TVs, entities."""
    people = [
        {"entity_id": s.entity_id, "name": s.name}
        for s in sorted(hass.states.async_all("person"), key=lambda s: s.name)
    ]
    todo_lists = [
        {"entity_id": s.entity_id, "name": s.name}
        for s in sorted(hass.states.async_all("todo"), key=lambda s: s.name)
    ]
    tvs = [
        {"id": e.entry_id, "name": e.title}
        for e in hass.config_entries.async_entries(TV_MGMT_DOMAIN)
        if not e.disabled_by
    ]
    speakers = [
        {"id": e.entry_id, "name": e.title}
        for e in hass.config_entries.async_entries(MEDIA_MGMT_DOMAIN)
        if not e.disabled_by
    ]
    # Phones first (the Companion app's notify actions), then the rest.
    notify = sorted(
        (
            {"service": name, "name": target_name(name)}
            for name in hass.services.async_services_for_domain("notify")
            if name not in ("send_message", "persistent_notification")
        ),
        key=lambda t: (not t["service"].startswith("mobile_app_"), t["name"]),
    )
    calendars = [
        {"entity_id": s.entity_id, "name": s.name}
        for s in sorted(hass.states.async_all("calendar"), key=lambda s: s.name)
    ]
    voices = [
        {"entity_id": s.entity_id, "name": s.name}
        for s in sorted(hass.states.async_all("tts"), key=lambda s: s.name)
    ]
    players = [
        {"entity_id": s.entity_id, "name": s.name}
        for s in sorted(hass.states.async_all("media_player"), key=lambda s: s.name)
    ]
    entities = [
        {"entity_id": s.entity_id, "name": s.name, "domain": s.domain}
        for s in sorted(
            hass.states.async_all(model.CONTROL_DOMAINS),
            key=lambda s: (s.domain, s.name.casefold()),
        )
    ]
    return {
        "people": people,
        "todo_lists": todo_lists,
        "tvs": tvs,
        "speakers": speakers,
        "notify": notify,
        "entities": entities,
        "calendars": calendars,
        "voices": voices,
        "players": players,
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/pin",
        vol.Optional(PASS): str,
        vol.Required("pin"): vol.Any(None, str),
        # True: your own PIN; false (the default): the family PIN.
        vol.Optional("own", default=False): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_pin(hass, connection, msg, manager) -> dict[str, Any]:
    """Set or clear the family PIN, or your own (admins only, not with a pass)."""
    user = connection.user
    user_id = user.id if user else None
    if msg["own"]:
        manager.passes.set_pin(msg["pin"], user_id, user.name if user else None)
    else:
        manager.passes.set_pin(msg["pin"])
    return {"pin_set": manager.passes.pin_set, **manager.passes.status(user_id)}


# ---- trading chores and cashing out (everyone asks, a parent says yes) ------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/trade/offer",
        vol.Optional(PASS): str,
        vol.Required("member_id"): str,
        vol.Required("chore_id"): str,
        vol.Optional("to"): vol.Any(None, str),
    }
)
@websocket_api.async_response
@_handler
async def ws_trade_offer(hass, connection, msg, manager) -> dict[str, Any]:
    """Offer one of your own chores today to someone else (or anyone)."""
    return {
        "trade": manager.trades.offer(msg["member_id"], msg["chore_id"], msg.get("to"))
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/trade/take",
        vol.Optional(PASS): str,
        vol.Required("trade_id"): str,
        vol.Required("member_id"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_trade_take(hass, connection, msg, manager) -> dict[str, Any]:
    return {"trade": manager.trades.take(msg["trade_id"], msg["member_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/trade/cancel",
        vol.Optional(PASS): str,
        vol.Required("trade_id"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_trade_cancel(hass, connection, msg, manager) -> dict[str, Any]:
    manager.trades.cancel(msg["trade_id"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/trade/decide",
        vol.Optional(PASS): str,
        vol.Required("trade_id"): str,
        vol.Required("approved"): bool,
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_trade_decide(hass, connection, msg, manager) -> dict[str, Any]:
    return {"trade": manager.trades.decide(msg["trade_id"], msg["approved"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/cash_out",
        vol.Optional(PASS): str,
        vol.Required("member_id"): str,
        vol.Required("points"): vol.Coerce(int),
    }
)
@websocket_api.async_response
@_handler
async def ws_cash_out(hass, connection, msg, manager) -> dict[str, Any]:
    """Turn points into money: the points go now, a parent pays it out."""
    entry = manager.cash_out(msg["member_id"], msg["points"])
    return {
        "entry": entry,
        "points": manager.points(msg["member_id"]),
        "badges": manager.take_new_badges(msg["member_id"]),
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/cash_out/cancel",
        vol.Optional(PASS): str,
        vol.Required("entry_id"): str,
    }
)
@_require_parent
@websocket_api.async_response
@_handler
async def ws_cash_out_cancel(hass, connection, msg, manager) -> dict[str, Any]:
    manager.cancel_cash_out(msg["entry_id"])
    return {}
