"""Assist voice, badges, trading chores, cashing out and week by week."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.family import model
from custom_components.family.const import DOMAIN
from custom_components.family.voice import find_chore, find_member
from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from .test_family import Client, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _chore(client: Client, name: str, members: list[str], points: int = 5) -> str:
    item = {"name": name, "points": points, "repeat": "daily", "members": members}
    return (await client.ok("save", collection="chores", item=item))["item"]["id"]


async def _members(client: Client, *names: str) -> list[str]:
    return [
        (await client.ok("save", collection="members", item={"name": n}))["item"]["id"]
        for n in names
    ]


def test_find_member_and_chore() -> None:
    members = [{"id": "a", "name": "Alex Sample"}, {"id": "s", "name": "Sam"}]
    assert find_member(members, "alex")["id"] == "a"
    assert find_member(members, "Sam's")["id"] == "s"
    assert find_member(members, "Riley") is None
    chores = [{"id": "1", "name": "Feed the dog"}, {"id": "2", "name": "Make your bed"}]
    assert find_chore(chores, "feed the dog")["id"] == "1"
    assert find_chore(chores, "the dog")["id"] == "1"
    assert find_chore(chores, "make my bed")["id"] == "2"
    assert find_chore(chores, "mow the lawn") is None


async def test_voice(hass: HomeAssistant, hass_ws_client, hass_admin_user) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    await _setup(hass)
    family = Client(await hass_ws_client(hass))
    alex, sam = await _members(family, "Alex", "Sam")
    await _chore(family, "Feed the dog", [alex])
    await _chore(family, "Make your bed", [alex, sam], points=3)

    async def say(text: str, user_id: str | None = None) -> str:
        result = await conversation.async_converse(
            hass, text, None, Context(user_id=user_id), language="en"
        )
        return result.response.speech["plain"]["speech"]

    assert await say("what does Alex have left") == (
        "Alex has 2 chores left: Feed the dog and Make your bed."
    )
    reply = await say("Alex finished feed the dog")
    assert reply.startswith("Nice, Alex! Feed the dog is done, +5 points.")
    assert "A parent will check it." in reply
    assert "First chore" in reply
    assert await say("how many points does Alex have") == "Alex has 5 points."
    assert await say("what does Alex have left") == (
        "Alex has 1 chore left: Make your bed."
    )
    assert "couldn't find mow the lawn" in await say("Sam did mow the lawn")
    assert "couldn't find Riley" in await say("how many points does Riley have")
    # "I" with nobody linked to this login.
    assert "Say your name" in await say("how many points do I have")

    # "I" is whoever is logged in, through their person.
    hass.states.async_set("person.alex", "home", {"user_id": hass_admin_user.id})
    await family.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "person": "person.alex"},
    )
    assert (
        await say("how many points do I have", hass_admin_user.id)
        == "Alex has 5 points."
    )


async def test_badges(hass: HomeAssistant, client) -> None:
    events = []
    hass.bus.async_listen("family_badge_earned", events.append)
    (alex,) = await _members(client, "Alex")
    chore = await _chore(client, "Feed the dog", [alex])
    done = await client.ok("complete", member_id=alex, chore_id=chore)
    keys = {b["key"] for b in done["badges"]}
    assert "first_chore" in keys
    assert "all_done" in keys
    assert {e.data["badge"] for e in events} >= {"first_chore", "all_done"}
    state = await client.ok("state")
    badges = state["members"][0]["badges"]
    assert [b["key"] for b in badges][:1] == ["first_chore"]
    assert badges[0]["emoji"] == "🌱"
    # Saving the member keeps them.
    await client.ok("save", collection="members", item={"id": alex, "name": "Alex"})
    state = await client.ok("state")
    assert state["members"][0]["badges"]


def test_badges_earned_model() -> None:
    entries = [{"member": "a", "kind": "chore", "points": 1} for _ in range(10)] + [
        {"member": "a", "kind": "chore", "points": 1, "review": "rejected"},
        {"member": "a", "kind": "reward", "points": -5, "given": "to_give"},
        {"member": "b", "kind": "cashout", "points": -5},
    ]
    assert model.badges_earned(entries, "a", 7) == {
        "first_chore",
        "chores_10",
        "streak_3",
        "streak_7",
        "first_reward",
    }
    assert model.badges_earned(entries, "b", 0) == {"cashed_out"}
    assert [
        b["key"] for b in model.badge_list({"streak_7": "x", "first_chore": "y"})
    ] == [
        "first_chore",
        "streak_7",
    ]


async def test_trading_a_chore(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    chore = await _chore(client, "Feed the dog", [alex])
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))

    # Only your own chores.
    res = await kiosk("trade/offer", member_id=sam, chore_id=chore)
    assert not res["success"]
    trade = (await kiosk.ok("trade/offer", member_id=alex, chore_id=chore))["trade"]
    assert trade["status"] == "offered"
    res = await kiosk("trade/take", trade_id=trade["id"], member_id=alex)
    assert not res["success"]
    await kiosk.ok("trade/take", trade_id=trade["id"], member_id=sam)
    # Still Alex's until a parent says yes; the shared screen can't.
    state = await client.ok("state")
    assert [c["can"] for c in state["chores"]] == [[alex]]
    res = await kiosk("trade/decide", trade_id=trade["id"], approved=True)
    assert res["error"]["code"] == "unauthorized"
    await client.ok("trade/decide", trade_id=trade["id"], approved=True)
    state = await client.ok("state")
    assert [c["can"] for c in state["chores"]] == [[sam]]
    assert state["trades"][0]["status"] == "approved"
    done = await kiosk.ok("complete", member_id=sam, chore_id=chore)
    assert done["points"] == 5
    res = await kiosk("trade/cancel", trade_id=trade["id"])
    assert not res["success"]

    # Tomorrow it's Alex's again.
    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    for t in manager.trades._items:
        t["day"] = (dt_util.now().date() - timedelta(days=1)).isoformat()
    state = await client.ok("state")
    assert state["trades"] == []


async def test_cant_take_a_chore_you_have(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    chore = await _chore(client, "Make your bed", [alex, sam])
    trade = (await client.ok("trade/offer", member_id=alex, chore_id=chore))["trade"]
    res = await client("trade/take", trade_id=trade["id"], member_id=sam)
    assert res["error"]["message"] == "You already have that chore today"


async def test_trade_no_and_cancel(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    chore = await _chore(client, "Feed the dog", [alex])
    trade = (await client.ok("trade/offer", member_id=alex, chore_id=chore, to=sam))[
        "trade"
    ]
    await client.ok("trade/cancel", trade_id=trade["id"])
    assert (await client.ok("state"))["trades"] == []
    trade = (await client.ok("trade/offer", member_id=alex, chore_id=chore))["trade"]
    await client.ok("trade/take", trade_id=trade["id"], member_id=sam)
    await client.ok("trade/decide", trade_id=trade["id"], approved=False)
    state = await client.ok("state")
    assert state["trades"] == []
    assert [c["can"] for c in state["chores"]] == [[alex]]


async def test_cash_out(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
) -> None:
    sent = async_mock_service(hass, "notify", "mobile_app_parent")
    await client.ok(
        "settings", notify_targets=["mobile_app_parent"], notify_rewards=True
    )
    (alex,) = await _members(client, "Alex")
    await client.ok("adjust", member_id=alex, points=40)
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    res = await kiosk("cash_out", member_id=alex, points=10)
    assert "point value" in res["error"]["message"]
    await client.ok("settings", point_value=0.25, currency="$")
    res = await kiosk("cash_out", member_id=alex, points=100)
    assert res["error"]["message"] == "Only 40 points to cash out"
    out = await kiosk.ok("cash_out", member_id=alex, points=20)
    assert out["points"] == 20
    assert out["entry"]["money"] == 5.0
    assert out["entry"]["title"] == "Cash out $5.00"
    assert "cashed_out" in {b["key"] for b in out["badges"]}
    await hass.async_block_till_done()
    assert sent[-1].data["title"] == "Alex picked Cash out $5.00"
    state = await client.ok("state")
    assert [e["id"] for e in state["to_give"]] == [out["entry"]["id"]]
    # A parent says no: the points go back.
    res = await kiosk("cash_out/cancel", entry_id=out["entry"]["id"])
    assert res["error"]["code"] == "unauthorized"
    await client.ok("cash_out/cancel", entry_id=out["entry"]["id"])
    state = await client.ok("state")
    assert state["members"][0]["points"] == 40
    # Paid: marked handed out.
    out = await kiosk.ok("cash_out", member_id=alex, points=8)
    await client.ok("given", entry_id=out["entry"]["id"])
    assert (await client.ok("state"))["to_give"] == []


def test_weekly_stats() -> None:
    today = date(2026, 11, 13)  # a Friday

    def at(days: int) -> str:
        return f"{(today - timedelta(days=days)).isoformat()}T12:00:00+00:00"

    entries: list[dict[str, Any]] = [
        {"member": "a", "kind": "chore", "points": 5, "at": at(0)},
        {
            "member": "a",
            "kind": "chore",
            "points": 5,
            "at": at(1),
            "review": "rejected",
        },
        {"member": "a", "kind": "reward", "points": -20, "at": at(2)},
        {"member": "a", "kind": "allowance", "points": 10, "at": at(8)},
        {"member": "a", "kind": "cashout", "points": -4, "at": at(8)},
        {"member": "a", "kind": "chore", "points": 3, "at": at(100)},
    ]
    weeks = model.weekly_stats(entries, ["a"], today, weeks=3)
    assert [w["week"] for w in weeks] == ["2026-10-26", "2026-11-02", "2026-11-09"]
    assert weeks[-1]["members"]["a"] == {"earned": 5, "spent": 20, "chores": 1}
    assert weeks[-2]["members"]["a"] == {"earned": 10, "spent": 4, "chores": 0}
    assert weeks[0]["members"]["a"] == {"earned": 0, "spent": 0, "chores": 0}


async def test_weeks_for_parents_only(
    hass: HomeAssistant, client, hass_ws_client, hass_read_only_access_token
) -> None:
    await _members(client, "Alex")
    assert len((await client.ok("state"))["weeks"]) == 8
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    assert "weeks" not in await kiosk.ok("state")
