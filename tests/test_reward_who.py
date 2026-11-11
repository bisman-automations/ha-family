"""Who can get each reward: storage, editing, the dashboards' data, and redeeming."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.family import model
from custom_components.family.const import STORAGE_KEY
from homeassistant.core import HomeAssistant
from tests.test_family import Client, _family, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _reward(client: Client, **item: Any) -> dict[str, Any]:
    return (await client.ok("save", collection="rewards", item=item))["item"]


async def test_new_reward_is_for_everyone_until_people_are_picked(
    hass: HomeAssistant, client: Client
):
    alex, sam = await _family(client)
    # Leaving it out, and sending null, both mean everyone.
    omitted = await _reward(client, name="Ice cream", points=5, kind="custom")
    assert omitted["members"] is None
    explicit = await _reward(
        client, name="Movie", points=10, kind="custom", members=None
    )
    assert explicit["members"] is None

    picked = await _reward(
        client,
        name="15 minutes of TV",
        points=5,
        kind="custom",
        members=[alex, sam, "not-a-person"],
    )
    assert picked["members"] == [alex, sam]
    state = await client.ok("state")
    row = next(r for r in state["rewards"] if r["id"] == picked["id"])
    assert row["members"] == [alex, sam]

    # Back to everyone, then nobody. An empty list is not everyone.
    everyone = await _reward(
        client,
        id=picked["id"],
        name="15 minutes of TV",
        points=5,
        kind="custom",
        members=None,
    )
    assert everyone["members"] is None
    nobody = await _reward(
        client,
        id=picked["id"],
        name="15 minutes of TV",
        points=5,
        kind="custom",
        members=[],
    )
    assert nobody["members"] == []

    # An edit that doesn't say who keeps the people already saved.
    kept = await _reward(
        client, id=picked["id"], name="15 minutes of TV", points=8, kind="custom"
    )
    assert kept["members"] == []
    assert kept["points"] == 8

    res = await client(
        "save", collection="rewards", item={"name": "Nope", "members": "alex"}
    )
    assert not res["success"]
    assert "who can get it" in res["error"]["message"].lower()


async def test_redeem_and_saving_are_refused_for_anyone_else(
    hass: HomeAssistant, client: Client
):
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=50)
    await client.ok("adjust", member_id=sam, points=50)
    reward = await _reward(
        client, name="15 minutes of TV", points=5, kind="custom", members=[alex]
    )
    events = async_capture_events(hass, "family_reward_redeemed")

    refused = await client("redeem", member_id=sam, reward_id=reward["id"])
    assert not refused["success"]
    assert refused["error"]["message"] == (
        "Sam can't get 15 minutes of TV. A parent hasn't included them"
    )
    assert (await client.ok("state"))["members"][1]["points"] == 50
    assert events == []

    # Together can't bring in someone the reward isn't for, and spends nothing.
    shared = await client(
        "redeem", member_id=alex, reward_id=reward["id"], together=[sam]
    )
    assert not shared["success"]
    assert "Sam can't get 15 minutes of TV" in shared["error"]["message"]
    points = {m["name"]: m["points"] for m in (await client.ok("state"))["members"]}
    assert points == {"Alex": 50, "Sam": 50}

    goal = await client("goal", member_id=sam, reward_id=reward["id"])
    assert not goal["success"]
    assert "Sam can't get 15 minutes of TV" in goal["error"]["message"]

    done = await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert done["points"] == 45
    await hass.async_block_till_done()
    assert events[0].data["reward"] == "15 minutes of TV"
    assert events[0].data["eligible"] == ["Alex"]

    # A reward for everyone still says so on the event.
    treat = await _reward(client, name="Ice cream", points=1, kind="custom")
    await client.ok("redeem", member_id=sam, reward_id=treat["id"])
    await hass.async_block_till_done()
    assert events[-1].data["eligible"] == "everyone"
    assert events[-1].data["member"] == "Sam"


async def test_unavailable_reward_is_refused_for_everyone(
    hass: HomeAssistant, client: Client
):
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=20)
    await client.ok("adjust", member_id=sam, points=20)
    reward = await _reward(
        client, name="Board game", points=5, kind="custom", members=[]
    )
    for member_id, name in ((alex, "Alex"), (sam, "Sam")):
        res = await client("redeem", member_id=member_id, reward_id=reward["id"])
        assert not res["success"]
        assert res["error"]["message"] == (
            f"{name} can't get Board game. Nobody can get it until a parent "
            "chooses who it's for"
        )
    # The list still has it, so a parent can choose someone.
    assert (await client.ok("state"))["rewards"][0]["members"] == []
    opened = await _reward(
        client,
        id=reward["id"],
        name="Board game",
        points=5,
        kind="custom",
        members=[sam],
    )
    assert opened["members"] == [sam]
    await client.ok("redeem", member_id=sam, reward_id=reward["id"])
    refused = await client("redeem", member_id=alex, reward_id=reward["id"])
    assert not refused["success"]


async def test_removing_a_member_drops_them_and_can_leave_it_unavailable(
    hass: HomeAssistant, client: Client
):
    alex, sam = await _family(client)
    riley = (await client.ok("save", collection="members", item={"name": "Riley"}))[
        "item"
    ]["id"]
    both = await _reward(
        client, name="Ice cream", points=5, kind="custom", members=[alex, sam]
    )
    only = await _reward(client, name="Music", points=5, kind="custom", members=[riley])
    everyone = await _reward(client, name="Movie", points=5, kind="custom")
    await client.ok("adjust", member_id=alex, points=30)
    await client.ok("goal", member_id=alex, reward_id=both["id"])

    await client.ok("delete", collection="members", item_id=riley)
    state = await client.ok("state")
    by_name = {r["name"]: r["members"] for r in state["rewards"]}
    # The last person it was for is gone: nobody, not everyone.
    # Ice cream was for Alex and Sam, so Sam stays.
    assert by_name["Music"] == []
    assert by_name["Ice cream"] == [alex, sam]
    assert by_name["Movie"] is None
    alex_row = next(m for m in state["members"] if m["id"] == alex)
    assert alex_row["goal"] == both["id"]

    res = await client("redeem", member_id=alex, reward_id=only["id"])
    assert not res["success"]
    assert "Nobody can get it" in res["error"]["message"]
    # Everyone is unchanged, so Alex can still get the movie.
    await client.ok("redeem", member_id=alex, reward_id=everyone["id"])

    # Taking Alex off the shared reward clears the goal he was saving for,
    # and leaves it for Sam.
    await _reward(
        client,
        id=both["id"],
        name="Ice cream",
        points=5,
        kind="custom",
        members=[sam],
    )
    state = await client.ok("state")
    alex_row = next(m for m in state["members"] if m["id"] == alex)
    assert alex_row["goal"] is None
    assert next(r for r in state["rewards"] if r["id"] == both["id"])["members"] == [
        sam
    ]

    await client.ok("delete", collection="members", item_id=alex)
    state = await client.ok("state")
    ice = next(r for r in state["rewards"] if r["id"] == both["id"])
    assert ice["members"] == [sam]
    movie = next(r for r in state["rewards"] if r["id"] == everyone["id"])
    assert movie["members"] is None


async def test_points_sensor_lists_rewards_they_can_get(
    hass: HomeAssistant, client: Client
):
    alex, sam = await _family(client)
    await _reward(client, name="Movie", points=10, kind="custom")
    await _reward(
        client, name="15 minutes of TV", points=5, kind="custom", members=[alex, sam]
    )
    await _reward(client, name="Board game", points=15, kind="custom", members=[])
    await _reward(client, name="Music", points=8, kind="custom", members=[sam])
    await hass.async_block_till_done()

    alex_rewards = hass.states.get("sensor.family_alex_points").attributes["rewards"]
    assert alex_rewards == [
        {"name": "Movie", "points": 10, "eligible": "everyone"},
        {
            "name": "15 minutes of TV",
            "points": 5,
            "eligible": ["Alex", "Sam"],
        },
    ]
    sam_names = [
        reward["name"]
        for reward in hass.states.get("sensor.family_sam_points").attributes["rewards"]
    ]
    assert sam_names == ["Movie", "15 minutes of TV", "Music"]


async def test_version_1_rewards_migrate_to_everyone(
    hass: HomeAssistant, hass_storage: dict[str, Any], hass_ws_client
):
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "members": [
                {
                    "id": "alex",
                    "name": "Alex",
                    "color": "#3F51B5",
                    "allowance": 0,
                }
            ],
            "rewards": [
                {
                    "id": "tv",
                    "name": "15 minutes of TV",
                    "points": 5,
                    "kind": "custom",
                }
            ],
        },
    }
    entry = await _setup(hass)
    stored = hass_storage[STORAGE_KEY]
    assert stored["version"] == 2
    assert stored["data"]["rewards"][0]["members"] is None

    client = Client(await hass_ws_client(hass))
    state = await client.ok("state")
    assert state["rewards"][0]["members"] is None
    await client.ok("adjust", member_id="alex", points=10)
    done = await client.ok("redeem", member_id="alex", reward_id="tv")
    assert done["points"] == 5
    # The migrated reward is the one the manager is using.
    assert entry.runtime_data.rewards[0]["members"] is None


async def test_version_2_keeps_nobody_and_fills_a_missing_key(
    hass: HomeAssistant, hass_storage: dict[str, Any], hass_ws_client
):
    hass_storage[STORAGE_KEY] = {
        "version": 2,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "members": [
                {"id": "alex", "name": "Alex", "color": "#3F51B5", "allowance": 0},
                {"id": "sam", "name": "Sam", "color": "#E91E63", "allowance": 0},
            ],
            "rewards": [
                {
                    "id": "old",
                    "name": "Board game",
                    "points": 5,
                    "kind": "custom",
                    "members": [],
                },
                {"id": "tv", "name": "TV", "points": 5, "kind": "custom"},
                {
                    "id": "ice",
                    "name": "Ice cream",
                    "points": 5,
                    "kind": "custom",
                    "members": ["alex"],
                },
            ],
            "settings": {"streak_rule_from": "2026-11-01"},
        },
    }
    entry = await _setup(hass)
    by_id = {r["id"]: r["members"] for r in entry.runtime_data.rewards}
    assert by_id == {"old": [], "tv": None, "ice": ["alex"]}

    client = Client(await hass_ws_client(hass))
    await client.ok("adjust", member_id="alex", points=20)
    refused = await client("redeem", member_id="alex", reward_id="old")
    assert not refused["success"]
    assert "Nobody can get it" in refused["error"]["message"]
    await client.ok("redeem", member_id="alex", reward_id="tv")
    await client.ok("redeem", member_id="alex", reward_id="ice")
    refused = await client("redeem", member_id="sam", reward_id="ice")
    assert not refused["success"]
    assert refused["error"]["code"] == "invalid"


async def test_state_lists_every_reward_for_the_parents_screen(
    hass: HomeAssistant, client: Client
):
    """The snapshot keeps them all. Each page of the Family dashboard filters."""
    alex, sam = await _family(client)
    await _reward(client, name="Movie", points=1, kind="custom")
    await _reward(client, name="TV", points=1, kind="custom", members=[alex])
    await _reward(client, name="Old", points=1, kind="custom", members=[])
    state = await client.ok("state")
    assert [r["name"] for r in state["rewards"]] == ["Movie", "TV", "Old"]
    assert [r["name"] for r in model.rewards_for(state["rewards"], alex)] == [
        "Movie",
        "TV",
    ]
    assert [r["name"] for r in model.rewards_for(state["rewards"], sam)] == ["Movie"]
    assert [r["name"] for r in model.rewards_for(state["rewards"], None)] == ["Movie"]
