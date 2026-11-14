"""Family inside Home Assistant: the dashboards' API, points, rewards, to-do lists."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
import voluptuous as vol

from custom_components.family.const import DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

TODO = "todo.chores"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Family", data={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


class Client:
    def __init__(self, ws) -> None:
        self.ws = ws

    async def __call__(self, type_: str, **msg: Any) -> dict[str, Any]:
        await self.ws.send_json_auto_id({"type": f"{DOMAIN}/{type_}", **msg})
        res = await self.ws.receive_json()
        while res.get("type") == "event":  # a subscription's news: not the answer
            res = await self.ws.receive_json()
        return res

    async def ok(self, type_: str, **msg: Any) -> dict[str, Any]:
        res = await self(type_, **msg)
        assert res["success"], res
        return res["result"]


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _family(client: Client) -> tuple[str, str]:
    alex = (await client.ok("save", collection="members", item={"name": "Alex"}))[
        "item"
    ]
    sam = (await client.ok("save", collection="members", item={"name": "Sam"}))["item"]
    return alex["id"], sam["id"]


async def test_chore_gives_points_then_a_parent_checks(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={
                "name": "Make your bed",
                "points": 5,
                "repeat": "daily",
                "members": [alex],
            },
        )
    )["item"]
    events = []
    hass.bus.async_listen("family_chore_done", events.append)

    state = await client.ok("state")
    assert [c["name"] for c in state["chores"]] == ["Make your bed"]
    assert state["chores"][0]["can"] == [alex]

    # Only Alex's chore.
    res = await client("complete", member_id=sam, chore_id=chore["id"])
    assert not res["success"]

    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    assert done["points"] == 5
    await hass.async_block_till_done()
    assert events[0].data["chore"] == "Make your bed"
    assert hass.states.get("sensor.family_alex_points").state == "5"

    # Done for today.
    state = await client.ok("state")
    assert state["chores"] == []
    assert state["to_check"][0]["title"] == "Make your bed"

    # It didn't happen: the points go and the chore comes back.
    await client.ok("review", entry_id=done["entry"]["id"], approved=False)
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == alex)["points"] == 0
    assert [c["name"] for c in state["chores"]] == ["Make your bed"]
    assert state["to_check"] == []


async def test_redeem_tv_time_and_other_rewards(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    tv = MockConfigEntry(domain="tv_mgmt", title="Family Room TV")
    tv.add_to_hass(hass)
    calls: list[ServiceCall] = []

    async def grant(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("tv_mgmt", "grant_extension", grant)
    await client.ok("adjust", member_id=alex, points=50, reason="Starting points")

    tv_time = (
        await client.ok(
            "save",
            collection="rewards",
            item={
                "name": "30 minutes of TV",
                "points": 20,
                "kind": "tv_time",
                "tv": tv.entry_id,
                "minutes": 30,
                "whole_home": True,
            },
        )
    )["item"]
    treat = (
        await client.ok(
            "save",
            collection="rewards",
            item={"name": "Ice cream", "points": 25, "kind": "custom"},
        )
    )["item"]

    res = await client.ok("redeem", member_id=alex, reward_id=tv_time["id"])
    assert res["points"] == 30
    assert calls[0].data == {
        "profile_id": tv.entry_id,
        "minutes": 30,
        "whole_home": True,
        "reason": "Alex's reward: 30 minutes of TV",
    }

    res = await client.ok("redeem", member_id=alex, reward_id=treat["id"])
    assert res["points"] == 5
    state = await client.ok("state")
    (to_give,) = state["to_give"]
    assert to_give["title"] == "Ice cream"
    await client.ok("given", entry_id=to_give["id"])
    assert (await client.ok("state"))["to_give"] == []

    # Not enough points left.
    res = await client("redeem", member_id=alex, reward_id=tv_time["id"])
    assert res["error"]["message"] == "Alex needs 20 points for 30 minutes of TV"


async def test_tv_time_needs_tv_mgmt(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=50)
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={
                "name": "TV",
                "points": 10,
                "kind": "tv_time",
                "tv": "gone",
                "minutes": 15,
            },
        )
    )["item"]
    res = await client("redeem", member_id=alex, reward_id=reward["id"])
    assert "TV Mgmt" in res["error"]["message"]
    # Nothing was spent.
    state = await client.ok("state")
    assert state["members"][0]["points"] == 50


async def test_chores_from_a_todo_list(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    items = [
        {"uid": "1", "summary": "Feed the dog [3]", "status": "needs_action"},
        {"uid": "2", "summary": "Take out the trash", "status": "needs_action"},
    ]
    updates: list[dict] = []

    async def get_items(call: ServiceCall):
        return {TODO: {"items": [i for i in items if i["status"] == "needs_action"]}}

    async def update_item(call: ServiceCall) -> None:
        updates.append(dict(call.data))
        for item in items:
            if item["uid"] == call.data["item"]:
                item["status"] = call.data["status"]
        hass.states.async_set(
            TODO, str(sum(i["status"] == "needs_action" for i in items))
        )

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register("todo", "update_item", update_item)
    hass.states.async_set(TODO, "2", {"friendly_name": "Chores"})

    await client.ok(
        "save", collection="todo_lists", item={"entity_id": TODO, "points": 2}
    )
    state = await client.ok("state")
    chores = {c["name"]: c for c in state["chores"]}
    assert chores["Feed the dog"]["points"] == 3
    assert chores["Take out the trash"]["points"] == 2
    assert chores["Feed the dog"]["list"] == "Chores"

    await client.ok("complete", member_id=alex, chore_id=chores["Feed the dog"]["id"])
    await hass.async_block_till_done()
    assert updates[-1]["status"] == "completed"
    state = await client.ok("state")
    assert [c["name"] for c in state["chores"]] == ["Take out the trash"]

    # Didn't happen: the item goes back on the list.
    await client.ok("review", entry_id=state["to_check"][0]["id"], approved=False)
    await hass.async_block_till_done()
    assert updates[-1]["status"] == "needs_action"
    state = await client.ok("state")
    assert sorted(c["name"] for c in state["chores"]) == [
        "Feed the dog",
        "Take out the trash",
    ]

    # Points for single items, set on the Parents dashboard.
    rows = {i["name"]: i for i in state["todo_lists"][0]["items"]}
    assert rows["Feed the dog"] == {
        "name": "Feed the dog",
        "points": 3,
        "rated": False,
        "unrated": 3,
        "members": [],
        "emoji": None,
        "skip": False,
    }
    await client.ok(
        "save",
        collection="todo_lists",
        item={
            "entity_id": TODO,
            "points": 2,
            "item_points": {"Take out the trash": 8, "Feed the dog": 5},
        },
    )
    state = await client.ok("state")
    chores = {c["name"]: c["points"] for c in state["chores"]}
    assert chores == {"Feed the dog": 5, "Take out the trash": 8}

    # Emptied: back to the points written in the item. Other items keep theirs,
    # and so does an item that comes back on the list later.
    await client.ok(
        "save",
        collection="todo_lists",
        item={"entity_id": TODO, "points": 2, "item_points": {"Feed the dog": None}},
    )
    items.append(
        {"uid": "3", "summary": "take out  the TRASH", "status": "needs_action"}
    )
    items[1]["status"] = "completed"
    hass.states.async_set(TODO, "2", {"friendly_name": "Chores"}, force_update=True)
    await hass.async_block_till_done()
    state = await client.ok("state")
    chores = {c["name"]: c["points"] for c in state["chores"]}
    assert chores == {"Feed the dog": 3, "take out  the TRASH": 8}

    # Who single items are for: their own people, else the list's.
    await client.ok(
        "save",
        collection="todo_lists",
        item={
            "entity_id": TODO,
            "points": 2,
            "members": [alex],
            "item_members": {"Take out the trash": [sam]},
            "item_emojis": {"Feed the dog": "🐶"},
        },
    )
    state = await client.ok("state")
    assert {c["name"]: c["emoji"] for c in state["chores"]} == {
        "Feed the dog": "🐶",
        "take out  the TRASH": None,
    }
    who = {c["name"]: c["members"] for c in state["chores"]}
    assert who == {"Feed the dog": [alex], "take out  the TRASH": [sam]}
    rows = {i["name"]: i["members"] for i in state["todo_lists"][0]["items"]}
    assert rows == {"Feed the dog": [], "take out  the TRASH": [sam]}
    # Nobody ticked: back to the list's people.
    await client.ok(
        "save",
        collection="todo_lists",
        item={
            "entity_id": TODO,
            "points": 2,
            "members": [alex],
            "item_members": {"Take out the trash": []},
        },
    )
    state = await client.ok("state")
    assert {c["members"][0] for c in state["chores"]} == {alex}


async def test_parents_only_actions(
    hass: HomeAssistant, hass_ws_client, hass_read_only_access_token
):
    entry = await _setup(hass)
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    state = await kiosk.ok("state")
    assert state["is_admin"] is False
    assert "to_check" not in state
    res = await kiosk("save", collection="members", item={"name": "Alex"})
    assert res["error"]["code"] == "unauthorized"
    res = await kiosk("adjust", member_id="x", points=5)
    assert res["error"]["code"] == "unauthorized"
    assert entry.runtime_data.members == []


async def test_home_controls(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    alex, _sam = await _family(client)
    hass.states.async_set("light.playroom", "on", {"friendly_name": "Playroom lights"})
    hass.states.async_set("scene.movie_night", "2026-11-04T19:00:00")
    hass.states.async_set("sensor.outside", "38", {"unit_of_measurement": "°F"})
    hass.states.async_set("automation.morning", "on")
    toggles = async_mock_service(hass, "light", "toggle")
    scenes = async_mock_service(hass, "scene", "turn_on")

    choices = await client.ok("choices")
    picked = {e["entity_id"] for e in choices["entities"]}
    assert {"light.playroom", "scene.movie_night", "sensor.outside"} <= picked
    assert "automation.morning" not in picked

    res = await client(
        "save", collection="controls", item={"entity_id": "automation.morning"}
    )
    assert not res["success"]
    light = (
        await client.ok(
            "save",
            collection="controls",
            item={"entity_id": "light.playroom", "members": [alex, "gone"]},
        )
    )["item"]
    assert light["members"] == [alex]
    scene = (
        await client.ok(
            "save",
            collection="controls",
            item={"entity_id": "scene.movie_night", "name": "Movie time"},
        )
    )["item"]
    sensor = (
        await client.ok(
            "save", collection="controls", item={"entity_id": "sensor.outside"}
        )
    )["item"]
    await client.ok("move", collection="controls", item_id=scene["id"], offset=-1)

    # The shared screen isn't an admin, and can use what a parent added.
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    state = await kiosk.ok("state")
    assert [(c["label"], c["kind"]) for c in state["controls"]] == [
        ("Movie time", "run"),
        ("Playroom lights", "toggle"),
        ("outside", "view"),
    ]
    await kiosk.ok("control", control_id=light["id"], action="toggle")
    await kiosk.ok("control", control_id=scene["id"], action="run")
    assert [c.data["entity_id"] for c in toggles] == ["light.playroom"]
    assert [c.data["entity_id"] for c in scenes] == ["scene.movie_night"]
    assert toggles[0].context.user_id is not None

    # Only the actions that entity allows, only entities on the dashboard,
    # and no changes for the shared screen.
    res = await kiosk("control", control_id=sensor["id"], action="toggle")
    assert res["error"]["code"] == "invalid"
    res = await kiosk("control", control_id="nope", action="toggle")
    assert res["error"]["code"] == "invalid"
    res = await kiosk("move", collection="controls", item_id=light["id"], offset=1)
    assert res["error"]["code"] == "unauthorized"
    hass.states.async_set("light.playroom", "unavailable")
    res = await kiosk("control", control_id=light["id"], action="toggle")
    assert "isn't available" in res["error"]["message"]

    # Removing a member takes them off controls too.
    await client.ok("delete", collection="members", item_id=alex)
    state = await client.ok("state")
    assert state["controls"][1]["members"] == []
    await client.ok("delete", collection="controls", item_id=sensor["id"])
    assert len((await client.ok("state"))["controls"]) == 2


async def test_logged_in_member_sees_their_own_page(
    hass: HomeAssistant, client, hass_admin_user
):
    hass.states.async_set(
        "person.alex",
        "home",
        {
            "friendly_name": "Alex",
            "user_id": hass_admin_user.id,
            "entity_picture": "/pic.jpg",
        },
    )
    alex = (
        await client.ok(
            "save", collection="members", item={"name": "Alex", "person": "person.alex"}
        )
    )["item"]
    state = await client.ok("state")
    assert state["me"] == alex["id"]
    assert state["members"][0]["picture"] == "/pic.jpg"


async def test_add_points_action_and_removing_a_member(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    await hass.services.async_call(
        DOMAIN,
        "add_points",
        {"member": "alex", "points": 7, "reason": "Helped"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.family_alex_points").state == "7"

    await client.ok("delete", collection="members", item_id=sam)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.family_sam_points") is None


async def test_saved_across_restarts(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=12)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.points(alex) == 12


async def test_set_up_once(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "abort"


async def test_dashboards_registered(hass: HomeAssistant):
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")
    with (
        patch(
            "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths",
            AsyncMock(),
        ),
        patch(
            "homeassistant.components.panel_custom.async_register_panel", AsyncMock()
        ) as register,
        patch("homeassistant.components.frontend.async_remove_panel") as remove,
        patch("homeassistant.components.frontend.add_extra_js_url") as add_card,
        patch("homeassistant.components.frontend.remove_extra_js_url") as remove_card,
    ):
        entry = await _setup(hass)
        panels = {
            c.kwargs["frontend_url_path"]: c.kwargs for c in register.await_args_list
        }
        assert panels["family"]["require_admin"] is False
        assert panels["family"]["config"] == {"mode": "family"}
        # One Family page in the sidebar. The old Parents page still opens
        # (notifications link to it) but isn't in the sidebar any more.
        assert panels["family"]["sidebar_title"] == "Family"
        assert panels["family-parents"]["sidebar_title"] is None
        assert panels["family-parents"]["require_admin"] is False
        assert panels["family-parents"]["config"] == {"mode": "parents"}
        # The Family card, for a dashboard a login can have as its default.
        card_url = add_card.call_args.args[1]
        assert card_url.startswith("/family_static/family-panel.js?v=")
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert remove_card.call_args.args[1] == card_url
        assert {c.args[1] for c in remove.call_args_list} == {
            "family",
            "family-parents",
        }


def _ago(entry: dict[str, Any], **delta: float) -> None:
    entry["at"] = (dt_util.now() - timedelta(**delta)).isoformat()


async def _tv_mgmt(hass: HomeAssistant, schema=None) -> tuple[str, list[ServiceCall]]:
    tv = MockConfigEntry(domain="tv_mgmt", title="Family Room TV")
    tv.add_to_hass(hass)
    calls: list[ServiceCall] = []

    async def grant(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("tv_mgmt", "grant_extension", grant, schema)
    return tv.entry_id, calls


async def test_undo_a_mistaken_tap(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    alex, _sam = await _family(client)
    tv, calls = await _tv_mgmt(hass)
    await client.ok("adjust", member_id=alex, points=40)
    chore = (
        await client.ok(
            "save", collection="chores", item={"name": "Make your bed", "points": 5}
        )
    )["item"]
    tv_time = (
        await client.ok(
            "save",
            collection="rewards",
            item={
                "name": "30 minutes of TV",
                "points": 20,
                "kind": "tv_time",
                "tv": tv,
                "minutes": 30,
            },
        )
    )["item"]

    # The shared screen can undo what it just did.
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    done = await kiosk.ok("complete", member_id=alex, chore_id=chore["id"])
    assert done["points"] == 45
    await kiosk.ok("undo", entry_id=done["entry"]["id"])
    state = await kiosk.ok("state")
    assert state["members"][0]["points"] == 40
    assert state["chores"][0]["can"]  # it can be done again

    got = await kiosk.ok("redeem", member_id=alex, reward_id=tv_time["id"])
    await kiosk.ok("undo", entry_id=got["entry"]["id"])
    assert calls[-1].data == {
        "profile_id": tv,
        "minutes": -30,
        "whole_home": False,
        "reason": "Undone: 30 minutes of TV",
    }
    assert (await kiosk.ok("state"))["members"][0]["points"] == 40

    # Only for a minute.
    done = await kiosk.ok("complete", member_id=alex, chore_id=chore["id"])
    _ago(entry.runtime_data._entry(done["entry"]["id"]), seconds=61)
    res = await kiosk("undo", entry_id=done["entry"]["id"])
    assert "Ask a parent" in res["error"]["message"]


async def test_reward_once_a_day(hass: HomeAssistant, client):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=50)
    await client.ok("adjust", member_id=sam, points=50)
    treat = (
        await client.ok(
            "save",
            collection="rewards",
            item={"name": "Ice cream", "points": 10, "limit": "daily"},
        )
    )["item"]
    assert treat["limit"] == "daily"
    got = await client.ok("redeem", member_id=alex, reward_id=treat["id"])
    res = await client("redeem", member_id=alex, reward_id=treat["id"])
    assert res["error"]["message"] == "Alex already had Ice cream today"
    # Each person once a day: Sam can still have one.
    await client.ok("redeem", member_id=sam, reward_id=treat["id"])
    state = await client.ok("state")
    assert state["rewards"][0]["used_by"] == sorted([alex, sam])

    # Tomorrow it's back.
    _ago(entry.runtime_data._entry(got["entry"]["id"]), days=1)
    await client.ok("redeem", member_id=alex, reward_id=treat["id"])


async def test_tv_mgmt_before_reasons(hass: HomeAssistant, client):
    """TV Mgmt 1.20.0 doesn't take a reason: the time is given without one."""
    alex, _sam = await _family(client)
    tv, calls = await _tv_mgmt(
        hass,
        vol.Schema(
            {
                vol.Required("profile_id"): str,
                vol.Required("minutes"): int,
                vol.Optional("whole_home"): bool,
            }
        ),
    )
    await client.ok("adjust", member_id=alex, points=50)
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={
                "name": "TV",
                "points": 10,
                "kind": "tv_time",
                "tv": tv,
                "minutes": 15,
            },
        )
    )["item"]
    await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert calls[0].data == {"profile_id": tv, "minutes": 15, "whole_home": False}


async def test_chores_checked_automatically(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    alex, _sam = await _family(client)
    chore = (
        await client.ok(
            "save", collection="chores", item={"name": "Make your bed", "points": 5}
        )
    )["item"]
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    _ago(entry.runtime_data._entry(done["entry"]["id"]), days=2)

    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    res = await kiosk("settings", auto_check="day")
    assert res["error"]["code"] == "unauthorized"
    res = await client("settings", auto_check="month")
    assert not res["success"]

    events = []
    hass.bus.async_listen("family_chore_reviewed", events.append)
    # Off by default: still to check.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1))
    await hass.async_block_till_done()
    assert len((await client.ok("state"))["to_check"]) == 1

    # Turned on: done right after a day.
    assert (await client.ok("settings", auto_check="day"))["settings"] == {
        "auto_check": "day",
        "streak_rule_from": dt_util.now().date().isoformat(),
    }
    await hass.async_block_till_done()
    state = await client.ok("state")
    assert state["to_check"] == []
    assert state["settings"]["auto_check"] == "day"
    assert state["settings"]["penalty"] == 0
    assert state["history"][0]["auto"] is True
    assert events[0].data["automatic"] is True

    # A chore done just now waits; the hourly check picks it up later.
    second = (
        await client.ok(
            "save", collection="chores", item={"name": "Feed the cat", "points": 3}
        )
    )["item"]
    done = await client.ok("complete", member_id=alex, chore_id=second["id"])
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1))
    await hass.async_block_till_done()
    assert len((await client.ok("state"))["to_check"]) == 1
    _ago(entry.runtime_data._entry(done["entry"]["id"]), days=1, minutes=1)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=2))
    await hass.async_block_till_done()
    assert (await client.ok("state"))["to_check"] == []


async def test_a_person_links_to_one_member(hass: HomeAssistant, client):
    hass.states.async_set("person.parent", "home", {"friendly_name": "Parent"})
    first = (
        await client.ok(
            "save",
            collection="members",
            item={"name": "Parent", "person": "person.parent"},
        )
    )["item"]
    res = await client(
        "save", collection="members", item={"name": "Other", "person": "person.parent"}
    )
    assert res["error"]["message"] == "That person is already linked to Parent"
    # Saving the same member again keeps its own link.
    await client.ok("save", collection="members", item={**first, "emoji": "🦖"})


async def test_family_dashboard_messages(hass: HomeAssistant, hass_ws_client):
    """What the Parents dashboard sends to make and update the shared screen's dashboard."""
    assert await async_setup_component(hass, "lovelace", {})
    client = await hass_ws_client(hass)

    async def send(type_: str, **msg: Any) -> dict[str, Any]:
        await client.send_json_auto_id({"type": type_, **msg})
        return await client.receive_json()

    async def ok(type_: str, **msg: Any) -> Any:
        res = await send(type_, **msg)
        assert res["success"], res
        return res["result"]

    assert await ok("lovelace/dashboards/list") == []
    await ok(
        "lovelace/dashboards/create",
        url_path="family-dashboard",
        title="Family dashboard",
        icon="mdi:home-heart",
        mode="storage",
        require_admin=False,
        show_in_sidebar=False,
    )
    # A dashboard that was made but never saved answers config_not_found,
    # which the Parents dashboard treats as empty.
    res = await send("lovelace/config", url_path="family-dashboard")
    assert res["error"]["code"] == "config_not_found"

    def card(member: str | None = None) -> dict[str, Any]:
        return {"type": "custom:family-card", **({"member": member} if member else {})}

    config = {
        "title": "Family dashboard",
        "views": [
            {"title": "Home", "path": "family", "type": "panel", "cards": [card()]},
            {
                "title": "Alex",
                "path": "family-member-a1",
                "type": "panel",
                "cards": [card("a1")],
            },
        ],
    }
    await ok("lovelace/config/save", url_path="family-dashboard", config=config)
    (dashboard,) = await ok("lovelace/dashboards/list")
    assert dashboard["url_path"] == "family-dashboard"
    # Read back to update the tabs, keeping anything added by hand.
    assert await ok("lovelace/config", url_path="family-dashboard") == config


async def test_bonus_for_all_chores_done(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    await client.ok("settings", bonus_all_done=5, auto_check="day")
    # Only the bonus setting changed when sent alone.
    await client.ok("settings", streak_days=0)
    assert (await client.ok("state"))["settings"]["auto_check"] == "day"

    own = []
    for name in ("Make your bed", "Feed the cat"):
        own.append(
            (
                await client.ok(
                    "save",
                    collection="chores",
                    item={"name": name, "points": 2, "members": [alex]},
                )
            )["item"]
        )
    shared = (
        await client.ok(
            "save", collection="chores", item={"name": "Sweep", "points": 1}
        )
    )["item"]
    bonuses = []
    hass.bus.async_listen("family_bonus_given", bonuses.append)

    # A chore anyone can do doesn't count; their own chores do.
    await client.ok("complete", member_id=alex, chore_id=shared["id"])
    first = await client.ok("complete", member_id=alex, chore_id=own[0]["id"])
    assert "bonuses" not in first["entry"]
    last = await client.ok("complete", member_id=alex, chore_id=own[1]["id"])
    assert [b["title"] for b in last["entry"]["bonuses"]] == ["All done today!"]
    assert last["points"] == 1 + 2 + 2 + 5
    await hass.async_block_till_done()
    assert bonuses[0].data["points"] == 5

    state = await client.ok("state")
    assert state["bonus"] == {"all_done": 5, "streak_days": 0, "streak": 0}
    assert state["members"][0]["done_today"] == 3
    assert state["members"][0]["streak"] == 1
    assert [e["title"] for e in state["done_today"]][0] == "Feed the cat"

    # Undo takes the bonus back with the chore; doing it again earns it again.
    await client.ok("undo", entry_id=last["entry"]["id"])
    assert (await client.ok("state"))["members"][0]["points"] == 3
    again = await client.ok("complete", member_id=alex, chore_id=own[1]["id"])
    assert again["points"] == 10

    # It didn't happen: the bonus goes too, and it's only once a day.
    await client.ok("review", entry_id=again["entry"]["id"], approved=False)
    assert (await client.ok("state"))["members"][0]["points"] == 3


async def test_streak_bonus(hass: HomeAssistant, client):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    manager = entry.runtime_data
    alex, _sam = await _family(client)
    await client.ok("settings", streak_days=3, streak_bonus=10)
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Make your bed", "points": 1, "members": [alex]},
        )
    )["item"]
    # Done the two days before today, under the old rule (any chore).
    for days in (2, 1):
        manager.entries.append(
            {
                "id": f"old{days}",
                "at": (dt_util.now() - timedelta(days=days)).isoformat(),
                "kind": "chore",
                "member": alex,
                "title": "Make your bed",
                "points": 1,
                "chore_id": chore["id"],
                "review": "approved",
            }
        )
    assert (await client.ok("state"))["members"][0]["streak"] == 2
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    # Finishing their own chores marks the day, even with no all-done bonus.
    assert [(b["title"], b["points"]) for b in done["entry"]["bonuses"]] == [
        ("All done today!", 0),
        ("3 days in a row!", 10),
    ]
    assert done["points"] == 3 + 10
    assert (await client.ok("state"))["members"][0]["streak"] == 3


async def test_penalty_when_a_chore_didnt_happen(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    await client.ok("settings", penalty=2)
    plain = (
        await client.ok(
            "save", collection="chores", item={"name": "Make your bed", "points": 5}
        )
    )["item"]
    strict = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Brush teeth", "points": 3, "penalty": 10},
        )
    )["item"]
    assert plain["penalty"] is None
    assert strict["penalty"] == 10
    events = []
    hass.bus.async_listen("family_chore_reviewed", events.append)

    async def points() -> int:
        return (await client.ok("state"))["members"][0]["points"]

    # The family's penalty: the 5 points back, and 2 more.
    done = await client.ok("complete", member_id=alex, chore_id=plain["id"])
    await client.ok("review", entry_id=done["entry"]["id"], approved=False)
    assert await points() == -2
    # Done right after all: the penalty goes too.
    await client.ok("review", entry_id=done["entry"]["id"], approved=True)
    assert await points() == 5

    # The chore's own penalty.
    done = await client.ok("complete", member_id=alex, chore_id=strict["id"])
    await client.ok("review", entry_id=done["entry"]["id"], approved=False)
    assert await points() == 5 - 10
    await hass.async_block_till_done()
    assert events[-1].data["penalty"] == 10

    # What the parent typed when checking wins, and replaces the earlier one.
    await client.ok("review", entry_id=done["entry"]["id"], approved=False, penalty=0)
    assert await points() == 5
    state = await client.ok("state")
    assert [e["kind"] for e in state["history"]].count("penalty") == 0


class FakeTodoList:
    """A to-do list entity's actions, with uids, like Local To-do."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self.items: list[dict[str, Any]] = []
        self._next = 0
        for name, handler in (
            ("add_item", self.add_item),
            ("update_item", self.update_item),
            ("remove_item", self.remove_item),
        ):
            hass.services.async_register("todo", name, handler)
        hass.services.async_register(
            "todo", "get_items", self.get_items, supports_response=SupportsResponse.ONLY
        )
        self._state()

    def _state(self) -> None:
        open_items = sum(i["status"] == "needs_action" for i in self.items)
        self.hass.states.async_set(
            self.entity_id, str(open_items), {"friendly_name": "Kids"}
        )

    def item(self, name: str) -> dict[str, Any] | None:
        return next((i for i in self.items if i["summary"] == name), None)

    async def get_items(self, call: ServiceCall):
        wanted = call.data.get("status") or ["needs_action", "completed"]
        return {
            self.entity_id: {
                "items": [dict(i) for i in self.items if i["status"] in wanted]
            }
        }

    async def add_item(self, call: ServiceCall) -> None:
        self._next += 1
        self.items.append(
            {
                "uid": f"u{self._next}",
                "summary": call.data["item"],
                "status": "needs_action",
            }
        )
        self._state()

    async def update_item(self, call: ServiceCall) -> None:
        item = next(i for i in self.items if i["uid"] == call.data["item"])
        if "status" in call.data:
            item["status"] = call.data["status"]
        if "rename" in call.data:
            item["summary"] = call.data["rename"]
        self._state()

    async def remove_item(self, call: ServiceCall) -> None:
        self.items = [i for i in self.items if i["uid"] not in call.data["item"]]
        self._state()


async def _sync(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_dashboard_chore_on_a_todo_list(hass: HomeAssistant, client):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    alex, _sam = await _family(client)
    todo = FakeTodoList(hass, "todo.kids")
    # The same list is also a chore list: Family's own items aren't counted twice.
    await client.ok(
        "save", collection="todo_lists", item={"entity_id": "todo.kids", "points": 1}
    )
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={
                "name": "Feed the cat",
                "points": 2,
                "repeat": "after_check",
                "todo_list": "todo.kids",
            },
        )
    )["item"]
    await _sync(hass)
    assert todo.item("Feed the cat")["status"] == "needs_action"
    state = await client.ok("state")
    assert [c["name"] for c in state["chores"]] == ["Feed the cat"]

    # Done: ticked off on the list. Still to check, so it isn't back yet.
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await _sync(hass)
    assert todo.item("Feed the cat")["status"] == "completed"
    assert (await client.ok("state"))["chores"] == []  # not back yet

    # Checked: it comes back, and so does the item.
    await client.ok("review", entry_id=done["entry"]["id"], approved=True)
    await _sync(hass)
    assert todo.item("Feed the cat")["status"] == "needs_action"
    assert len(todo.items) == 1

    # Renamed with the chore; deleted on the list: added again when it's open.
    await client.ok(
        "save",
        collection="chores",
        item={**chore, "name": "Feed the cats", "repeat": "after_check"},
    )
    await _sync(hass)
    assert todo.item("Feed the cats") is not None
    todo.items.clear()
    entry.runtime_data.todo_sync.schedule()
    await _sync(hass)
    # Nothing changed for the chore, so nothing is done until it does.
    assert todo.items == []
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await client.ok("review", entry_id=done["entry"]["id"], approved=True)
    await _sync(hass)
    assert todo.item("Feed the cats")["status"] == "needs_action"

    # Off the list, or removed: its item goes.
    await client.ok(
        "save",
        collection="chores",
        item={
            **chore,
            "name": "Feed the cats",
            "repeat": "after_check",
            "todo_list": None,
        },
    )
    await _sync(hass)
    assert todo.items == []
    await client.ok(
        "save",
        collection="chores",
        item={**chore, "repeat": "after_check", "todo_list": "todo.kids"},
    )
    await _sync(hass)
    assert len(todo.items) == 1
    await client.ok("delete", collection="chores", item_id=chore["id"])
    await _sync(hass)
    assert todo.items == []


async def test_chore_back_days_after_done(hass: HomeAssistant, client):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    alex, _sam = await _family(client)
    todo = FakeTodoList(hass, "todo.kids")
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={
                "name": "Water the plants",
                "points": 2,
                "repeat": "after_days",
                "repeat_days": 3,
                "todo_list": "todo.kids",
            },
        )
    )["item"]
    assert chore["repeat_days"] == 3
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await _sync(hass)
    assert todo.item("Water the plants")["status"] == "completed"
    assert (await client.ok("state"))["chores"] == []  # not back yet

    # Three days later (the midnight sync): back, and open on the list.
    entry.runtime_data._entry(done["entry"]["id"])["at"] = (
        dt_util.now() - timedelta(days=3)
    ).isoformat()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1))
    await _sync(hass)
    assert todo.item("Water the plants")["status"] == "needs_action"
    assert alex in (await client.ok("state"))["chores"][0]["can"]


async def test_chore_back_right_away(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Put a toy away", "points": 1, "repeat": "always"},
        )
    )["item"]
    for _ in range(3):
        await client.ok("complete", member_id=alex, chore_id=chore["id"])
    state = await client.ok("state")
    assert state["members"][0]["points"] == 3
    assert alex in state["chores"][0]["can"]


# ---- 1.6.0: set days and hours, turns, saving up, music time, parents' phones ----


def _next(weekday: int, hour: int, minute: int = 0, second: int = 0):
    """A time on the coming weekday (Monday 0), a week or more ahead: time
    listeners only fire forwards."""
    now = dt_util.now()
    day = now + timedelta(days=7 + (weekday - now.weekday()) % 7)
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


async def test_chores_on_set_days_and_hours(hass: HomeAssistant, client, freezer):
    # A Tuesday morning.
    tuesday = _next(1, 7)
    freezer.move_to(tuesday)
    alex, _sam = await _family(client)
    await client.ok(
        "save",
        collection="chores",
        item={
            "name": "Brush teeth",
            "points": 1,
            "days": [1, 3],
            "from_time": "6:00",
            "until_time": "09:00",
        },
    )
    wednesday = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Take out the trash", "points": 3, "days": [2]},
        )
    )["item"]
    assert wednesday["days"] == [2]
    state = await client.ok("state")
    assert [c["name"] for c in state["chores"]] == ["Brush teeth"]
    assert state["all_chores"][0]["from_time"] == "06:00"
    res = await client("complete", member_id=alex, chore_id=wednesday["id"])
    assert res["error"]["message"] == "Take out the trash isn't for right now"
    res = await client(
        "save", collection="chores", item={"name": "Bad", "from_time": "nine"}
    )
    assert not res["success"]

    # The dashboards hear when the morning's over.
    await client.ws.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    sub = await client.ws.receive_json()
    assert sub["success"]
    freezer.move_to(tuesday.replace(hour=9, second=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    event = await client.ws.receive_json()
    assert event["id"] == sub["id"]
    assert event["event"] == {"changed": True}
    assert (await client.ok("state"))["chores"] == []

    # Wednesday: the trash.
    freezer.move_to(tuesday + timedelta(days=1, hours=5))
    state = await client.ok("state")
    assert [c["name"] for c in state["chores"]] == ["Take out the trash"]


async def test_chores_taken_in_turns(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    res = await client(
        "save",
        collection="chores",
        item={"name": "Dishes", "points": 4, "members": [alex], "turns": True},
    )
    assert res["error"]["message"] == "Pick at least two people to take turns"
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={
                "name": "Dishes",
                "points": 4,
                "repeat": "always",
                "members": [alex, sam],
                "turns": True,
                "turn_first": sam,
            },
        )
    )["item"]
    state = await client.ok("state")
    [dishes] = state["chores"]
    assert dishes["turn"] == sam
    assert dishes["rotation"] == [alex, sam]
    assert dishes["can"] == [sam]
    res = await client("complete", member_id=alex, chore_id=chore["id"])
    assert not res["success"]
    await client.ok("complete", member_id=sam, chore_id=chore["id"])
    [dishes] = (await client.ok("state"))["chores"]
    assert dishes["turn"] == alex

    # Not done after all: it's Sam's turn again.
    entry_id = (await client.ok("state"))["to_check"][0]["id"]
    await client.ok("review", entry_id=entry_id, approved=False)
    [dishes] = (await client.ok("state"))["chores"]
    assert dishes["turn"] == sam


async def test_saving_for_a_reward(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    alex, _sam = await _family(client)
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={"name": "Ice cream", "points": 10, "kind": "custom"},
        )
    )["item"]
    # Picked on the shared screen, which isn't an admin.
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    await kiosk.ok("goal", member_id=alex, reward_id=reward["id"])
    res = await kiosk("goal", member_id=alex, reward_id="nope")
    assert not res["success"]
    # Editing the member keeps it.
    await client.ok("save", collection="members", item={"id": alex, "name": "Alexa"})
    member = (await client.ok("state"))["members"][0]
    assert member["goal"] == reward["id"]

    # Spent on it: saved up, so the goal's done.
    await client.ok("adjust", member_id=alex, points=10)
    await kiosk.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert (await client.ok("state"))["members"][0]["goal"] is None

    # A reward that's removed stops being a goal.
    await kiosk.ok("goal", member_id=alex, reward_id=reward["id"])
    await client.ok("delete", collection="rewards", item_id=reward["id"])
    assert (await client.ok("state"))["members"][0]["goal"] is None
    await kiosk.ok("goal", member_id=alex, reward_id=None)


async def test_music_time_reward(hass: HomeAssistant, client):
    speaker = MockConfigEntry(domain="media_mgmt", title="Kids Room")
    speaker.add_to_hass(hass)
    calls: list[ServiceCall] = []

    async def grant(call: ServiceCall) -> None:
        calls.append(call)

    alex, _sam = await _family(client)
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={
                "name": "Music",
                "points": 5,
                "kind": "music_time",
                "speaker": speaker.entry_id,
                "minutes": 20,
            },
        )
    )["item"]
    await client.ok("adjust", member_id=alex, points=5)
    res = await client("redeem", member_id=alex, reward_id=reward["id"])
    assert res["error"]["message"] == "Music time needs Media Mgmt, which isn't set up"

    hass.services.async_register("media_mgmt", "grant_extension", grant)
    choices = await client.ok("choices")
    assert choices["speakers"] == [{"id": speaker.entry_id, "name": "Kids Room"}]
    state = await client.ok("state")
    assert state["rewards"][0]["speaker_name"] == "Kids Room"
    done = await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert done["entry"]["given"] == "given"
    assert calls[0].data == {
        "profile_id": speaker.entry_id,
        "minutes": 20,
        "reason": "Alex's reward: Music",
    }
    await client.ok("undo", entry_id=done["entry"]["id"])
    assert calls[1].data["minutes"] == -20


async def test_music_time_for_the_whole_home(hass: HomeAssistant, client):
    speaker = MockConfigEntry(domain="media_mgmt", title="Kids Room")
    speaker.add_to_hass(hass)
    calls: list[ServiceCall] = []

    async def grant(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("media_mgmt", "grant_extension", grant)
    alex, _sam = await _family(client)
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={
                "name": "Party music",
                "points": 0,
                "kind": "music_time",
                "speaker": speaker.entry_id,
                "minutes": 30,
                "whole_home": True,
            },
        )
    )["item"]
    assert reward["whole_home"] is True
    done = await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert calls[0].data == {
        "profile_id": speaker.entry_id,
        "minutes": 30,
        "reason": "Alex's reward: Party music",
        "whole_home": True,
    }
    # Undo takes the whole home's time back too.
    await client.ok("undo", entry_id=done["entry"]["id"])
    assert calls[1].data["minutes"] == -30
    assert calls[1].data["whole_home"] is True


async def test_media_mgmt_before_reasons(hass: HomeAssistant, client):
    speaker = MockConfigEntry(domain="media_mgmt", title="Kids Room")
    speaker.add_to_hass(hass)
    calls: list[ServiceCall] = []

    async def grant(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register(
        "media_mgmt",
        "grant_extension",
        grant,
        vol.Schema({vol.Required("profile_id"): str, vol.Required("minutes"): int}),
    )
    alex, _sam = await _family(client)
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={
                "name": "Music",
                "points": 0,
                "kind": "music_time",
                "speaker": speaker.entry_id,
                "minutes": 15,
            },
        )
    )["item"]
    await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert calls[0].data == {"profile_id": speaker.entry_id, "minutes": 15}


async def test_parents_check_chores_from_their_phones(
    hass: HomeAssistant, client, hass_admin_user, hass_read_only_user
):
    from homeassistant.core import Context  # noqa: PLC0415

    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    alex, _sam = await _family(client)
    res = await client("settings", notify_targets=["mobile_app_nobody"])
    assert (
        res["error"]["message"] == "There's no notify action called mobile_app_nobody"
    )
    choices = await client.ok("choices")
    assert {"service": "mobile_app_dads_phone", "name": "Dads phone"} in choices[
        "notify"
    ]
    chore = (
        await client.ok("save", collection="chores", item={"name": "Bed", "points": 5})
    )["item"]

    # Off until it's turned on.
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await hass.async_block_till_done()
    assert sent == []
    await client.ok("undo", entry_id=(await client.ok("state"))["to_check"][0]["id"])

    settings = (
        await client.ok(
            "settings",
            notify_targets=["mobile_app_dads_phone"],
            notify_done=True,
            notify_rewards=True,
        )
    )["settings"]
    assert settings["notify_targets"] == ["mobile_app_dads_phone"]
    await hass.async_block_till_done()
    sent.clear()
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    entry_id = done["entry"]["id"]
    await hass.async_block_till_done()
    [note] = sent
    assert note.data["title"] == "Alex did Bed"
    assert note.data["data"]["tag"] == f"family-{entry_id}"
    actions = [a["action"] for a in note.data["data"]["actions"]]
    assert actions == [f"FAMILY_RIGHT_{entry_id}", f"FAMILY_DIDNT_{entry_id}"]

    # Someone who isn't a parent can't check it from a phone.
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"FAMILY_DIDNT_{entry_id}"},
        context=Context(user_id=hass_read_only_user.id),
    )
    await hass.async_block_till_done()
    assert (await client.ok("state"))["to_check"][0]["id"] == entry_id

    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"FAMILY_RIGHT_{entry_id}"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    state = await client.ok("state")
    assert state["to_check"] == []
    assert state["history"][0]["review"] == "approved"
    # Checked: its notification is taken away.
    assert sent[-1].data == {
        "message": "clear_notification",
        "data": {"tag": f"family-{entry_id}"},
    }
    # A second press does nothing harmful.
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": "FAMILY_RIGHT_gone"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()

    # A reward to hand out.
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={"name": "Ice cream", "points": 1, "kind": "custom"},
        )
    )["item"]
    sent.clear()
    got = await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    await hass.async_block_till_done()
    assert sent[0].data["title"] == "Alex picked Ice cream"
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"FAMILY_GIVEN_{got['entry']['id']}"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    assert (await client.ok("state"))["to_give"] == []


async def test_weekly_summary(hass: HomeAssistant, client, freezer):
    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    # Saturday evening: nothing. Sunday at 18:00: the summary.
    sunday = _next(6, 18)
    freezer.move_to(sunday - timedelta(days=1))
    alex, _sam = await _family(client)
    chore = (
        await client.ok("save", collection="chores", item={"name": "Bed", "points": 5})
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await client.ok(
        "settings", notify_targets=["mobile_app_dads_phone"], weekly_summary=True
    )
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert sent == []
    freezer.move_to(sunday)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    [summary] = sent
    assert summary.data["title"] == "Family this week"
    assert summary.data["message"].splitlines() == [
        "Alex: 1 chore, +5, 5 now",
        "Sam: 0 chores, +0, 0 now",
        "1 chore to check",
    ]


async def test_parent_pin_gives_the_shared_screen_a_pass(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    """The PIN opens the parent controls on a login that isn't an admin."""
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    state = await kiosk.ok("state")
    assert state["pin_set"] is False
    assert state["parent"] is False
    res = await kiosk("unlock", pin="2468")
    assert not res["success"]

    # Only an admin sets the PIN; a pass can't change it.
    res = await kiosk("pin", pin="1357")
    assert res["error"]["code"] == "unauthorized"
    res = await client("pin", pin="12")
    assert not res["success"]
    assert (await client.ok("pin", pin="2468"))["pin_set"] is True
    stored = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.settings
    assert "2468" not in str(stored["parent_pin"])

    res = await kiosk("unlock", pin="1111")
    assert res["error"]["message"] == "That's not the PIN. Try again."
    token = (await kiosk.ok("unlock", pin="2468"))["pass"]

    # With the pass: parent commands and the parent data.
    state = await kiosk.ok("state", **{"pass": token})
    assert state["parent"] is True
    assert state["is_admin"] is False
    assert "settings" in state
    saved = await kiosk.ok(
        "save", collection="members", item={"name": "Alex"}, **{"pass": token}
    )
    assert saved["item"]["name"] == "Alex"
    await kiosk.ok("choices", **{"pass": token})
    res = await kiosk("pin", pin="1357", **{"pass": token})
    assert res["error"]["code"] == "unauthorized"

    # Without it, or with a made-up one: still refused.
    res = await kiosk("adjust", member_id=saved["item"]["id"], points=5)
    assert res["error"]["code"] == "unauthorized"
    res = await kiosk(
        "adjust", member_id=saved["item"]["id"], points=5, **{"pass": "nope"}
    )
    assert res["error"]["code"] == "unauthorized"

    # Back to Family ends it.
    await kiosk.ok("lock", **{"pass": token})
    state = await kiosk.ok("state", **{"pass": token})
    assert state["parent"] is False
    assert "settings" not in state

    # Removing the PIN ends every pass.
    token = (await kiosk.ok("unlock", pin="2468"))["pass"]
    assert (await client.ok("pin", pin=None))["pin_set"] is False
    assert (await kiosk.ok("state", **{"pass": token}))["parent"] is False


async def test_parent_pass_belongs_to_its_login(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    await client.ok("pin", pin="2468")
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    token = (await kiosk.ok("unlock", pin="2468"))["pass"]
    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    assert manager.passes.valid(token, "someone-else") is False
    assert (await kiosk.ok("state", **{"pass": token}))["parent"] is True


async def test_parent_pass_runs_out(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    from custom_components.family import parent_pass

    await client.ok("pin", pin="2468")
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    now = 1000.0
    with patch.object(parent_pass.time, "monotonic", lambda: now):
        token = (await kiosk.ok("unlock", pin="2468"))["pass"]
        now += parent_pass.PASS_SECONDS - 5
        # Using it keeps it going.
        assert (await kiosk.ok("state", **{"pass": token}))["parent"] is True
        now += parent_pass.PASS_SECONDS - 5
        assert (await kiosk.ok("state", **{"pass": token}))["parent"] is True
        now += parent_pass.PASS_SECONDS + 1
        assert (await kiosk.ok("state", **{"pass": token}))["parent"] is False


async def test_wrong_pins_lock_the_pad_and_tell_the_parents(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
):
    from custom_components.family import parent_pass

    sent = async_mock_service(hass, "notify", "mobile_app_parent")
    await client.ok("settings", notify_targets=["mobile_app_parent"])
    await client.ok("pin", pin="2468")
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    now = 1000.0
    with patch.object(parent_pass.time, "monotonic", lambda: now):
        for _ in range(parent_pass.MAX_TRIES - 1):
            res = await kiosk("unlock", pin="0000")
            assert res["error"]["message"] == "That's not the PIN. Try again."
        res = await kiosk("unlock", pin="0000")
        assert "Too many wrong PINs" in res["error"]["message"]
        await hass.async_block_till_done()
        assert sent and sent[-1].data["title"] == "Parent PIN locked"
        # Even the right PIN waits.
        res = await kiosk("unlock", pin="2468")
        assert "Too many wrong PINs" in res["error"]["message"]
        now += parent_pass.LOCK_SECONDS + 1
        assert (await kiosk.ok("unlock", pin="2468"))["pass"]


async def test_admins_are_parents_without_a_pin(hass: HomeAssistant, client):
    state = await client.ok("state")
    assert state["parent"] is True
    assert state["is_admin"] is True


async def test_each_parent_can_have_their_own_pin(
    hass: HomeAssistant,
    client,
    hass_ws_client,
    hass_admin_user,
    hass_read_only_access_token,
):
    state = await client.ok("state")
    assert state["pins"] == {"family": False, "mine": False, "parents": []}
    res = await client.ok("pin", pin="1357", own=True)
    assert res["mine"] is True
    assert res["family"] is False
    assert res["parents"] == [hass_admin_user.name]
    await client.ok("pin", pin="2468")
    # Two PINs can't be the same digits.
    res = await client("pin", pin="1357")
    assert res["error"]["message"] == "That PIN is already used. Pick another one."
    res = await client("pin", pin="2468", own=True)
    assert not res["success"]
    # The hashes never leave Home Assistant.
    settings = (await client.ok("settings", penalty=1))["settings"]
    assert "parent_pin" not in settings
    assert "parent_pins" not in settings

    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    state = await kiosk.ok("state")
    assert state["pin_set"] is True
    assert state["pins"] is None
    own = await kiosk.ok("unlock", pin="1357")
    assert own["by"] == hass_admin_user.name
    family = await kiosk.ok("unlock", pin="2468")
    assert family["by"] is None
    for token in (own["pass"], family["pass"]):
        assert (await kiosk.ok("state", **{"pass": token}))["parent"] is True

    # A parent who's no longer an admin: their own PIN stops working.
    hass_admin_user.groups = []
    res = await kiosk("unlock", pin="1357")
    assert res["error"]["message"] == "That's not the PIN. Try again."
    assert (await kiosk.ok("unlock", pin="2468"))["pass"]


async def test_only_the_family_pin_or_your_own(hass: HomeAssistant, client):
    await client.ok("pin", pin="1357", own=True)
    await client.ok("pin", pin=None)
    state = await client.ok("state")
    assert state["pins"]["mine"] is True
    assert state["pin_set"] is True
    await client.ok("pin", pin=None, own=True)
    state = await client.ok("state")
    assert state["pin_set"] is False
    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    assert "parent_pins" not in manager.settings
