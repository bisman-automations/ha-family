"""Routines: step-by-step checklists."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from tests.test_family import Client, _family, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _routine(client: Client, **item) -> dict:
    return (
        await client.ok(
            "save",
            collection="routines",
            item={
                "name": "Morning",
                "emoji": "🌅",
                "points": 3,
                "steps": ["Get dressed", " Brush teeth ", "", "Make the bed"],
                **item,
            },
        )
    )["item"]


async def test_routine_steps_and_finish(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    done = []
    hass.bus.async_listen("family_chore_done", done.append)
    routine = await _routine(client, members=[alex])
    assert routine["steps"] == ["Get dressed", "Brush teeth", "Make the bed"]

    state = await client.ok("state")
    [today] = state["routines"]
    assert today["who"] == [alex] and today["ticked"] == {alex: []}

    # Only its people, and only real steps.
    res = await client(
        "routine/step", routine_id=routine["id"], member_id=sam, step=0, done=True
    )
    assert not res["success"]
    res = await client(
        "routine/step", routine_id=routine["id"], member_id=alex, step=9, done=True
    )
    assert not res["success"]

    step = lambda n, on=True: client.ok(  # noqa: E731
        "routine/step", routine_id=routine["id"], member_id=alex, step=n, done=on
    )
    assert (await step(0))["ticked"] == [0]
    assert (await step(2))["ticked"] == [0, 2]
    assert (await step(2, False))["ticked"] == [0]
    assert "entry" not in await step(2)
    finished = await step(1)
    assert finished["entry"]["title"] == "Morning" and finished["entry"]["points"] == 3
    await hass.async_block_till_done()
    assert done and done[0].data["routine"] is True

    state = await client.ok("state")
    [today] = state["routines"]
    assert today["finished"] == [alex]
    assert next(m for m in state["members"] if m["id"] == alex)["points"] == 3
    # It waits for a parent like a chore.
    assert any(e.get("routine_id") == routine["id"] for e in state["to_check"])
    # Finished: no more ticking today.
    res = await client(
        "routine/step", routine_id=routine["id"], member_id=alex, step=0, done=False
    )
    assert not res["success"]


async def test_routine_for_everyone_and_editing(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    routine = await _routine(client, points=0)
    [today] = (await client.ok("state"))["routines"]
    assert sorted(today["who"]) == sorted([alex, sam])

    res = await client(
        "save", collection="routines", item={"name": "Empty", "steps": []}
    )
    assert not res["success"]

    # Not today: not shown.
    await client.ok(
        "save", collection="routines", item={**routine, "days": [], "enabled": False}
    )
    assert (await client.ok("state"))["routines"] == []
    assert len((await client.ok("state"))["all_routines"]) == 1

    # A member removed is dropped from it.
    await client.ok("save", collection="routines", item={**routine, "members": [alex]})
    await client.ok("delete", collection="members", item_id=alex)
    [saved] = (await client.ok("state"))["all_routines"]
    assert saved["members"] == []
    await client.ok("delete", collection="routines", item_id=routine["id"])
    assert (await client.ok("state"))["all_routines"] == []
