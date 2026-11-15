"""2.11.0: chore bingo, the give jar, time to leave, chore ideas from the
kids, races, the evening check-in, and chores that wait for something or
start something."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from custom_components.family import bingo as bingo_module
from custom_components.family.leave import clean_leave_times, leave_at
from homeassistant.core import HomeAssistant, ServiceCall
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


async def _chore(client: Client, name: str, members: list[str], points: int = 1) -> str:
    item = {"name": name, "points": points, "members": members}
    return (await client.ok("save", collection="chores", item=item))["item"]["id"]


def test_bingo_board_is_the_same_all_week() -> None:
    chores = [{"id": f"c{i}", "name": f"C{i}"} for i in range(12)]
    monday = date(2026, 11, 9)
    board = bingo_module.pick_board(chores, "a", monday)
    assert len(board) == 9 and len(set(board)) == 9
    assert bingo_module.pick_board(chores, "a", date(2026, 11, 15)) == board
    assert bingo_module.pick_board(chores, "a", date(2026, 11, 16)) != board
    assert bingo_module.pick_board(chores[:8], "a", monday) == []
    assert bingo_module.lines_done([True] * 3 + [False] * 6) == 1
    assert bingo_module.lines_done([True] * 9) == 8


async def test_bingo_lines_and_full_card(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    for i in range(9):
        await _chore(client, f"Chore {i}", [alex])
    await client.ok("settings", bingo_line=2, bingo_full=10)
    state = await client.ok("state")
    cells = state["bingo"][alex]["cells"]
    assert len(cells) == 9 and not any(c["done"] for c in cells)
    earned = []
    entries = []
    for cell in cells:
        done = await client.ok("complete", member_id=alex, chore_id=cell["chore_id"])
        entries.append(done["entry"])
        earned += [b["bonus"] for b in done["entry"].get("bonuses", [])]
    assert earned.count("bingo_line") == 8
    assert earned.count("bingo_full") == 1
    state = await client.ok("state")
    assert state["bingo"][alex]["full"] and state["bingo"][alex]["lines"] == 8
    # Undoing the last chore takes its bingo bonuses back.
    await client.ok("undo", entry_id=entries[-1]["id"])
    state = await client.ok("state")
    assert not state["bingo"][alex]["full"]
    await client.ok("settings", bingo_line=0, bingo_full=0)
    assert (await client.ok("state"))["bingo"] == {}


async def test_give_jar(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    result = await client("give", member_id=alex, points=1)
    assert not result["success"]  # no goal yet
    await client.ok(
        "settings",
        give_goal={"name": "Animal shelter", "emoji": "🐶", "target": 10},
        give_percent=20,
    )
    await client.ok("adjust", member_id=alex, points=20, reason="Start")
    await client.ok("give", member_id=alex, points=5)
    assert not (await client("give", member_id=alex, points=100))["success"]
    state = await client.ok("state")
    assert state["give"]["total"] == 5 and state["give"]["by"] == {alex: 5}
    assert next(m for m in state["members"] if m["id"] == alex)["points"] == 15
    # The allowance's share goes in by itself.
    manager = hass.config_entries.async_entries("family")[0].runtime_data
    assert manager.give.from_allowance(alex, 10)["points"] == -2
    await client.ok(
        "settings",
        give_goal={"name": "Animal shelter", "target": 10},
        restart_give=True,
    )
    assert (await client.ok("state"))["give"]["total"] == 0


def test_time_to_leave() -> None:
    times = clean_leave_times({"0": "07:40", "5": "", "9": "08:00"})
    assert times == {"0": "07:40"}
    monday = datetime(2026, 11, 16, 7, 20, tzinfo=dt_util.get_default_time_zone())
    shown = leave_at({"leave_times": times, "leave_warn": 45}, monday)
    assert shown["at"].startswith("2026-11-16T07:40") and shown["warn_minutes"] == 45
    assert leave_at({"leave_times": times}, monday.replace(hour=8)) is None
    assert leave_at({"leave_times": times}, monday.replace(day=17)) is None


async def test_leave_in_the_snapshot(hass: HomeAssistant, client) -> None:
    now = dt_util.now()
    await client.ok(
        "settings", leave_times={str(now.weekday()): "23:59"}, leave_warn=20
    )
    state = await client.ok("state")
    if now.hour == 23 and now.minute >= 59:
        return
    assert state["leave"]["warn_minutes"] == 20
    settings = state["settings"]
    assert settings["leave_times"] == {str(now.weekday()): "23:59"}


async def test_chore_ideas(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    idea = (
        await client.ok("idea/add", member_id=alex, name="Wash the car", points=20)
    )["idea"]
    other = (await client.ok("idea/add", member_id=alex, name="Rake"))["idea"]
    await client.ok("idea/cancel", idea_id=other["id"])
    state = await client.ok("state")
    assert [i["name"] for i in state["chore_ideas"]] == ["Wash the car"]
    result = await client.ok(
        "idea/decide", idea_id=idea["id"], approved=True, points=15
    )
    chore = result["chore"]
    assert chore["points"] == 15 and chore["members"] == [alex]
    assert chore["repeat"] == "once"
    state = await client.ok("state")
    assert state["chore_ideas"][0]["status"] == "approved"
    assert not (await client("idea/decide", idea_id=idea["id"], approved=False))[
        "success"
    ]


async def test_races(hass: HomeAssistant, client) -> None:
    alex, sam = await _members(client, "Alex", "Sam")
    a = await _chore(client, "Bed", [alex])
    s = await _chore(client, "Bed too", [sam])
    assert not (await client("challenge", member_id=alex, other_id=sam))["success"]
    await client.ok("settings", challenge_points=5)
    race = (await client.ok("challenge", member_id=alex, other_id=sam))["challenge"]
    assert not (await client("challenge", member_id=alex, other_id=sam))["success"]
    done = await client.ok("complete", member_id=sam, chore_id=s)
    assert any(b["bonus"] == "challenge" for b in done["entry"]["bonuses"])
    state = await client.ok("state")
    assert state["challenges"][0]["winner"] == sam
    # The other one finishing later wins nothing.
    later = await client.ok("complete", member_id=alex, chore_id=a)
    assert not any(b["bonus"] == "challenge" for b in later["entry"].get("bonuses", []))
    # Undone: the race is open again.
    await client.ok("undo", entry_id=done["entry"]["id"])
    state = await client.ok("state")
    assert state["challenges"][0]["id"] == race["id"]
    assert state["challenges"][0]["winner"] is None


async def test_evening_check_in(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    assert not (await client("mood", member_id=alex, mood="good"))["success"]
    await client.ok("settings", mood_check=True)
    await client.ok("mood", member_id=alex, mood="tired")
    assert not (await client("mood", member_id=alex, mood="meh"))["success"]
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == alex)["mood_today"] == "tired"
    assert state["moods"][alex][-1]["mood"] == "tired"
    assert len(state["moods"][alex]) == 14
    await client.ok("mood", member_id=alex, mood=None)
    state = await client.ok("state")
    assert next(m for m in state["members"] if m["id"] == alex)["mood_today"] is None


async def test_only_when_and_on_done(hass: HomeAssistant, client) -> None:
    (alex,) = await _members(client, "Alex")
    started: list[ServiceCall] = []

    async def _turn_on(call: ServiceCall) -> None:
        started.append(call)

    hass.services.async_register("script", "turn_on", _turn_on)
    hass.states.async_set("script.tv_time", "off")
    hass.states.async_set("sensor.kind_of_day", "Holiday")
    item = {
        "name": "Homework",
        "points": 2,
        "members": [alex],
        "only_when": {
            "entity_id": "sensor.kind_of_day",
            "states": "School day, Exam day",
        },
        "on_done": "script.tv_time",
    }
    chore = (await client.ok("save", collection="chores", item=item))["item"]
    assert chore["only_when"]["states"] == ["School day", "Exam day"]
    state = await client.ok("state")
    assert not [c for c in state["chores"] if c["id"] == chore["id"]]
    assert not (await client("complete", member_id=alex, chore_id=chore["id"]))[
        "success"
    ]
    hass.states.async_set("sensor.kind_of_day", "School day")
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await hass.async_block_till_done()
    assert [c.data["entity_id"] for c in started] == ["script.tv_time"]
    bad = {**item, "on_done": "light.kitchen"}
    assert not (await client("save", collection="chores", item=bad))["success"]
    choices = await client.ok("choices")
    assert any(s["entity_id"] == "script.tv_time" for s in choices["starters"])
    assert any(w["entity_id"] == "sensor.kind_of_day" for w in choices["watchables"])
