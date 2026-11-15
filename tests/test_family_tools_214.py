"""2.14.0: whole-week trades, the saving bonus to come, the homework timer,
goals for some of the family or just the kids, photos of the month, how
hard a chore is and points by age, and rewards to buy on a list."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.family import model
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


async def test_trade_for_the_week(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Dishes", "points": 2, "members": [alex]},
        )
    )["item"]
    trade = (
        await client.ok("trade/offer", member_id=alex, chore_id=chore["id"], week=True)
    )["trade"]
    today = dt_util.now().date()
    assert trade["until"] == (today + timedelta(days=6 - today.weekday())).isoformat()
    await client.ok("trade/take", trade_id=trade["id"], member_id=sam)
    await client.ok("trade/decide", trade_id=trade["id"], approved=True)
    manager = _manager(hass)
    assert manager.trades.apply({"id": chore["id"], "members": [alex]})["members"] == [
        sam
    ]
    # Still on until Sunday, gone after.
    trades = manager.trades
    trades._items[0]["day"] = (today - timedelta(days=1)).isoformat()  # noqa: SLF001
    assert trades.items and trades.apply({"id": chore["id"], "members": [alex]})[
        "members"
    ] == [sam]
    trades._items[0]["until"] = (today - timedelta(days=1)).isoformat()  # noqa: SLF001
    assert trades.items == []


async def test_saving_bonus_to_come(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    assert (await client.ok("state"))["saving_next"] is None
    await client.ok("settings", saving_percent=10)
    await client.ok("adjust", member_id=alex, points=50, reason="Start")
    nxt = (await client.ok("state"))["saving_next"]
    assert nxt["points"][alex] == 5 and nxt["percent"] == 10


async def test_homework_timer(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    assert not (
        await client("reading/log", member_id=alex, minutes=30, kind="homework")
    )["success"]
    await client.ok(
        "settings", homework={"block_minutes": 20, "points": 3, "max_minutes": 90}
    )
    entry = (
        await client.ok("reading/log", member_id=alex, minutes=45, kind="homework")
    )["entry"]
    assert entry["points"] == 6 and entry["chore_id"] == "homework"
    assert entry["title"] == "Homework 45 minutes"
    state = await client.ok("state")
    assert state["homework_today"][alex] == 45 and state["reading_today"][alex] == 0


async def test_goals_for_some_or_the_kids(hass: HomeAssistant, client) -> None:
    alex, sam, mom = await _members(client, "Alex", "Sam", "Mom")
    manager = _manager(hass)
    manager.parent_ids = {mom}
    kids = (
        await client.ok("family_goal/save", name="McDonald's", target=10, kids=True)
    )["goal"]
    pair = (
        await client.ok("family_goal/save", name="Lego", target=10, members=[alex, sam])
    )["goal"]
    assert not (
        await client("family_goal/save", name="Solo", target=10, members=[alex])
    )["success"]
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Table", "points": 4, "members": [alex, mom]},
        )
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await client.ok("complete", member_id=mom, chore_id=chore["id"])
    goals = {g["id"]: g for g in (await client.ok("state"))["family_goals"]}
    # Mom's points don't count toward the kids' goal, and it isn't hers.
    assert goals[kids["id"]]["progress"] == 4 and goals[kids["id"]]["kids"]
    assert mom not in goals[kids["id"]]["who"]
    assert goals[pair["id"]]["progress"] == 4 and goals[pair["id"]]["who"] == [
        alex,
        sam,
    ]
    await client.ok("delete", collection="members", item_id=sam)
    goals = {g["id"]: g for g in (await client.ok("state"))["family_goals"]}
    assert goals[pair["id"]]["who"] is None  # one left: the whole family again


async def test_photos_of_the_month(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    manager = _manager(hass)
    now = dt_util.now()
    manager.entries += [
        {
            "id": "p1",
            "at": now.isoformat(),
            "kind": "chore",
            "member": alex,
            "title": "Bed",
            "points": 1,
            "photo": True,
        },
        {
            "id": "p2",
            "at": now.isoformat(),
            "kind": "chore",
            "member": alex,
            "title": "No",
            "points": 1,
            "photo": True,
            "review": "rejected",
        },
        {
            "id": "p3",
            "at": now.isoformat(),
            "kind": "chore",
            "member": alex,
            "title": "Plain",
            "points": 1,
        },
    ]
    photos = (await client.ok("photos/month"))["photos"]
    assert [p["entry_id"] for p in photos] == ["p1"]
    assert (await client.ok("photos/month", months_ago=1))["photos"] == []


def test_points_by_age() -> None:
    rule = model.clean_age_points({"percent": 10, "from_age": 6})
    assert model.age_points(10, 8, rule) == 12
    assert model.age_points(10, 5, rule) == 10
    assert model.age_points(10, None, rule) == 10
    assert model.clean_age_points({"percent": 0}) is None
    with pytest.raises(ValueError):
        model.clean_age_points({"percent": 80})


async def test_difficulty_and_age_points(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    year = dt_util.now().year - 10
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "birthday": "01-01", "birth_year": year},
    )
    await client.ok("settings", age_points={"percent": 10, "from_age": 6})
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Mow", "points": 10, "members": [alex], "difficulty": "hard"},
        )
    )["item"]
    assert chore["difficulty"] == "hard"
    entry = (await client.ok("complete", member_id=alex, chore_id=chore["id"]))["entry"]
    assert entry["points"] == 14  # four years over six
    bad = (
        await client.ok(
            "save", collection="chores", item={"name": "X", "difficulty": "silly"}
        )
    )["item"]
    assert bad["difficulty"] == ""


async def test_rewards_to_buy_go_on_a_list(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    added = async_mock_service(hass, "todo", "add_item")
    hass.states.async_set("todo.shopping", "0")
    assert not (await client("settings", reward_list="light.x"))["success"]
    await client.ok("settings", reward_list="todo.shopping")
    reward = (
        await client.ok(
            "save", collection="rewards", item={"name": "A new toy", "points": 5}
        )
    )["item"]
    await client.ok("adjust", member_id=alex, points=10, reason="Start")
    await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    await hass.async_block_till_done()
    assert added[0].data == {"entity_id": "todo.shopping", "item": "A new toy for Alex"}
