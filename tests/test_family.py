"""Family inside Home Assistant: the dashboards' API, points, rewards, to-do lists."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.family.const import DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.setup import async_setup_component

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
    alex, _sam = await _family(client)
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
    ):
        entry = await _setup(hass)
        panels = {
            c.kwargs["frontend_url_path"]: c.kwargs for c in register.await_args_list
        }
        assert panels["family"]["require_admin"] is False
        assert panels["family"]["config"] == {"mode": "family"}
        assert panels["family-parents"]["require_admin"] is True
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert {c.args[1] for c in remove.call_args_list} == {
            "family",
            "family-parents",
        }
