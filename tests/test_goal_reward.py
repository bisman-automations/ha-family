"""2.19.0: a family goal can unlock a reward, used once when it's reached."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant, ServiceCall

from .test_family import Client, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _members(client: Client, *names: str) -> list[str]:
    return [
        (await client.ok("save", collection="members", item={"name": n}))["item"]["id"]
        for n in names
    ]


def _manager(hass: HomeAssistant):
    return hass.config_entries.async_entries("family")[0].runtime_data


async def _reward(client: Client, **item) -> dict:
    return (await client.ok("save", collection="rewards", item=item))["item"]


async def _goal(client: Client) -> dict:
    return next(iter((await client.ok("state"))["family_goals"]))


async def test_reached_goal_unlocks_its_reward_once(
    hass: HomeAssistant, client
) -> None:
    alex, sam, mom = await _members(client, "Alex", "Sam", "Mom")
    _manager(hass).parent_ids = {mom}
    treat = await _reward(client, name="McDonald's", points=300, kind="custom")
    goal = (
        await client.ok(
            "family_goal/save",
            name="Kids McDonald's night",
            target=5,
            kids=True,
            reward=treat["id"],
        )
    )["goal"]
    assert goal["reward"] == treat["id"]

    # Locked until it's reached.
    view = await _goal(client)
    assert view["reward"]["name"] == "McDonald's" and not view["reached"]
    res = await client("family_goal/claim", goal_id=goal["id"], member_id=alex)
    assert not res["success"] and "isn't reached" in res["error"]["message"]

    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Table", "points": 5, "members": [alex]},
        )
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    assert (await _goal(client))["reached"]

    # The kids' goal: not Mom's to use.
    res = await client("family_goal/claim", goal_id=goal["id"], member_id=mom)
    assert not res["success"]

    before = next(m for m in (await client.ok("state"))["members"] if m["id"] == sam)[
        "points"
    ]
    entry = (await client.ok("family_goal/claim", goal_id=goal["id"], member_id=sam))[
        "entry"
    ]
    assert entry["points"] == 0 and entry["given"] == "to_give"
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == sam)["points"] == before
    view = next(g for g in state["family_goals"] if g["id"] == goal["id"])
    assert view["reward_used_by"] == sam
    # It waits for a parent to hand it out, like any reward.
    assert any(e["id"] == entry["id"] for e in state["to_give"])

    # Once only.
    res = await client("family_goal/claim", goal_id=goal["id"], member_id=alex)
    assert not res["success"] and "used already" in res["error"]["message"]

    # Undo puts it back.
    await client.ok("undo", entry_id=entry["id"])
    assert (await _goal(client))["reward_used_by"] is None
    await client.ok("family_goal/claim", goal_id=goal["id"], member_id=alex)

    # Starting the goal again locks it until it's reached again.
    await client.ok(
        "family_goal/save",
        item_id=goal["id"],
        name="Kids McDonald's night",
        target=5,
        kids=True,
        reward=treat["id"],
        restart=True,
    )
    view = await _goal(client)
    assert not view["reached"] and view["reward_used_by"] is None


async def test_tv_time_reward_is_given_straight_away(
    hass: HomeAssistant, client
) -> None:
    (alex,) = await _members(client, "Alex")
    tv = MockConfigEntry(domain="tv_mgmt", title="Family Room TV")
    tv.add_to_hass(hass)
    calls: list[ServiceCall] = []

    async def grant(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("tv_mgmt", "grant_extension", grant)
    movie = await _reward(
        client,
        name="Movie time",
        points=100,
        kind="tv_time",
        tv=tv.entry_id,
        minutes=60,
        whole_home=False,
    )
    goal = (
        await client.ok(
            "family_goal/save", name="Movie night", target=1, reward=movie["id"]
        )
    )["goal"]
    chore = (
        await client.ok("save", collection="chores", item={"name": "Bed", "points": 1})
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    entry = (await client.ok("family_goal/claim", goal_id=goal["id"], member_id=alex))[
        "entry"
    ]
    assert entry["given"] == "given" and entry["minutes"] == 60
    assert calls and calls[0].data["minutes"] == 60


async def test_deleting_the_reward_or_saving_without_one(
    hass: HomeAssistant, client
) -> None:
    (alex,) = await _members(client, "Alex")
    treat = await _reward(client, name="Ice cream", points=10, kind="custom")
    res = await client("family_goal/save", name="Party", target=1, reward="missing")
    assert not res["success"]
    goal = (
        await client.ok("family_goal/save", name="Party", target=1, reward=treat["id"])
    )["goal"]
    await client.ok("delete", collection="rewards", item_id=treat["id"])
    assert (await _goal(client))["reward"] is None
    res = await client("family_goal/claim", goal_id=goal["id"], member_id=alex)
    assert not res["success"] and "no reward" in res["error"]["message"]
    plain = (await client.ok("family_goal/save", name="Picnic", target=1))["goal"]
    assert plain["reward"] is None


async def test_one_each_and_parents_are_told(hass: HomeAssistant, client) -> None:
    from pytest_homeassistant_custom_component.common import async_mock_service

    sent = async_mock_service(hass, "notify", "mobile_app_parent")
    await client.ok(
        "settings", notify_targets=["mobile_app_parent"], notify_rewards=True
    )
    alex, sam = await _members(client, "Alex", "Sam")
    treat = await _reward(client, name="Ice cream", points=20, kind="custom")
    goal = (
        await client.ok(
            "family_goal/save",
            name="Clean week",
            target=2,
            members=[alex, sam],
            reward=treat["id"],
            reward_each=True,
        )
    )["goal"]
    assert goal["reward_each"]
    chore = (
        await client.ok("save", collection="chores", item={"name": "Bed", "points": 2})
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await hass.async_block_till_done()
    told = [c for c in sent if c.data["title"] == "Goal reached: Clean week"]
    assert len(told) == 1
    assert "Each of them can use it once" in told[0].data["message"]

    await client.ok("family_goal/claim", goal_id=goal["id"], member_id=alex)
    res = await client("family_goal/claim", goal_id=goal["id"], member_id=alex)
    assert (
        not res["success"]
        and "Alex used Ice cream already" in (res["error"]["message"])
    )
    await client.ok("family_goal/claim", goal_id=goal["id"], member_id=sam)
    view = await _goal(client)
    assert view["reward_each"] and view["reward_used"] == [alex, sam]

    # Told once, not on every change after.
    await client.ok("adjust", member_id=alex, points=1, reason="x")
    await hass.async_block_till_done()
    assert len([c for c in sent if c.data["title"].startswith("Goal reached")]) == 1


async def test_no_reward_no_notice(hass: HomeAssistant, client) -> None:
    from pytest_homeassistant_custom_component.common import async_mock_service

    sent = async_mock_service(hass, "notify", "mobile_app_parent")
    await client.ok(
        "settings", notify_targets=["mobile_app_parent"], notify_rewards=True
    )
    (alex,) = await _members(client, "Alex")
    await client.ok("family_goal/save", name="Picnic", target=1, reward_each=True)
    chore = (
        await client.ok("save", collection="chores", item={"name": "Bed", "points": 1})
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await hass.async_block_till_done()
    assert not [c for c in sent if c.data["title"].startswith("Goal reached")]
    assert (await _goal(client))["reward_each"] is False
