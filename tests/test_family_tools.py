"""2.5.0: countdowns, reward requests, dinner vote, away, double points,
seasonal chores, the shopping list, the saving and birthday bonuses, adding
calendar events and the weekly report."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.family import model
from custom_components.family.manager import manager_of
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util
from tests.test_family import Client, FakeTodoList, _family, _next, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


@pytest.fixture
async def kiosk(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token):
    return Client(await hass_ws_client(hass, hass_read_only_access_token))


async def _chore(client: Client, **item) -> dict:
    return (
        await client.ok(
            "save", collection="chores", item={"points": 5, "repeat": "daily", **item}
        )
    )["item"]


def _member(state: dict, member_id: str) -> dict:
    return next(m for m in state["members"] if m["id"] == member_id)


# ---------------------------------------------------------------- seasons


def test_seasons():
    assert model.clean_month_day("2026-10-01", "x") == "10-01"
    assert model.clean_month_day("2-29", "x") == "02-29"
    assert model.clean_month_day("", "x") is None
    with pytest.raises(ValueError):
        model.clean_month_day("13-01", "x")
    fall = {"from_date": "10-01", "until_date": "11-30"}
    assert model.in_season(fall, date(2026, 10, 1))
    assert model.in_season(fall, date(2026, 11, 30))
    assert not model.in_season(fall, date(2026, 12, 1))
    winter = {"from_date": "12-01", "until_date": "03-31"}
    assert model.in_season(winter, date(2027, 1, 15))
    assert not model.in_season(winter, date(2027, 4, 1))
    assert model.in_season({}, date(2027, 4, 1))
    assert not model.on_day({**winter, "days": []}, date(2027, 6, 1))


async def test_seasonal_chore(hass: HomeAssistant, client, freezer):
    freezer.move_to(dt_util.start_of_local_day(date(2026, 11, 14)).replace(hour=9))
    alex, _sam = await _family(client)
    await _chore(
        client,
        name="Rake leaves",
        members=[alex],
        from_date="10-01",
        until_date="11-30",
    )
    await _chore(
        client, name="Shovel", members=[alex], from_date="12-01", until_date="03-31"
    )
    state = await client.ok("state")
    assert [c["name"] for c in state["chores"]] == ["Rake leaves"]
    saved = next(c for c in state["all_chores"] if c["name"] == "Shovel")
    assert (saved["from_date"], saved["until_date"]) == ("12-01", "03-31")
    res = await client(
        "save", collection="chores", item={"name": "Half", "from_date": "10-01"}
    )
    assert "both" in res["error"]["message"]


# ------------------------------------------------------------------- away


async def test_away_pauses_chores_streaks_and_allowance(
    hass: HomeAssistant, client, freezer
):
    sunday = _next(6, 7)
    freezer.move_to(sunday)
    alex, _sam = await _family(client)
    await client.ok(
        "save", collection="members", item={"id": alex, "name": "Alex", "allowance": 10}
    )
    chore = await _chore(client, name="Bed", members=[alex])
    await client.ok(
        "save",
        collection="routines",
        item={"name": "Morning", "steps": ["Teeth"], "members": [alex]},
    )
    await client.ok("settings", allowance_day=6, allowance_hour=8)

    res = await client.ok("away", action="add")
    assert res["away"]["now"]["until"] is None
    state = await client.ok("state")
    assert state["chores"] == [] and state["routines"] == []
    assert _member(state, alex)["own_today"]["total"] == 0
    refused = await client("complete", member_id=alex, chore_id=chore["id"])
    assert "away" in refused["error"]["message"]
    manager = manager_of(hass)
    assert not manager._has_own(alex)(sunday.date())

    # No allowance while away.
    freezer.move_to(sunday.replace(hour=8, minute=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    manager.async_allowance()
    assert _member(await client.ok("state"), alex)["points"] == 0

    # Back home today: today counts again.
    await client.ok("away", action="back")
    state = await client.ok("state")
    assert [c["name"] for c in state["chores"]] == ["Bed"]
    assert state["away"]["now"] is None

    # A planned trip can be dropped; one can't overlap another.
    start = (sunday.date() + timedelta(days=10)).isoformat()
    end = (sunday.date() + timedelta(days=14)).isoformat()
    trip = await client.ok("away", action="add", **{"from": start, "until": end})
    (planned,) = trip["away"]["planned"]
    overlap = await client("away", action="add", **{"from": end})
    assert "overlaps" in overlap["error"]["message"]
    await client.ok("away", action="remove", period_id=planned["id"])
    assert (await client.ok("state"))["away"]["planned"] == []
    res = await client("away", action="back")
    assert not res["success"]


async def test_away_days_dont_break_a_streak(hass: HomeAssistant, client, freezer):
    monday = _next(0, 9)
    freezer.move_to(monday)
    alex, _sam = await _family(client)
    chore = await _chore(client, name="Bed", members=[alex])
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    manager = manager_of(hass)
    # Away Tuesday and Wednesday, back Thursday.
    tue = monday.date() + timedelta(days=1)
    manager.settings["away"] = [
        {
            "id": "a",
            "from": tue.isoformat(),
            "until": (tue + timedelta(days=1)).isoformat(),
        }
    ]
    freezer.move_to(monday + timedelta(days=3))
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    assert manager.streak(alex) == 2


# --------------------------------------------------------- double points


async def test_double_points(hass: HomeAssistant, client, freezer):
    freezer.move_to(_next(5, 9))
    alex, _sam = await _family(client)
    bed = await _chore(client, name="Bed", members=[alex])
    dishes = await _chore(client, name="Dishes", members=[alex])
    until = (dt_util.now() + timedelta(hours=3)).isoformat()
    boost = (
        await client.ok(
            "boost/start", label="Saturday cleanup", until=until, chores=[bed["id"]]
        )
    )["boost"]
    state = await client.ok("state")
    shown = {c["name"]: c for c in state["chores"]}
    assert shown["Bed"]["points"] == 10 and shown["Bed"]["boost"] == 2
    assert shown["Dishes"]["points"] == 5 and "boost" not in shown["Dishes"]
    assert state["boosts"][0]["on"] is True

    entry = (await client.ok("complete", member_id=alex, chore_id=bed["id"]))["entry"]
    assert entry["points"] == 10 and entry["boost"] == 2
    await client.ok("complete", member_id=alex, chore_id=dishes["id"])
    assert _member(await client.ok("state"), alex)["points"] == 15

    await client.ok("boost/stop", boost_id=boost["id"])
    assert (await client.ok("state"))["boosts"] == []
    bad = await client("boost/start", factor=5, until=until)
    assert not bad["success"]
    past = (dt_util.now() - timedelta(hours=1)).isoformat()
    assert not (await client("boost/start", until=past))["success"]

    # Triple for every chore, ending later: dropped once it's over.
    await client.ok("boost/start", factor=3, until=until)
    assert model.boost_factor(manager_of(hass).boosts.items, "any", dt_util.now()) == 3
    freezer.tick(timedelta(hours=4))
    manager_of(hass).async_allowance()
    assert manager_of(hass).boosts.items == []


# -------------------------------------------------------------- countdowns


async def test_countdowns_and_birthdays(hass: HomeAssistant, client, kiosk, freezer):
    freezer.move_to(dt_util.start_of_local_day(date(2026, 11, 14)).replace(hour=9))
    alex, _sam = await _family(client)
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "birthday": "2016-11-20"},
    )
    trip = (
        await client.ok("countdown/save", name="Beach", emoji="🏖️", date="2026-12-01")
    )["countdown"]
    state = await kiosk.ok("state")
    rows = [(c["name"], c["days"]) for c in state["countdowns"]]
    assert rows == [("Alex's birthday", 6), ("Beach", 17)]
    assert _member(state, alex)["birthday"] == "11-20"

    # Only parents edit them; a past day is refused.
    res = await kiosk("countdown/save", name="X", date="2026-12-02")
    assert res["error"]["code"] == "unauthorized"
    assert not (await client("countdown/save", name="X", date="2026-11-01"))["success"]

    await client.ok(
        "countdown/save", item_id=trip["id"], name="Beach!", date="2026-12-01"
    )
    assert [c["name"] for c in (await kiosk.ok("state"))["countdowns"]][1] == "Beach!"
    # Its day over: gone.
    freezer.move_to(dt_util.start_of_local_day(date(2026, 12, 2)).replace(hour=1))
    manager_of(hass).async_allowance()
    assert manager_of(hass).countdowns.items == []
    await client.ok("countdown/save", name="Party", date="2026-12-24", member=alex)
    party = manager_of(hass).countdowns.items[0]
    await client.ok("countdown/delete", item_id=party["id"])
    assert manager_of(hass).countdowns.items == []


async def test_birthday_bonus(hass: HomeAssistant, client, freezer):
    freezer.move_to(dt_util.start_of_local_day(date(2026, 11, 20)).replace(hour=7))
    alex, sam = await _family(client)
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "birthday": "11-20"},
    )
    await client.ok("settings", birthday_points=25)
    manager = manager_of(hass)
    manager.async_allowance()
    manager.async_allowance()
    state = await client.ok("state")
    assert _member(state, alex)["points"] == 25
    assert _member(state, alex)["birthday_today"] is True
    assert _member(state, sam)["birthday_today"] is False
    assert state["recent"][0]["kind"] == "birthday"
    # Editing Alex keeps that this year's was given.
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "birthday": "11-20"},
    )
    manager.async_allowance()
    assert manager.points(alex) == 25
    assert model.birthday_on("02-29", date(2027, 2, 28))
    assert not model.birthday_on("02-29", date(2028, 2, 28))
    assert model.next_birthday("02-29", date(2027, 3, 1)) == date(2028, 2, 29)


# ---------------------------------------------------------- reward requests


async def test_reward_requests(hass: HomeAssistant, client, kiosk):
    alex, sam = await _family(client)
    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    await client.ok(
        "settings", notify_targets=["mobile_app_dads_phone"], notify_rewards=True
    )
    req = (
        await kiosk.ok(
            "request/add", member_id=alex, name="Sleepover", emoji="🏕️", points=150
        )
    )["request"]
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent[-1].data["title"] == "Alex asked for Sleepover"
    state = await kiosk.ok("state")
    assert state["requests"][0]["status"] == "pending"

    # Only parents answer; yes makes it a reward for Alex alone.
    res = await kiosk("request/decide", request_id=req["id"], approved=True)
    assert res["error"]["code"] == "unauthorized"
    res = await client.ok(
        "request/decide", request_id=req["id"], approved=True, points=200
    )
    assert res["reward"]["points"] == 200 and res["reward"]["members"] == [alex]
    state = await kiosk.ok("state")
    assert state["requests"][0]["status"] == "approved"
    assert any(r["name"] == "Sleepover" for r in state["rewards"])

    no = (await kiosk.ok("request/add", member_id=sam, name="Pony"))["request"]
    await client.ok("request/decide", request_id=no["id"], approved=False)
    again = await client("request/decide", request_id=no["id"], approved=False)
    assert not again["success"]
    # Taken back before an answer.
    oops = (await kiosk.ok("request/add", member_id=sam, name="Oops"))["request"]
    await kiosk.ok("request/cancel", request_id=oops["id"])
    for i in range(5):
        await kiosk.ok("request/add", member_id=sam, name=f"Thing {i}")
    res = await kiosk("request/add", member_id=sam, name="One more")
    assert "already asked" in res["error"]["message"]
    # A yes with no points asked or given is refused.
    nopoints = manager_of(hass).requests.items[-1]
    res = await client("request/decide", request_id=nopoints["id"], approved=True)
    assert not res["success"]


# -------------------------------------------------------------- dinner vote


async def test_dinner_vote(hass: HomeAssistant, client, kiosk, freezer):
    day = _next(2, 15)
    freezer.move_to(day)
    alex, sam = await _family(client)
    vote = (
        await client.ok(
            "vote/start", options=["Tacos", "Pizza", " tacos ", "Soup"], closes="17:00"
        )
    )["vote"]
    assert vote["options"] == ["Tacos", "Pizza", "Soup"]
    assert not (await client("vote/start", options=["A", "B"]))["success"]
    await kiosk.ok("vote/cast", member_id=alex, option=1)
    await kiosk.ok("vote/cast", member_id=sam, option=0)
    await kiosk.ok("vote/cast", member_id=sam, option=1)  # changed their mind
    state = await kiosk.ok("state")
    assert state["vote"]["counts"] == [0, 2, 0]
    assert not (await kiosk("vote/cast", member_id=sam, option=9))["success"]

    # Closes by itself at its time; the winner is dinner.
    freezer.move_to(day.replace(hour=17, minute=0, second=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = await kiosk.ok("state")
    assert state["vote"]["status"] == "closed" and state["vote"]["winner"] == 1
    assert state["meals"][0]["dinner"] == "Pizza"
    assert not (await kiosk("vote/cast", member_id=sam, option=0))["success"]
    # The next day it's gone.
    manager = manager_of(hass)
    manager.vote.tick(day + timedelta(days=1))
    assert manager.vote.vote is None

    assert model.vote_winner(["A", "B"], {"x": 0, "y": 1}) == 0
    assert model.vote_winner(["A", "B"], {}) is None
    await client.ok("vote/start", options=["A", "B"])
    await client.ok("vote/close")
    await client.ok("vote/cancel")
    assert manager.vote.vote is None


# ------------------------------------------------------------ shopping list


async def test_shopping_list_from_meals(hass: HomeAssistant, client):
    todo = FakeTodoList(hass, "todo.shopping")
    await todo.add_item(ServiceCall(hass, "todo", "add_item", {"item": "milk"}))
    today = dt_util.now().date()
    res = await client("shopping", entity_id="todo.shopping")
    assert "anything to buy" in res["error"]["message"]
    await client.ok(
        "meals",
        date=today.isoformat(),
        dinner="Tacos",
        ingredients="Tortillas, cheese\nSalsa",
    )
    await client.ok(
        "meals",
        date=(today + timedelta(days=1)).isoformat(),
        dinner="Cereal",
        ingredients="Milk; Cheese",
    )
    state = await client.ok("state")
    assert state["meals"][0]["ingredients"] == "Tortillas\ncheese\nSalsa"
    res = await client.ok("shopping", entity_id="todo.shopping")
    assert res == {"added": ["Tortillas", "cheese", "Salsa"], "skipped": ["Milk"]}
    assert [i["summary"] for i in todo.items] == [
        "milk",
        "Tortillas",
        "cheese",
        "Salsa",
    ]
    state = await client.ok("state")
    assert state["settings"]["shopping_list"] == "todo.shopping"
    res = await client("shopping", entity_id="todo.nope")
    assert not res["success"]


# ------------------------------------------------------------- saving bonus


async def test_saving_bonus(hass: HomeAssistant, client, freezer):
    sunday = _next(6, 7)
    freezer.move_to(sunday - timedelta(days=8))
    alex, sam = await _family(client)
    await client.ok("adjust", member_id=alex, points=100)
    await client.ok("adjust", member_id=sam, points=100)
    freezer.move_to(sunday - timedelta(days=2))
    # Sam spends 60 this week; Alex earns 50 more (that doesn't count).
    await client.ok("adjust", member_id=sam, points=-60)
    await client.ok("adjust", member_id=alex, points=50)
    await client.ok(
        "settings", allowance_day=6, allowance_hour=8, saving_percent=10, saving_max=8
    )
    freezer.move_to(sunday.replace(hour=8, minute=1))
    manager = manager_of(hass)
    manager.async_allowance()
    manager.async_allowance()
    assert manager.points(alex) == 150 + 8  # 10% of 100 kept, at most 8
    assert manager.points(sam) == 40 + 4
    assert manager.entries[-1]["kind"] == "saving"
    res = await client("settings", saving_percent=60)
    assert not res["success"]
    assert model.saving_bonus(0, 10, 0) == 0
    assert model.saving_bonus(55, 10, 0) == 5


# ----------------------------------------------------------- calendar events


async def test_add_calendar_event(hass: HomeAssistant, client):
    hass.states.async_set("calendar.family", "off", {"friendly_name": "Family"})
    created = async_mock_service(hass, "calendar", "create_event")

    async def get_events(call):
        return {"calendar.family": {"events": []}}

    from homeassistant.core import SupportsResponse

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    res = await client(
        "calendar/add", entity_id="calendar.family", title="Dentist", date="2026-12-01"
    )
    assert "family's calendars" in res["error"]["message"]
    await client.ok("settings", calendars=[{"entity_id": "calendar.family"}])
    await client.ok(
        "calendar/add",
        entity_id="calendar.family",
        title="Dentist",
        date="2026-12-01",
        start="16:00",
        end="17:00",
    )
    data = created[-1].data
    assert data["summary"] == "Dentist"
    assert data["start_date_time"].startswith("2026-12-01T16:00")
    assert data["end_date_time"].startswith("2026-12-01T17:00")
    await client.ok(
        "calendar/add",
        entity_id="calendar.family",
        title="Camp",
        date="2026-12-01",
        end_date="2026-12-03",
    )
    assert created[-1].data["start_date"] == "2026-12-01"
    assert created[-1].data["end_date"] == "2026-12-04"


# ------------------------------------------------------------ weekly report


async def test_weekly_report(hass: HomeAssistant, client, kiosk, freezer):
    freezer.move_to(_next(2, 9))
    alex, _sam = await _family(client)
    bed = await _chore(client, name="Bed", members=[alex], repeat="always")
    for _ in range(3):
        await client.ok("complete", member_id=alex, chore_id=bed["id"])
    reward = (
        await client.ok(
            "save", collection="rewards", item={"name": "Ice cream", "points": 5}
        )
    )["item"]
    await client.ok("redeem", member_id=alex, reward_id=reward["id"])
    report = (await client.ok("report"))["report"]
    row = next(m for m in report["members"] if m["id"] == alex)
    assert row["chores"] == 3
    assert row["top_chores"] == [{"name": "Bed", "times": 3}]
    assert row["earned"] == 15 and row["spent"] == 5
    assert row["rewards"] == ["Ice cream"]
    assert row["points"] == 10
    last = (await client.ok("report", weeks_ago=1))["report"]
    assert next(m for m in last["members"] if m["id"] == alex)["chores"] == 0
    assert (await kiosk("report"))["error"]["code"] == "unauthorized"
