"""Rewards bought together: the points are held until a parent says yes."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_mock_service,
)

from homeassistant.core import Context, HomeAssistant
from tests.test_family import Client, _family, _setup, _tv_mgmt


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _points(client: Client) -> dict[str, int]:
    return {m["name"]: m["points"] for m in (await client.ok("state"))["members"]}


async def _reward(client: Client, **item) -> str:
    return (await client.ok("save", collection="rewards", item=item))["item"]["id"]


async def test_together_waits_for_a_parent_then_hands_out_once(
    hass: HomeAssistant, client
):
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=30)
    await client.ok("adjust", member_id=sam, points=8)
    pizza = await _reward(client, name="Pizza night", points=25, kind="custom")
    redeemed = async_capture_events(hass, "family_reward_redeemed")

    # Neither has enough alone; Sam puts in all 8 and Alex covers the rest.
    res = await client.ok("redeem", member_id=sam, reward_id=pizza, together=[alex])
    assert res["points"] == 0
    assert await _points(client) == {"Alex": 13, "Sam": 0}
    state = await client.ok("state")
    [request] = state["to_approve"]
    assert request["title"] == "Pizza night"
    assert request["points"] == 25
    assert {s["member"]: s["points"] for s in request["shares"]} == {alex: 17, sam: 8}
    assert state["to_give"] == []
    assert state["recent"][0]["given"] == "to_approve"

    await client.ok("approve", group_id=request["group"], approved=True)
    state = await client.ok("state")
    assert state["to_approve"] == []
    # Handed out once, for both.
    [give] = state["to_give"]
    assert set(give["together"]) == {alex, sam}
    assert await _points(client) == {"Alex": 13, "Sam": 0}
    assert sorted(e.data["points"] for e in redeemed) == [8, 17]
    assert {e.data["together"] for e in redeemed} == {"Sam and Alex"}

    await client.ok("given", entry_id=give["id"])
    state = await client.ok("state")
    assert state["to_give"] == []
    assert {e["given"] for e in state["history"] if e.get("group")} == {"given"}

    # Already answered.
    res = await client("approve", group_id=request["group"], approved=False)
    assert res["error"]["message"] == "Someone dealt with that already"


async def test_no_gives_the_points_back(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=10)
    await client.ok("adjust", member_id=sam, points=10)
    movie = await _reward(client, name="Movie", points=10, kind="custom")
    await client.ok("redeem", member_id=alex, reward_id=movie, together=[sam])
    assert await _points(client) == {"Alex": 5, "Sam": 5}
    [request] = (await client.ok("state"))["to_approve"]
    await client.ok("approve", group_id=request["group"], approved=False)
    state = await client.ok("state")
    assert state["to_approve"] == []
    assert not [e for e in state["history"] if e.get("group")]
    assert await _points(client) == {"Alex": 10, "Sam": 10}


async def test_together_needs_enough_points_and_someone_else(
    hass: HomeAssistant, client
):
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=5)
    await client.ok("adjust", member_id=sam, points=3)
    big = await _reward(client, name="Zoo trip", points=20, kind="custom")
    res = await client("redeem", member_id=alex, reward_id=big, together=[sam])
    assert (
        res["error"]["message"] == "Together they have 8 of the 20 points for Zoo trip"
    )
    res = await client("redeem", member_id=alex, reward_id=big, together=[alex])
    assert res["error"]["message"] == "Pick who's sharing it"
    await client.ok("adjust", member_id=sam, points=-3)
    small = await _reward(client, name="Sticker", points=2, kind="custom")
    res = await client("redeem", member_id=alex, reward_id=small, together=[sam])
    assert res["error"]["message"] == "Sam has no points to put in"


async def test_undo_takes_back_the_whole_request(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=4)
    await client.ok("adjust", member_id=sam, points=4)
    treat = await _reward(client, name="Treat", points=6, kind="custom")
    res = await client.ok("redeem", member_id=alex, reward_id=treat, together=[sam])
    await client.ok("undo", entry_id=res["entry"]["id"])
    state = await client.ok("state")
    assert state["to_approve"] == []
    assert await _points(client) == {"Alex": 4, "Sam": 4}


async def test_tv_time_together_is_given_when_a_parent_says_yes(
    hass: HomeAssistant, client
):
    tv, calls = await _tv_mgmt(hass)
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=10)
    await client.ok("adjust", member_id=sam, points=10)
    reward = await _reward(
        client, name="Movie night", points=20, kind="tv_time", tv=tv, minutes=90
    )
    await client.ok("redeem", member_id=alex, reward_id=reward, together=[sam])
    assert calls == []
    [request] = (await client.ok("state"))["to_approve"]
    await client.ok("approve", group_id=request["group"], approved=True)
    [call] = calls
    assert call.data["minutes"] == 90
    assert call.data["reason"] == "Alex and Sam's reward: Movie night"
    state = await client.ok("state")
    assert state["to_give"] == []
    # It can't be undone from the shared screen once a parent said yes.
    shares = [e for e in state["history"] if e.get("group")]
    res = await client("undo", entry_id=shares[0]["id"])
    assert not res["success"]


async def test_parents_say_yes_or_no_from_their_phones(
    hass: HomeAssistant, client, hass_admin_user, hass_read_only_user
):
    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    alex, sam = await _family(client)
    await client.ok(
        "settings", notify_targets=["mobile_app_dads_phone"], notify_rewards=True
    )
    await client.ok("adjust", member_id=alex, points=6)
    await client.ok("adjust", member_id=sam, points=6)
    game = await _reward(client, name="Game night", points=10, kind="custom")
    await client.ok("redeem", member_id=alex, reward_id=game, together=[sam])
    await hass.async_block_till_done()
    [note] = sent
    [request] = (await client.ok("state"))["to_approve"]
    group = request["group"]
    assert note.data["title"] == "Alex and Sam want Game night together"
    assert (
        note.data["message"] == "Points: Alex 5, Sam 5. They're held until you say yes."
    )
    assert [a["action"] for a in note.data["data"]["actions"]] == [
        f"FAMILY_YES_{group}",
        f"FAMILY_NO_{group}",
    ]

    # Not from someone who isn't a parent.
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"FAMILY_YES_{group}"},
        context=Context(user_id=hass_read_only_user.id),
    )
    await hass.async_block_till_done()
    assert (await client.ok("state"))["to_approve"]

    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"FAMILY_YES_{group}"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    state = await client.ok("state")
    assert state["to_approve"] == []
    assert state["to_give"][0]["title"] == "Game night"
    titles = [s.data.get("title") or s.data["message"] for s in sent]
    assert "clear_notification" in titles
    assert "Alex and Sam picked Game night" in titles
