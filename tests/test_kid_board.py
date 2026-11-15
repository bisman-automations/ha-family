"""2.6.0: History (reasons, who, more, chart) and the Family dashboard's extras."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.family import model
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .test_family import Client, _family, _setup


@pytest.fixture(name="client")
async def _client(hass: HomeAssistant, hass_ws_client) -> Client:
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _chore(client: Client, **item) -> dict:
    item = {"name": "Make your bed", "points": 5, "repeat": "daily", **item}
    return (await client.ok("save", collection="chores", item=item))["item"]


# ---- pure helpers -------------------------------------------------------------------


def test_clean_reason() -> None:
    assert model.clean_reason("  bed   not made ") == "bed not made"
    assert model.clean_reason("") is None
    assert len(model.clean_reason("x" * 500)) == model.MAX_REASON


def test_daily_balances() -> None:
    today = date(2026, 11, 14)
    entries = [
        {"member": "a", "at": "2026-11-01T10:00:00-06:00", "points": 5},
        {"member": "a", "at": "2026-11-13T10:00:00-06:00", "points": 3},
        {
            "member": "a",
            "at": "2026-11-13T11:00:00-06:00",
            "points": 9,
            "review": model.REVIEW_REJECTED,
        },
        {"member": "a", "at": "2026-11-14T10:00:00-06:00", "points": -2},
    ]
    result = model.daily_balances(entries, {"a": 10}, ["a", "b"], today, 3)
    assert result["days"] == ["2026-11-12", "2026-11-13", "2026-11-14"]
    assert result["members"] == {"a": [15, 18, 16], "b": [0, 0, 0]}


def test_beat_timer() -> None:
    now = dt_util.now()
    chore = {"timer_minutes": 10}
    start = (now - timedelta(minutes=9)).isoformat()
    assert model.beat_timer(chore, start, now)
    assert not model.beat_timer(chore, (now - timedelta(minutes=11)).isoformat(), now)
    assert not model.beat_timer(chore, (now + timedelta(minutes=1)).isoformat(), now)
    assert not model.beat_timer(chore, "soon", now)
    assert not model.beat_timer({}, start, now)
    assert not model.beat_timer(chore, None, now)
    with pytest.raises(ValueError):
        model.clean_timer(500)


def test_family_streak() -> None:
    today = date(2026, 11, 14)
    days = lambda *n: {today - timedelta(days=d) for d in n}  # noqa: E731
    busy = lambda day: True  # noqa: E731
    off_sunday = lambda day: day.weekday() != 6  # noqa: E731
    # Both did today, yesterday and the day before; Sam missed 3 days ago.
    done = {"a": days(0, 1, 2, 3), "b": days(0, 1, 2)}
    assert model.family_streak(done, {"a": busy, "b": busy}, today) == 3
    # Today not finished yet: counts back from yesterday.
    done = {"a": days(1, 2), "b": days(0, 1, 2)}
    assert model.family_streak(done, {"a": busy, "b": busy}, today) == 2
    # A day off (Nov 8 is a Sunday) neither breaks nor counts.
    done = {"a": {date(2026, 11, d) for d in (7, 9, 10, 11, 12, 13, 14)}}
    assert model.family_streak(done, {"a": off_sunday}, today) == 7
    assert model.family_streak({}, {}, today) == 0


def test_what_to_wear() -> None:
    cold = model.what_to_wear(35, "°F", "rainy")
    assert cold["feel"] == "Cold"
    assert "umbrella" in cold["text"]
    assert model.what_to_wear(30, "°C", "sunny")["feel"] == "Hot"
    assert model.what_to_wear(-5, "°C", "snowy")["emoji"] == "❄️"
    assert model.what_to_wear("unknown", "°C", "sunny") is None


def test_clean_links() -> None:
    links = model.clean_links(
        [
            {"name": "School lunch", "url": "https://example.com/menu", "member": "a"},
            {"name": "", "url": ""},
            {"name": "Library", "url": "http://example.org", "member": "nobody"},
        ],
        {"a"},
    )
    assert [(link["name"], link["member"]) for link in links] == [
        ("School lunch", "a"),
        ("Library", None),
    ]
    assert [link["mobile"] for link in links] == [True, True]
    assert not model.clean_links(
        [{"name": "Wide", "url": "https://example.com", "mobile": False}], set()
    )[0]["mobile"]
    for bad in (
        [{"name": "Bad", "url": "javascript:alert(1)"}],
        [{"name": "", "url": "https://example.com"}],
    ):
        with pytest.raises(ValueError):
            model.clean_links(bad, set())


def test_ages() -> None:
    day = date(2026, 11, 14)
    kid = {"id": "a", "birthday": "11-20", "birth_year": 2018}
    teen = {"id": "b", "birthday": "01-02", "birth_year": 2012}
    unknown = {"id": "c", "birthday": "05-05"}
    assert model.age_on(kid, day) == 7
    assert model.age_on(teen, day) == 14
    assert model.age_on(unknown, day) is None
    members = [kid, teen, unknown]
    chore = {"id": "mow", "members": [], "min_age": 12}
    narrowed = model.for_ages(chore, members, day)
    # Riley's age isn't known: kept. Nobody was picked: still up for grabs.
    assert narrowed["members"] == ["b", "c"]
    assert narrowed["grab"] is True
    assert model.for_ages({**chore, "members": ["a"]}, members, day)["enabled"] is False
    assert model.for_ages({"id": "x"}, members, day) == {"id": "x"}
    with pytest.raises(ValueError):
        model.clean_birth_year(1800, 2026)


# ---- History ------------------------------------------------------------------------


async def test_didnt_happen_with_a_reason_and_who(
    hass: HomeAssistant, client: Client
) -> None:
    alex, _sam = await _family(client)
    chore = await _chore(client, members=[alex])
    done = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await client.ok(
        "review",
        entry_id=done["entry"]["id"],
        approved=False,
        penalty=2,
        reason="  Bed   not made ",
    )
    state = await client.ok("state")
    chore_entry = next(e for e in state["history"] if e["kind"] == "chore")
    assert chore_entry["reason"] == "Bed not made"
    # The test login is an admin with no family member: its own name.
    assert chore_entry["reviewed_by"]
    penalty = next(e for e in state["history"] if e["kind"] == "penalty")
    assert penalty["reason"] == "Bed not made"
    assert penalty["after"] == -2

    # Done right after all: the reason goes.
    await client.ok("review", entry_id=done["entry"]["id"], approved=True)
    state = await client.ok("state")
    chore_entry = next(e for e in state["history"] if e["kind"] == "chore")
    assert "reason" not in chore_entry

    entry = await client.ok("adjust", member_id=alex, points=3, reason="Kind")
    assert entry["entry"]["by"] == chore_entry["reviewed_by"]


async def test_history_pages_and_chart(hass: HomeAssistant, client: Client) -> None:
    alex, _sam = await _family(client)
    for _ in range(5):
        await client.ok("adjust", member_id=alex, points=1)
    first = await client.ok("history", limit=3)
    assert len(first["entries"]) == 3
    assert first["more"] is True
    rest = await client.ok("history", before=first["entries"][-1]["at"], limit=3)
    assert rest["more"] is False
    assert {e["id"] for e in first["entries"]}.isdisjoint(
        e["id"] for e in rest["entries"]
    )
    state = await client.ok("state")
    assert state["history_more"] is False
    chart = state["balance_days"]
    assert len(chart["days"]) == 28
    assert chart["members"][alex][-1] == 5


# ---- the Family dashboard's extras ---------------------------------------------------


async def test_timer_bonus(hass: HomeAssistant, client: Client) -> None:
    alex, _sam = await _family(client)
    chore = await _chore(client, members=[alex], timer_minutes=10, timer_bonus=3)
    assert chore["timer_minutes"] == 10
    started = (dt_util.now() - timedelta(minutes=4)).isoformat()
    done = await client.ok(
        "complete", member_id=alex, chore_id=chore["id"], timer_started=started
    )
    assert any(b["bonus"] == "timer" for b in done["entry"]["bonuses"])
    assert done["points"] >= 8

    res = await client(
        "save",
        collection="chores",
        item={"name": "Too long", "points": 1, "timer_minutes": 999},
    )
    assert not res["success"]


async def test_high_fives_and_points_story(hass: HomeAssistant, client: Client) -> None:
    alex, sam = await _family(client)
    entry = (await client.ok("high_five", from_id=alex, to_id=sam, emoji="⭐"))["entry"]
    assert entry["points"] == 0
    assert entry["title"] == "⭐"
    assert not (await client("high_five", from_id=alex, to_id=alex))["success"]
    for _ in range(9):
        await client.ok("high_five", from_id=alex, to_id=sam)
    too_many = await client("high_five", from_id=alex, to_id=sam)
    assert "tomorrow" in too_many["error"]["message"]
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == sam)["points"] == 0

    await client.ok("adjust", member_id=sam, points=4)
    story = await client.ok("points_story", member_id=sam)
    assert story["points"] == 4
    # High fives aren't in the points story.
    assert [(e["before"], e["after"]) for e in story["entries"]] == [(0, 4)]


async def test_tomorrow_ages_and_family_streak(
    hass: HomeAssistant, client: Client
) -> None:
    alex, sam = await _family(client)
    year = dt_util.now().year
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "birthday": "01-01", "birth_year": year - 7},
    )
    await client.ok(
        "save",
        collection="members",
        item={"id": sam, "name": "Sam", "birthday": "01-01", "birth_year": year - 13},
    )
    bed = await _chore(client, members=[alex, sam])
    mow = await _chore(client, name="Mow the lawn", members=[], min_age=12)
    res = await client(
        "save",
        collection="chores",
        item={"name": "Odd", "points": 1, "min_age": 10, "max_age": 5},
    )
    assert not res["success"]

    state = await client.ok("state")
    lawn = next(c for c in state["chores"] if c["id"] == mow["id"])
    assert lawn["can"] == [sam]
    assert not (await client("complete", member_id=alex, chore_id=mow["id"]))["success"]
    tomorrow = state["tomorrow"]
    assert tomorrow["date"] == (dt_util.now().date() + timedelta(days=1)).isoformat()
    assert [c["id"] for c in tomorrow["chores"][alex]] == [bed["id"]]
    assert [c["id"] for c in tomorrow["chores"][sam]] == [bed["id"]]
    assert state["family_streak"] == 0

    # Both finish their own chores today: a family streak of one day.
    await client.ok("complete", member_id=alex, chore_id=bed["id"])
    await client.ok("complete", member_id=sam, chore_id=bed["id"])
    assert (await client.ok("state"))["family_streak"] == 1


async def test_screen_time_weather_and_links(
    hass: HomeAssistant, client: Client
) -> None:
    await _family(client)
    tv = MockConfigEntry(domain="tv_mgmt", title="Family Room TV")
    tv.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "sensor",
        "tv_mgmt",
        f"{tv.entry_id}_time_remaining_today",
        config_entry=tv,
        suggested_object_id="family_room_tv_time_left",
    )
    hass.states.async_set(
        "weather.home", "rainy", {"temperature": 40, "temperature_unit": "°F"}
    )
    state = await client.ok("state")
    assert state["screen"] == [
        {
            "kind": "tv",
            "name": "Family Room TV",
            "entity_id": "sensor.family_room_tv_time_left",
        }
    ]
    assert state["weather"] is None

    assert not (await client("settings", weather_entity="sensor.nope"))["success"]
    await client.ok("settings", weather_entity="weather.home")
    weather = (await client.ok("state"))["weather"]
    assert weather["feel"] == "Cold"
    assert "umbrella" in weather["text"]

    await client.ok(
        "settings",
        links=[{"name": "School lunch", "emoji": "🍎", "url": "https://example.com"}],
    )
    links = (await client.ok("state"))["links"]
    assert [link["name"] for link in links] == ["School lunch"]
    bad = await client("settings", links=[{"name": "x", "url": "ftp://example.com"}])
    assert not bad["success"]


async def test_picture_mode_is_kept(hass: HomeAssistant, client: Client) -> None:
    alex, _sam = await _family(client)
    await client.ok(
        "save",
        collection="members",
        item={"id": alex, "name": "Alex", "picture_mode": True},
    )
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == alex)["picture_mode"] is True
