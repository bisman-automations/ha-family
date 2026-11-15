"""2.9.0: chore photos, a chore's own streak, picking chores from a pool,
chores a device finishes, and money owed."""

from __future__ import annotations

import base64
from datetime import date, timedelta

import pytest

from custom_components.family import model
from homeassistant.core import Context, HomeAssistant
from homeassistant.util import dt as dt_util

from .test_family import Client, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0fake").decode()


async def _members(client: Client, *names: str) -> list[str]:
    return [
        (await client.ok("save", collection="members", item={"name": n}))["item"]["id"]
        for n in names
    ]


async def _chore(client: Client, **item) -> dict:
    return (await client.ok("save", collection="chores", item={"points": 2, **item}))[
        "item"
    ]


def test_chore_streak_and_owed() -> None:
    today = date(2026, 11, 15)
    entries = [
        {
            "member": "a",
            "kind": "chore",
            "chore_id": "c",
            "at": f"{today - timedelta(days=d)}T08:00:00",
        }
        for d in (0, 1, 2, 4)
    ]
    assert model.chore_streak(entries, "a", "c", today) == 3
    entries[1]["review"] = "rejected"
    assert model.chore_streak(entries, "a", "c", today) == 1
    assert model.chore_streak(entries, "b", "c", today) == 0
    weekly = [
        {"member": "a", "kind": "chore", "chore_id": "w", "at": "2026-11-10T08:00:00"},
        {"member": "a", "kind": "chore", "chore_id": "w", "at": "2026-11-05T08:00:00"},
    ]
    assert model.chore_streak(weekly, "a", "w", today, weekly=True) == 2
    assert model.next_picker(["a", "b"], {"x": "a"}, {"x": 5}) == "b"
    assert model.next_picker(["a", "b"], {}, {}) == "a"
    assert model.next_picker([], {}, {}) is None
    owed = model.money_owed(
        [
            {"member": "a", "kind": "cashout", "given": "to_give", "money": 1.5},
            {"member": "a", "kind": "cashout", "given": "to_give", "money": 2},
            {"member": "a", "kind": "cashout", "given": "given", "money": 9},
        ]
    )
    assert owed == {"a": 3.5}
    assert model.clean_photo("need") == "need"
    assert model.clean_photo("sometimes") == ""


async def test_photo_proof(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    chore = await _chore(client, name="Tidy room", photo="need", members=[alex])
    res = await client("complete", member_id=alex, chore_id=chore["id"])
    assert "photo" in res["error"]["message"]
    res = await client(
        "complete",
        member_id=alex,
        chore_id=chore["id"],
        photo="data:image/png;base64,AAAA",
    )
    assert not res["success"]
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"], photo=JPEG)
    assert done["entry"]["photo"] is True
    photo = await client.ok("photo", entry_id=done["entry"]["id"])
    assert photo["url"] == JPEG
    # Undone: the photo goes too.
    await client.ok("undo", entry_id=done["entry"]["id"])
    assert (await client.ok("photo", entry_id=done["entry"]["id"]))["url"] is None
    res = await client("photo", entry_id="../x")
    assert not res["success"]


async def test_chore_streak_bonus(hass: HomeAssistant, client, freezer) -> None:
    (alex,) = await _members(client, "Alex")
    chore = await _chore(
        client,
        name="Make bed",
        members=[alex],
        streak_days=2,
        streak_bonus=5,
        repeat="daily",
    )
    freezer.move_to(dt_util.now() + timedelta(days=1))
    first = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    assert not any(
        b["bonus"] == "chore_streak" for b in first["entry"].get("bonuses", [])
    )
    freezer.move_to(dt_util.now() + timedelta(days=1))
    second = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    streak = [b for b in second["entry"]["bonuses"] if b["bonus"] == "chore_streak"]
    assert streak and streak[0]["points"] == 5 and "2 days" in streak[0]["title"]


async def test_pick_your_chores(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    big = await _chore(client, name="Mow", points=10, pool=True, members=[alex, sam])
    small = await _chore(client, name="Dust", points=2, pool=True, members=[alex, sam])
    third = await _chore(client, name="Sweep", points=3, pool=True, members=[alex, sam])
    state = await client.ok("state")
    assert state["picks"]["next"] == alex
    assert {c["id"] for c in state["chores"]}.isdisjoint({big["id"], small["id"]})
    # Not your turn.
    res = await client("pick", member_id=sam, chore_id=big["id"])
    assert "Alex's turn" in res["error"]["message"]
    picked = await client.ok("pick", member_id=alex, chore_id=big["id"])
    assert picked["next"] == sam
    res = await client("pick", member_id=sam, chore_id=big["id"])
    assert "already" in res["error"]["message"]
    await client.ok("pick", member_id=sam, chore_id=small["id"])
    # Sam has fewer points picked, so Sam goes again.
    state = await client.ok("state")
    assert state["picks"]["next"] == sam
    mow = next(c for c in state["chores"] if c["id"] == big["id"])
    assert mow["can"] == [alex] and mow["picked_by"] == alex
    res = await client("complete", member_id=alex, chore_id=third["id"])
    assert "Nobody picked" in res["error"]["message"]
    await client.ok("unpick", chore_id=big["id"])
    state = await client.ok("state")
    assert (
        next(c for c in state["picks"]["pool"] if c["id"] == big["id"])["picked_by"]
        is None
    )
    res = await client("unpick", chore_id=big["id"])
    assert not res["success"]
    # A chore can't be both picked and taken in turns.
    res = await client(
        "save",
        collection="chores",
        item={
            "name": "X",
            "pool": True,
            "turns": True,
            "members": [alex, sam],
            "turn_first": alex,
        },
    )
    assert not res["success"]
    # A weekly target: once Sam has 2 points, Alex picks.
    await client.ok("settings", pick_points=2)
    state = await client.ok("state")
    assert state["settings"]["pick_points"] == 2
    assert state["picks"]["next"] == alex
    await client.ok("delete", collection="members", item_id=sam)
    state = await client.ok("state")
    assert (
        next(c for c in state["picks"]["pool"] if c["id"] == small["id"])["picked_by"]
        is None
    )


async def test_done_when_a_device_finishes(
    hass: HomeAssistant,
    client,
    hass_admin_user,
) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    hass.states.async_set("vacuum.upstairs", "docked")
    hass.states.async_set("person.alex", "home", {"user_id": hass_admin_user.id})
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "person": "person.alex"},
    )
    chore = await _chore(
        client,
        name="Vacuum",
        done_when={"entity_id": "vacuum.upstairs", "state": "docked"},
    )
    # Alex starts it from Home Assistant; when it docks, Alex gets the points.
    hass.states.async_set(
        "vacuum.upstairs", "cleaning", context=Context(user_id=hass_admin_user.id)
    )
    hass.states.async_set("vacuum.upstairs", "docked")
    await hass.async_block_till_done()
    state = await client.ok("state")
    assert any(
        e["chore_id"] == chore["id"] and e["member"] == alex
        for e in state["done_today"]
    )
    # Started by nobody we know: it waits for someone to say it was them.
    other = await _chore(
        client,
        name="Unload dishwasher",
        done_when={"entity_id": "binary_sensor.dishwasher_door", "state": "on"},
    )
    hass.states.async_set("binary_sensor.dishwasher_door", "off")
    hass.states.async_set("binary_sensor.dishwasher_door", "on")
    await hass.async_block_till_done()
    state = await client.ok("state")
    claim = state["claims"][0]
    assert claim["chore_id"] == other["id"]
    hass.states.async_set("binary_sensor.dishwasher_door", "off")
    hass.states.async_set("binary_sensor.dishwasher_door", "on")
    await hass.async_block_till_done()
    assert len((await client.ok("state"))["claims"]) == 1
    res = await client.ok("claim", claim_id=claim["id"], member_id=sam)
    assert res["points"] == 2
    assert (await client.ok("state"))["claims"] == []
    res = await client("claim", claim_id=claim["id"], member_id=sam)
    assert not res["success"]
    res = await client(
        "save",
        collection="chores",
        item={"name": "Y", "done_when": {"entity_id": "vacuum.x"}},
    )
    assert not res["success"]
    await client.ok("delete", collection="chores", item_id=other["id"])


async def test_money_owed_and_paid_all(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    await client.ok("settings", point_value=0.1, currency="$")
    await client.ok("adjust", member_id=alex, points=50)
    await client.ok("cash_out", member_id=alex, points=10)
    await client.ok("cash_out", member_id=alex, points=20)
    state = await client.ok("state")
    assert state["owed"] == {alex: 3.0}
    assert (await client.ok("paid_all", member_id=alex)) == {"paid": 2}
    assert (await client.ok("state"))["owed"] == {}
