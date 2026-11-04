"""The dashboards' API.

Everyone (the shared screen included) can see chores and rewards, mark a
chore done, spend points and use the home controls a parent put on the
dashboard (only those): the Family dashboard runs on a shared display that
kids tap. Checking chores, editing the lists and changing points are
for admins (the Parents dashboard).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import model
from .const import DOMAIN, SIGNAL_CHANGED, TV_MGMT_DOMAIN
from .manager import FamilyError, FamilyManager, manager_of

COLLECTIONS = ("members", "chores", "rewards", "todo_lists", "controls")


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    for command in (
        ws_state,
        ws_subscribe,
        ws_complete,
        ws_redeem,
        ws_control,
        ws_undo,
        ws_review,
        ws_given,
        ws_adjust,
        ws_save,
        ws_delete,
        ws_move,
        ws_settings,
        ws_choices,
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


# ---- everyone ------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/state"})
@websocket_api.async_response
@_handler
async def ws_state(hass, connection, msg, manager) -> dict[str, Any]:
    return manager.snapshot(*_user(connection))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
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
        vol.Required("type"): f"{DOMAIN}/complete",
        vol.Required("member_id"): str,
        vol.Required("chore_id"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_complete(hass, connection, msg, manager) -> dict[str, Any]:
    entry = await manager.async_complete(msg["member_id"], msg["chore_id"])
    return {"entry": entry, "points": manager.points(msg["member_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/redeem",
        vol.Required("member_id"): str,
        vol.Required("reward_id"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_redeem(hass, connection, msg, manager) -> dict[str, Any]:
    entry = await manager.async_redeem(msg["member_id"], msg["reward_id"])
    return {"entry": entry, "points": manager.points(msg["member_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/control",
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
    {vol.Required("type"): f"{DOMAIN}/undo", vol.Required("entry_id"): str}
)
@websocket_api.async_response
@_handler
async def ws_undo(hass, connection, msg, manager) -> dict[str, Any]:
    """Undo a chore or reward tapped by mistake, within a minute."""
    await manager.async_undo(msg["entry_id"])
    return {}


# ---- parents (admins) ----------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/review",
        vol.Required("entry_id"): str,
        vol.Required("approved"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_review(hass, connection, msg, manager) -> dict[str, Any]:
    return {"entry": await manager.async_review(msg["entry_id"], msg["approved"])}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/given", vol.Required("entry_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_given(hass, connection, msg, manager) -> dict[str, Any]:
    return {"entry": manager.mark_given(msg["entry_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/adjust",
        vol.Required("member_id"): str,
        vol.Required("points"): int,
        vol.Optional("reason"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_adjust(hass, connection, msg, manager) -> dict[str, Any]:
    entry = manager.adjust(msg["member_id"], msg["points"], msg.get("reason"))
    return {"entry": entry, "points": manager.points(msg["member_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/save",
        vol.Required("collection"): vol.In(COLLECTIONS),
        vol.Required("item"): dict,
    }
)
@websocket_api.require_admin
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
    else:
        saved = await manager.async_save_todo_list(item)
    return {"item": saved}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/delete",
        vol.Required("collection"): vol.In(COLLECTIONS),
        # Not "id": that's the websocket message's own id.
        vol.Required("item_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_delete(hass, connection, msg, manager) -> dict[str, Any]:
    await manager.async_delete(msg["collection"], msg["item_id"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/move",
        vol.Required("collection"): vol.In(COLLECTIONS),
        vol.Required("item_id"): str,
        vol.Required("offset"): vol.In((-1, 1)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_move(hass, connection, msg, manager) -> dict[str, Any]:
    manager.move(msg["collection"], msg["item_id"], msg["offset"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/settings",
        vol.Optional("auto_check"): vol.Any(None, str),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_settings(hass, connection, msg, manager) -> dict[str, Any]:
    return {"settings": manager.save_settings(msg)}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/choices"})
@websocket_api.require_admin
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
        "entities": entities,
    }
