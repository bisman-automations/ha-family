"""2.13.0: several family goals, chore auctions, allowance rules, the
reading log, team chores, gift ideas, the screen-time bank and beat the
clock."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from custom_components.family import allowance_rule, bank, reading
from custom_components.family.auctions import winner
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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


async def test_several_family_goals(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    reached = []
    hass.bus.async_listen("family_goal_reached", reached.append)
    pizza = (await client.ok("family_goal/save", name="Pizza", target=4))["goal"]
    movie = (await client.ok("family_goal/save", name="Movie", emoji="🎬", target=50))[
        "goal"
    ]
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Table", "points": 5, "members": [alex, sam]},
        )
    )["item"]
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await hass.async_block_till_done()
    state = await client.ok("state")
    goals = {g["id"]: g for g in state["family_goals"]}
    assert goals[pizza["id"]]["reached"] and goals[movie["id"]]["progress"] == 5
    # Still to reach first.
    assert state["family_goals"][0]["id"] == movie["id"]
    assert state["family_goal"]["id"] == movie["id"]
    assert [e.data["id"] for e in reached] == [pizza["id"]]
    # Starting a reached goal again counts from now.
    await client.ok(
        "family_goal/save", item_id=pizza["id"], name="Pizza", target=4, restart=True
    )
    goals = {g["id"]: g for g in (await client.ok("state"))["family_goals"]}
    assert goals[pizza["id"]]["progress"] == 0
    await client.ok("family_goal/delete", item_id=pizza["id"])
    assert len((await client.ok("state"))["family_goals"]) == 1
    for n in range(5):
        await client.ok("family_goal/save", name=f"Goal {n}", target=10)
    assert not (await client("family_goal/save", name="Too many", target=10))["success"]


async def test_one_old_goal_becomes_the_first(hass: HomeAssistant, client) -> None:
    manager = _manager(hass)
    manager.settings.pop("family_goals", None)
    manager.settings["family_goal"] = {
        "name": "Old",
        "target": 9,
        "since": dt_util.now().isoformat(),
    }
    manager.goals.load()
    assert manager.goals.items[0]["name"] == "Old"
    assert "family_goal" not in manager.settings


async def test_chore_auction(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    auction = (await client.ok("auction/start", name="Garage", points=30, minutes=60))[
        "auction"
    ]
    assert not (
        await client("auction/bid", auction_id=auction["id"], member_id=alex, points=40)
    )["success"]
    await client.ok("auction/bid", auction_id=auction["id"], member_id=alex, points=20)
    await client.ok("auction/bid", auction_id=auction["id"], member_id=sam, points=15)
    state = await client.ok("state")
    assert state["auctions"][0]["lowest"] == 15
    # Time's up: the lowest bid gets a one-off chore worth it.
    manager = _manager(hass)
    manager.auctions.tick(dt_util.now() + timedelta(minutes=61))
    state = await client.ok("state")
    closed = state["auctions"][0]
    assert closed["winner"] == sam and closed["won_for"] == 15
    chore = next(c for c in state["chores"] if c["name"] == "Garage")
    assert chore["points"] == 15 and chore["can"] == [sam]
    assert winner([]) is None
    assert (
        winner([{"points": 3, "at": "2"}, {"points": 3, "at": "1", "member": "x"}])[
            "at"
        ]
        == "1"
    )


def test_allowance_rule() -> None:
    rule = allowance_rule.clean_rule(
        {"enabled": True, "boost_at": 100, "boost": 20, "cut_below": 50, "cut": 25}
    )
    today = date(2026, 11, 16)
    every = lambda _d: True  # noqa: E731
    all_week = {today - timedelta(days=i) for i in range(1, 8)}
    share = allowance_rule.last_week_share(all_week, every, today)
    assert share == 1
    assert allowance_rule.adjusted(10, share, rule) == (
        12,
        "+20%: 100% of days all done",
    )
    two = set(list(sorted(all_week))[:2])
    low = allowance_rule.last_week_share(two, every, today)
    assert allowance_rule.adjusted(10, low, rule)[0] == 8
    assert allowance_rule.adjusted(10, 0.6, rule) == (10, None)
    assert allowance_rule.adjusted(10, None, rule) == (10, None)
    assert allowance_rule.last_week_share(set(), lambda _d: False, today) is None
    with pytest.raises(Exception, match="below"):
        allowance_rule.clean_rule({"boost_at": 40, "cut_below": 60})


async def test_allowance_follows_the_rule(hass: HomeAssistant, client) -> None:
    manager = _manager(hass)
    (alex,) = await _members(client, "Alex")
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "allowance": 10},
    )
    await client.ok(
        "save",
        collection="chores",
        item={"name": "Bed", "points": 1, "members": [alex]},
    )
    await client.ok(
        "settings", allowance_rule={"enabled": True, "cut_below": 50, "cut": 50}
    )
    now = dt_util.now()
    await client.ok("settings", allowance_day=now.weekday(), allowance_hour=0)
    manager.settings["allowance_week"] = None
    manager.async_allowance()
    entry = next(e for e in manager.entries if e["kind"] == "allowance")
    # No day last week was all done: half.
    assert entry["points"] == 5 and entry["base_points"] == 10
    assert "50%" in entry["title"]


async def test_reading_log(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    assert not (await client("reading/log", member_id=alex, minutes=20))["success"]
    await client.ok(
        "settings", reading={"block_minutes": 15, "points": 2, "max_minutes": 60}
    )
    first = (await client.ok("reading/log", member_id=alex, minutes=20, book="Hobbit"))[
        "entry"
    ]
    assert first["points"] == 2 and first["review"] == "pending"
    # 20 + 25 = 45 minutes: three whole blocks, so one more is earned.
    second = (await client.ok("reading/log", member_id=alex, minutes=25))["entry"]
    assert second["points"] == 4
    third = (await client.ok("reading/log", member_id=alex, minutes=40))["entry"]
    assert third["minutes"] == 15  # capped at 60 a day
    assert not (await client("reading/log", member_id=alex, minutes=5))["success"]
    state = await client.ok("state")
    assert state["reading_today"][alex] == 60 and state["reading"]["points"] == 2
    assert reading.reading_points(14, {"block_minutes": 15, "points": 2}) == 0


async def test_team_chore(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    assert not (
        await client(
            "save",
            collection="chores",
            item={"name": "Yard", "points": 6, "members": [alex], "team": True},
        )
    )["success"]
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Yard", "points": 6, "members": [alex, sam], "team": True},
        )
    )["item"]
    done = (await client.ok("complete", member_id=alex, chore_id=chore["id"]))["entry"]
    assert done["points"] == 0 and done["team_waiting"] == ["Sam"]
    assert "team_waiting" not in _manager(hass).entries[-1]
    state = await client.ok("state")
    assert _points(state, alex) == 0
    yard = next(c for c in state["chores"] if c["id"] == chore["id"])
    assert yard["team_done"] == [alex]
    await client.ok("complete", member_id=sam, chore_id=chore["id"])
    state = await client.ok("state")
    assert _points(state, alex) == 6 and _points(state, sam) == 6


async def test_gift_ideas(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "birthday": "05-04"},
    )
    reward = (
        await client.ok(
            "save", collection="rewards", item={"name": "Movie", "points": 10}
        )
    )["item"]
    await client.ok("wish", member_id=alex, reward_id=reward["id"], on=True)
    ideas = (
        await client.ok("gift_idea", member_id=alex, text="Bike helmet", add=True)
    )["gift_ideas"]
    assert ideas == ["Bike helmet"]
    # Editing the member keeps their ideas.
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "birthday": "05-04"},
    )
    text = (await client.ok("gifts/text", member_id=alex))["text"]
    assert text.splitlines() == [
        "Gift ideas for Alex",
        "Birthday: May 4",
        "- Bike helmet",
        "- Movie",
    ]
    await client.ok("gift_idea", member_id=alex, text="bike helmet", add=False)
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == alex)["gift_ideas"] == []


async def test_screen_time_bank(hass: HomeAssistant, client) -> None:
    assert bank.deposit(100, 45, 120) == 20
    assert bank.deposit(0, None, 120) == 0
    (alex,) = await _members(client, "Alex")
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "bank_tv": "tv_entry", "bank_max": 60},
    )
    er.async_get(hass).async_get_or_create(
        "sensor", "tv_mgmt", "tv_entry_time_remaining_today", suggested_object_id="left"
    )
    hass.states.async_set("sensor.left", "25")
    manager = _manager(hass)
    night = dt_util.now().replace(hour=23, minute=56)
    manager.bank.tick(night)
    manager.bank.tick(night)  # once a day
    assert (await client.ok("state"))["bank"] == {alex: 25}
    granted = []

    async def grant(call):
        granted.append(call.data)

    hass.services.async_register("tv_mgmt", "grant_extension", grant)
    assert (await client.ok("bank/spend", member_id=alex, minutes=10))["left"] == 15
    assert granted[0]["profile_id"] == "tv_entry" and granted[0]["minutes"] == 10
    assert not (await client("bank/spend", member_id=alex, minutes=30))["success"]


async def test_beat_the_clock(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    now = dt_util.now()
    later = (now + timedelta(minutes=20)).strftime("%H:%M")
    if later < now.strftime("%H:%M"):
        pytest.skip("too close to midnight")
    await client.ok(
        "settings", leave_times={str(now.weekday()): later}, beat_clock_points=3
    )
    routine = (
        await client.ok(
            "save",
            collection="routines",
            item={
                "name": "Morning",
                "points": 2,
                "steps": ["Dress"],
                "beat_clock": True,
            },
        )
    )["item"]
    result = await client.ok(
        "routine/step", routine_id=routine["id"], member_id=alex, step=0, done=True
    )
    assert result["entry"]["bonuses"][0]["points"] == 3
    assert _points(await client.ok("state"), alex) == 5
