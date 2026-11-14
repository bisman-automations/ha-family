"""A hold on someone's rewards: chores still earn points, spending waits."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from custom_components.family import model
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from tests.test_family import Client, _family, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


def _member(state: dict, member_id: str) -> dict:
    return next(m for m in state["members"] if m["id"] == member_id)


async def _reward(client: Client, **item) -> str:
    return (
        await client.ok(
            "save",
            collection="rewards",
            item={"name": "Ice cream", "points": 5, **item},
        )
    )["item"]["id"]


def test_hold_end():
    now = datetime(2026, 11, 14, 9, 30, tzinfo=dt_util.get_default_time_zone())
    assert model.hold_end(now, 0, None) == now.replace(day=15, hour=0, minute=0)
    assert model.hold_end(now, 3, None) == now + timedelta(days=3)
    assert model.hold_end(now, None, date(2026, 11, 20)) == now.replace(
        day=21, hour=0, minute=0
    )
    with pytest.raises(ValueError):
        model.hold_end(now, None, date(2026, 11, 13))
    with pytest.raises(ValueError):
        model.hold_end(now, 91, None)
    assert model.held_until({"rewards_held_until": None}, now) is None
    later = (now + timedelta(hours=1)).isoformat()
    assert model.held_until({"rewards_held_until": later}, now) is not None
    assert (
        model.held_until({"rewards_held_until": later}, now + timedelta(hours=2))
        is None
    )


async def test_a_hold_stops_spending_until_it_ends(
    hass: HomeAssistant, client, freezer
):
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=20)
    await client.ok("adjust", member_id=sam, points=20)
    reward = await _reward(client)
    events = []
    hass.bus.async_listen("family_rewards_held", events.append)

    res = await client.ok("hold", member_id=alex, days=2, reason="Talking back")
    assert res["member"]["hold_reason"] == "Talking back"
    state = await client.ok("state")
    assert _member(state, alex)["held_until"]
    assert _member(state, sam)["held_until"] is None
    assert events[0].data["member"] == "Alex"

    refused = await client("redeem", member_id=alex, reward_id=reward)
    assert not refused["success"]
    assert "on hold" in refused["error"]["message"]
    assert "Talking back" in refused["error"]["message"]
    together = await client("redeem", member_id=sam, reward_id=reward, together=[alex])
    assert not together["success"]
    # Others aren't held.
    await client.ok("redeem", member_id=sam, reward_id=reward)
    # Editing the member keeps the hold.
    await client.ok("save", collection="members", item={"id": alex, "name": "Alex"})
    assert _member(await client.ok("state"), alex)["held_until"]

    freezer.tick(timedelta(days=2, minutes=1))
    assert _member(await client.ok("state"), alex)["held_until"] is None
    await client.ok("redeem", member_id=alex, reward_id=reward)


async def test_lifting_a_hold(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=20)
    reward = await _reward(client)
    await client.ok("hold", member_id=alex, days=0)
    assert not (await client("redeem", member_id=alex, reward_id=reward))["success"]
    await client.ok("hold", member_id=alex, lift=True)
    await client.ok("redeem", member_id=alex, reward_id=reward)


async def test_a_hold_needs_a_day_ahead(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    res = await client("hold", member_id=alex, until="2000-01-01")
    assert not res["success"]
