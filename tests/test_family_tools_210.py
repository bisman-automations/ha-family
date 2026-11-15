"""2.10.0: fair turns, a parent's match, screen time chores unlock, chore
instructions, doing a chore together, and the family meeting."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta

import pytest

from custom_components.family import model
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from .test_family import Client, _setup

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0fake").decode()


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _members(client: Client, *names: str) -> list[str]:
    return [
        (await client.ok("save", collection="members", item={"name": n}))["item"]["id"]
        for n in names
    ]


def test_fair_turns_split_and_match() -> None:
    now = datetime(2026, 11, 15, 12, tzinfo=dt_util.UTC)
    entries = [
        {
            "member": "a",
            "kind": "chore",
            "chore_id": "c",
            "at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "member": "a",
            "kind": "chore",
            "chore_id": "c",
            "at": (now - timedelta(days=2)).isoformat(),
        },
        {
            "member": "b",
            "kind": "chore",
            "chore_id": "c",
            "at": (now - timedelta(days=3)).isoformat(),
        },
        {
            "member": "c",
            "kind": "chore",
            "chore_id": "c",
            "at": (now - timedelta(days=4)).isoformat(),
        },
        {
            "member": "c",
            "kind": "chore",
            "chore_id": "c",
            "at": (now - timedelta(days=60)).isoformat(),
        },
        {
            "member": "b",
            "kind": "chore",
            "chore_id": "c",
            "at": now.isoformat(),
            "review": "rejected",
        },
    ]
    # b and c did it once lately; c longest ago.
    assert model.fair_member("c", ["a", "b", "c"], entries, now) == "c"
    assert model.fair_member("c", ["a", "b", "d"], entries, now) == "d"
    chore = {"id": "c", "turns": True, "members": ["a", "b", "c"], "turn_every": "fair"}
    assert model.turn_member(chore, entries, now) == "c"
    assert model.split_evenly(5, ["a", "b"]) == {"a": 3, "b": 2}
    assert model.split_evenly(5, []) == {}
    assert model.match_points(100, 25) == 20
    assert model.match_points(100, 0) == 0
    assert model.match_points(7, 50) == 2


async def test_fair_turns_from_the_editor(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={
                "name": "Bins",
                "points": 2,
                "members": [alex, sam],
                "turns": True,
                "turn_every": "fair",
            },
        )
    )["item"]
    state = await client.ok("state")
    bins = next(c for c in state["chores"] if c["id"] == chore["id"])
    assert bins["turn"] == alex
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    # Tomorrow it's Sam's: Alex has done it lately, Sam hasn't.
    assert (await client.ok("state"))["tomorrow"]["chores"][sam][0]["id"] == chore["id"]


async def test_a_parent_matches_saving_up(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    reward = (
        await client.ok(
            "save", collection="rewards", item={"name": "Bike", "points": 100}
        )
    )["item"]
    await client.ok("settings", goal_match=25)
    await client.ok("adjust", member_id=alex, points=80)
    res = await client("redeem", member_id=alex, reward_id=reward["id"])
    assert "100 points" in res["error"]["message"]  # not saving for it: no match
    await client.ok("goal", member_id=alex, reward_id=reward["id"])
    state = await client.ok("state")
    assert state["goal_match"] == 25
    done = await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert done["entry"]["match"] == 20
    assert done["points"] == 0
    history = (await client.ok("state"))["history"]
    assert any(e.get("bonus") == "match" and e["points"] == 20 for e in history)


async def test_own_chores_unlock_screen_time(hass: HomeAssistant, client) -> None:
    grants: list[ServiceCall] = []

    async def grant(call: ServiceCall) -> None:
        grants.append(call)

    hass.services.async_register("tv_mgmt", "grant_extension", grant)
    (alex,) = await _members(client, "Alex")
    await client.ok(
        "save",
        collection="members",
        item={
            "id": alex,
            "name": "Alex",
            "unlock_tv": "tv_entry",
            "unlock_minutes": 30,
        },
    )
    res = await client(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "unlock_tv": "tv", "unlock_minutes": 0},
    )
    assert not res["success"]
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Bed", "points": 1, "members": [alex]},
        )
    )["item"]
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await hass.async_block_till_done()
    assert (
        grants
        and grants[0].data["minutes"] == 30
        and grants[0].data["profile_id"] == "tv_entry"
    )
    assert "📺 +30 min" in next(
        b["title"] for b in done["entry"]["bonuses"] if b["bonus"] == "all_done"
    )
    await client.ok("undo", entry_id=done["entry"]["id"])
    assert grants[-1].data["minutes"] == -30


async def test_chore_instructions_and_example(hass: HomeAssistant, client) -> None:
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={
                "name": "Bed",
                "points": 1,
                "how": "Pillow on top.\\nBlanket straight.",
            },
        )
    )["item"]
    assert chore["how"].startswith("Pillow")
    assert (await client.ok("chore/example", chore_id=chore["id"]))["url"] is None
    await client.ok("chore/set_example", chore_id=chore["id"], photo=JPEG)
    assert (await client.ok("chore/example", chore_id=chore["id"]))["url"] == JPEG
    state = await client.ok("state")
    assert (
        next(c for c in state["all_chores"] if c["id"] == chore["id"])["example"]
        is True
    )
    # Saving the chore again keeps its example.
    saved = (await client.ok("save", collection="chores", item={**chore, "how": "x"}))[
        "item"
    ]
    assert saved["example"] is True
    await client.ok("chore/set_example", chore_id=chore["id"], photo=None)
    assert (await client.ok("chore/example", chore_id=chore["id"]))["url"] is None
    res = await client("chore/set_example", chore_id="nope", photo=None)
    assert not res["success"]


async def test_a_chore_done_together(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Garage", "points": 5, "members": [alex]},
        )
    )["item"]
    done = await client.ok(
        "complete", member_id=alex, chore_id=chore["id"], helpers=[sam]
    )
    assert done["entry"]["points"] == 3 and done["entry"]["together"] == [alex, sam]
    state = await client.ok("state")
    points = {m["id"]: m["points"] for m in state["members"]}
    assert points == {alex: 3, sam: 2}
    helped = next(e for e in state["to_check"] if e["member"] == sam)
    assert helped["title"] == "Garage (with Alex)"
    await client.ok("undo", entry_id=done["entry"]["id"])
    assert {m["id"]: m["points"] for m in (await client.ok("state"))["members"]} == {
        alex: 0,
        sam: 0,
    }


async def test_family_meeting(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Bed", "points": 1, "members": [alex]},
        )
    )["item"]
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await client.ok(
        "review", entry_id=done["entry"]["id"], approved=False, reason="Not done"
    )
    report = (await client.ok("report"))["report"]
    me = report["members"][0]
    assert me["didnt"][0]["title"] == "Bed" and me["didnt"][0]["reason"] == "Not done"
    assert me["next_week"] == ["Bed"]
