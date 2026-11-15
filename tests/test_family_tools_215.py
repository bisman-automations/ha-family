"""2.15.0: shop days, the swap market, grades, theme weeks, the helper
bonus, money paid out and goal milestones."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from custom_components.family import extras, model
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


async def test_shop_days(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    await client.ok("adjust", member_id=alex, points=50, reason="Start")
    today = dt_util.now().weekday()
    other = (today + 1) % 7
    reward = (
        await client.ok(
            "save",
            collection="rewards",
            item={"name": "Toy", "points": 5, "shop_days": [other]},
        )
    )["item"]
    assert reward["shop_days"] == [other]
    res = await client("redeem", member_id=alex, reward_id=reward["id"])
    assert not res["success"] and model.WEEKDAY_NAMES[other] in res["error"]["message"]
    await client.ok(
        "save",
        collection="rewards",
        item={
            "id": reward["id"],
            "name": "Toy",
            "points": 5,
            "shop_days": [today, other],
        },
    )
    await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    assert model.weekday_names([5, 6]) == "Saturday and Sunday"


async def test_grades(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    assert (await client.ok("state"))["grade_points"] == extras.DEFAULT_GRADES
    await client.ok("settings", grade_points={"A+": 12, "A": 10})
    entry = (
        await client.ok("grade/add", member_id=alex, subject="Math test", grade="A+")
    )["entry"]
    assert entry["points"] == 12 and entry["title"] == "A+ in Math test"
    assert not (await client("grade/add", member_id=alex, grade="Z"))["success"]
    assert _points(await client.ok("state"), alex) == 12


async def test_theme_week(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    today = dt_util.now().date()
    assert not (await client("theme/keep", member_id=alex))["success"]
    await client.ok(
        "settings",
        theme_week={
            "name": "Kind words",
            "points": 2,
            "from": today.isoformat(),
            "until": (today + timedelta(days=6)).isoformat(),
        },
    )
    await client.ok("theme/keep", member_id=alex)
    assert not (await client("theme/keep", member_id=alex))["success"]
    theme = (await client.ok("state"))["theme"]
    assert theme["kept"] == [alex] and theme["name"] == "Kind words"
    assert not (
        await client(
            "settings",
            theme_week={"name": "X", "from": "2026-01-10", "until": "2026-01-01"},
        )
    )["success"]
    await client.ok("settings", theme_week=None)
    assert (await client.ok("state"))["theme"] is None
    assert sam


async def test_helper_bonus(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    await client.ok("settings", helper_bonus=3)
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Garage", "points": 10, "members": [alex]},
        )
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"], helpers=[sam])
    state = await client.ok("state")
    assert _points(state, alex) == 5 and _points(state, sam) == 8


def test_payouts() -> None:
    members = [{"id": "a"}, {"id": "b"}]
    today = date(2026, 11, 15)
    entries = [
        {
            "kind": "cashout",
            "member": "a",
            "at": "2026-11-02T10:00:00",
            "money": 2.5,
            "given": "given",
        },
        {
            "kind": "cashout",
            "member": "a",
            "at": "2026-11-09T10:00:00",
            "money": 1.0,
            "given": "to_give",
        },
        {
            "kind": "cashout",
            "member": "b",
            "at": "2026-10-09T10:00:00",
            "money": 4.0,
            "given": "given",
        },
    ]
    rows = extras.payouts(entries, members, today, 3)
    assert [r["month"] for r in rows] == ["2026-11", "2026-10", "2026-09"]
    assert rows[0]["people"][0] == {"member": "a", "asked": 3.5, "paid": 2.5}
    assert rows[1]["people"][1] == {"member": "b", "asked": 4.0, "paid": 4.0}


async def test_payouts_command(hass: HomeAssistant, client) -> None:
    await _members(client, "Alex")
    months = (await client.ok("payouts"))["months"]
    assert len(months) == 6


async def test_goal_milestones(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    seen = []
    hass.bus.async_listen("family_goal_milestone", seen.append)
    await client.ok("family_goal/save", name="Pizza", target=20)
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Bins", "points": 11, "members": [alex]},
        )
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await hass.async_block_till_done()
    assert [e.data["percent"] for e in seen] == [25, 50]
    goal = (await client.ok("state"))["family_goals"][0]
    assert goal["milestone"] == 50
