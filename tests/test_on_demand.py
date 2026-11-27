"""Chores that only come when a parent adds them (Add now)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.family import model
from homeassistant.core import HomeAssistant
from tests.test_family import Client, _family, _next, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _names(client: Client) -> list[str]:
    return [c["name"] for c in (await client.ok("state"))["chores"]]


async def test_a_chore_shows_only_after_a_parent_adds_it(
    hass: HomeAssistant, client, freezer
):
    freezer.move_to(_next(1, 9))
    alex, sam = await _family(client)
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Wash the car", "points": 10, "repeat": "on_demand"},
        )
    )["item"]
    assert chore["repeat"] == "on_demand"
    assert await _names(client) == []
    res = await client("complete", member_id=alex, chore_id=chore["id"])
    assert res["error"]["message"] == "Wash the car isn't for right now"
    assert (await client.ok("state"))["demand_showing"] == []

    # Add now: on the dashboard, for whoever's first.
    await client.ok("chore/offer", chore_id=chore["id"])
    assert await _names(client) == ["Wash the car"]
    assert (await client.ok("state"))["demand_showing"] == [chore["id"]]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    # Done once: nobody can do it again, and it's gone the next day.
    assert await _names(client) == []
    res = await client("complete", member_id=sam, chore_id=chore["id"])
    assert not res["success"]
    assert (await client.ok("state"))["demand_showing"] == [chore["id"]]
    freezer.tick(timedelta(days=1))
    assert (await client.ok("state"))["demand_showing"] == []

    # Added again: back once more. An edit keeps it out.
    await client.ok("chore/offer", chore_id=chore["id"])
    await client.ok(
        "save",
        collection="chores",
        item={**chore, "points": 12},
    )
    assert await _names(client) == ["Wash the car"]

    # Take back before anyone does it.
    await client.ok("chore/offer", chore_id=chore["id"], offer=False)
    assert await _names(client) == []


async def test_each_of_its_people_does_it_once(hass: HomeAssistant, client, freezer):
    freezer.move_to(_next(2, 9))
    alex, sam = await _family(client)
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={
                "name": "Rake leaves",
                "points": 5,
                "repeat": "on_demand",
                "members": [alex, sam],
            },
        )
    )["item"]
    await client.ok("chore/offer", chore_id=chore["id"])
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    state = await client.ok("state")
    [row] = state["chores"]
    assert row["can"] == [sam]
    await client.ok("complete", member_id=sam, chore_id=chore["id"])
    assert await _names(client) == []


async def test_only_parents_add_and_only_these_chores(
    hass: HomeAssistant, client, hass_admin_user
):
    alex, _sam = await _family(client)
    daily = (
        await client.ok("save", collection="chores", item={"name": "Bed", "points": 1})
    )["item"]
    res = await client("chore/offer", chore_id=daily["id"])
    assert res["error"]["message"] == "Bed comes back by itself"
    res = await client("chore/offer", chore_id="nope")
    assert not res["success"]
    hass_admin_user.groups = []
    res = await client("chore/offer", chore_id=daily["id"])
    assert not res["success"]


def test_demand_showing() -> None:
    now = model.datetime(2026, 11, 27, 12, 0)
    chore = {"id": "c", "repeat": "on_demand", "members": ["a", "b"]}
    assert not model.demand_showing(chore, [], now)
    chore["offered"] = "2026-11-26T08:00:00"
    entry = {"kind": "chore", "chore_id": "c", "member": "a", "review": "pending"}
    assert model.demand_showing(chore, [dict(entry, at="2026-11-26T09:00:00")], now)
    done = [
        dict(entry, at="2026-11-26T09:00:00"),
        dict(entry, member="b", at="2026-11-26T10:00:00"),
    ]
    assert not model.demand_showing(chore, done, now)  # finished yesterday
    today = [dict(e, at="2026-11-27T10:00:00") for e in done]
    assert model.demand_showing(chore, today, now)  # finished today: still shown
    rejected = [dict(done[0]), dict(done[1], review="rejected")]
    assert model.demand_showing(chore, rejected, now)  # didn't happen: back
    old = [dict(e, at="2026-11-25T10:00:00") for e in done]
    assert model.demand_showing(chore, old, now)  # done before it was put out
