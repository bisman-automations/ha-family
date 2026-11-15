"""2.12.0: paying for a trade, streak freezes, quests, statements, quiet
hours, pet care and wishlists."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from custom_components.family.statement import month_bounds, statement
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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


def _points(state, member_id):
    return next(m for m in state["members"] if m["id"] == member_id)["points"]


async def test_paying_for_a_trade(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Dishes", "points": 2, "members": [alex]},
        )
    )["item"]
    assert not (
        await client("trade/offer", member_id=alex, chore_id=chore["id"], pay=5)
    )["success"]
    await client.ok("adjust", member_id=alex, points=10, reason="Start")
    trade = (
        await client.ok("trade/offer", member_id=alex, chore_id=chore["id"], pay=5)
    )["trade"]
    assert trade["pay"] == 5
    await client.ok("trade/take", trade_id=trade["id"], member_id=sam)
    await client.ok("trade/decide", trade_id=trade["id"], approved=True)
    state = await client.ok("state")
    assert _points(state, alex) == 5 and _points(state, sam) == 5


async def test_streak_freeze(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    await client.ok(
        "save",
        collection="chores",
        item={"name": "Bed", "points": 1, "members": [alex]},
    )
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == alex)["freeze_offers"] == []
    await client.ok("settings", freeze_cost=3)
    await client.ok("adjust", member_id=alex, points=10, reason="Start")
    state = await client.ok("state")
    offers = next(m for m in state["members"] if m["id"] == alex)["freeze_offers"]
    today = dt_util.now().date().isoformat()
    assert today in offers
    assert not (await client("freeze", member_id=alex, day="2001-01-01"))["success"]
    await client.ok("freeze", member_id=alex, day=today)
    manager = _manager(hass)
    assert dt_util.now().date() in manager.frozen_days(alex)
    assert not manager._has_own(alex)(dt_util.now().date())  # noqa: SLF001 - a day off
    state = await client.ok("state")
    assert _points(state, alex) == 7
    # One a week.
    assert next(m for m in state["members"] if m["id"] == alex)["freeze_offers"] == []


async def test_quests(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    assert not (await client("quest/save", quest={"name": "Garage", "steps": []}))[
        "success"
    ]
    quest = (
        await client.ok(
            "quest/save",
            quest={
                "name": "Clear the garage",
                "emoji": "🧹",
                "steps": [
                    {"name": "Sort the toys", "points": 5},
                    {"name": "Sweep", "points": 3},
                ],
            },
        )
    )["quest"]
    await client.ok("quest/step", quest_id=quest["id"], member_id=alex)
    state = await client.ok("state")
    q = state["quests"][0]
    assert q["next"] == 1 and not q["finished"] and _points(state, alex) == 5
    await client.ok("quest/step", quest_id=quest["id"], member_id=sam)
    state = await client.ok("state")
    assert state["quests"][0]["finished"] and _points(state, sam) == 3
    assert not (await client("quest/step", quest_id=quest["id"], member_id=sam))[
        "success"
    ]
    await client.ok("quest/undo", quest_id=quest["id"])
    state = await client.ok("state")
    assert state["quests"][0]["next"] == 1 and _points(state, sam) == 0
    await client.ok("quest/delete", quest_id=quest["id"])
    assert (await client.ok("state"))["quests"] == []


def test_statement() -> None:
    assert month_bounds(date(2026, 1, 15), 1) == (date(2025, 12, 1), date(2026, 1, 1))
    assert month_bounds(date(2026, 12, 3), 0) == (date(2026, 12, 1), date(2027, 1, 1))
    entries = [
        {
            "member": "a",
            "at": "2026-10-30T10:00:00",
            "kind": "chore",
            "points": 4,
            "title": "Old",
        },
        {
            "member": "a",
            "at": "2026-11-02T10:00:00",
            "kind": "chore",
            "points": 5,
            "title": "Bed",
        },
        {
            "member": "a",
            "at": "2026-11-03T10:00:00",
            "kind": "reward",
            "points": -3,
            "title": "TV",
        },
        {
            "member": "a",
            "at": "2026-11-04T10:00:00",
            "kind": "give",
            "points": -1,
            "title": "Gave",
        },
        {
            "member": "a",
            "at": "2026-11-05T10:00:00",
            "kind": "penalty",
            "points": -2,
            "title": "Late",
        },
        {
            "member": "a",
            "at": "2026-11-06T10:00:00",
            "kind": "chore",
            "points": 9,
            "review": "rejected",
        },
        {"member": "b", "at": "2026-11-06T10:00:00", "kind": "chore", "points": 9},
    ]
    result = statement(entries, "a", 10, date(2026, 11, 1), date(2026, 12, 1))
    assert result["opening"] == 14
    assert (result["earned"], result["spent"], result["given"], result["taken"]) == (
        5,
        3,
        1,
        2,
    )
    assert result["closing"] == 13
    assert [line["title"] for line in result["lines"]] == ["Bed", "TV", "Gave", "Late"]


async def test_statement_and_quiet_hours(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    await client.ok("adjust", member_id=alex, points=4, reason="Helped")
    result = (await client.ok("statement", member_id=alex))["statement"]
    assert result["member"] == "Alex" and result["closing"] == 4
    await client.ok("settings", quiet_from="21:00", quiet_until="06:30")
    state = await client.ok("state")
    assert state["quiet"] == {"from": "21:00", "until": "06:30"}
    assert state["settings"]["quiet_from"] == "21:00"


async def test_pet_care(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    now = dt_util.now()
    soon = (now + timedelta(minutes=30)).strftime("%H:%M")
    later = (now + timedelta(hours=3)).strftime("%H:%M")
    if now.hour >= 20:
        return  # the times would wrap past midnight
    pet = (
        await client.ok(
            "pet/save",
            pet={"name": "Rex", "emoji": "🐶", "times": [soon, later], "points": 1},
        )
    )["pet"]
    await client.ok("pet/care", pet_id=pet["id"], slot=0, member_id=alex)
    result = await client("pet/care", pet_id=pet["id"], slot=0, member_id=sam)
    assert not result["success"] and "already" in result["error"]["message"]
    assert not (await client("pet/care", pet_id=pet["id"], slot=1, member_id=sam))[
        "success"
    ]  # not due yet
    state = await client.ok("state")
    slot = state["pets"][0]["slots"][0]
    assert slot["done_by"] == alex and slot["due"]
    # Undo frees the slot again.
    await client.ok("undo", entry_id=slot["entry"])
    state = await client.ok("state")
    assert state["pets"][0]["slots"][0]["done_by"] is None


async def test_wishlist(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    rewards = [
        (await client.ok("save", collection="rewards", item={"name": n, "points": 5}))[
            "item"
        ]
        for n in ("A", "B", "C", "D")
    ]
    for r in rewards[:3]:
        await client.ok("wish", member_id=alex, reward_id=r["id"], on=True)
    assert not (
        await client("wish", member_id=alex, reward_id=rewards[3]["id"], on=True)
    )["success"]
    await client.ok("wish", member_id=sam, reward_id=rewards[1]["id"], on=True)
    await client.ok("wish", member_id=alex, reward_id=rewards[0]["id"], on=False)
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == alex)["wishes"] == [
        rewards[1]["id"],
        rewards[2]["id"],
    ]
    assert state["most_wanted"][0] == {
        "reward_id": rewards[1]["id"],
        "members": [alex, sam],
    }
    # Editing the member keeps their wishes.
    await client.ok("save", collection="members", item={"id": alex, "name": "Alex"})
    state = await client.ok("state")
    assert len(next(m for m in state["members"] if m["id"] == alex)["wishes"]) == 2
