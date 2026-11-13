"""The family goal and speaker reminders."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.family import model
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from tests.test_family import DOMAIN, Client, _family, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


def _manager(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data


async def _chore(client: Client, **item) -> dict:
    return (await client.ok("save", collection="chores", item={"points": 5, **item}))[
        "item"
    ]


def test_goal_progress_counts_chores_and_bonuses_since_it_began():
    start = datetime(2026, 11, 1, 12, 0, tzinfo=dt_util.UTC)
    at = lambda hours: (start + timedelta(hours=hours)).isoformat()  # noqa: E731
    entries = [
        {"kind": "chore", "points": 5, "at": at(-1)},  # before: not counted
        {"kind": "chore", "points": 5, "at": at(1)},
        {"kind": "bonus", "points": 2, "at": at(2)},
        {"kind": "chore", "points": 5, "at": at(3), "review": "rejected"},
        {"kind": "reward", "points": -20, "at": at(4)},  # spending doesn't count
        {"kind": "adjust", "points": 3, "at": at(5)},
    ]
    assert model.goal_progress(entries, start.isoformat()) == 7
    assert model.goal_progress(entries, None) == 0


def test_reminder_text():
    assert model.reminder_text("Set the table", []) == "Reminder: Set the table."
    assert (
        model.reminder_text("Set the table", ["Alex", "Sam"])
        == "Reminder for Alex and Sam: Set the table."
    )


async def test_family_goal(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    reached = []
    hass.bus.async_listen("family_goal_reached", reached.append)
    assert (await client.ok("state"))["family_goal"] is None

    await client.ok(
        "settings", family_goal={"name": "Pizza night", "emoji": "🍕", "target": 8}
    )
    goal = (await client.ok("state"))["family_goal"]
    assert goal["name"] == "Pizza night" and goal["progress"] == 0
    assert goal["reached"] is False

    chore = await _chore(client, name="Set the table", members=[alex, sam])
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    goal = (await client.ok("state"))["family_goal"]
    assert goal["progress"] == 5
    # Points together don't come out of anyone's balance.
    assert (
        next(m for m in (await client.ok("state"))["members"] if m["id"] == alex)[
            "points"
        ]
        == 5
    )

    await client.ok("complete", member_id=sam, chore_id=chore["id"])
    await hass.async_block_till_done()
    goal = (await client.ok("state"))["family_goal"]
    assert goal["reached"] is True and goal["progress"] == 8
    assert len(reached) == 1 and reached[0].data["name"] == "Pizza night"

    # Changing the name keeps counting; starting over counts from now.
    await client.ok("settings", family_goal={"name": "Pizza!", "target": 8})
    assert (await client.ok("state"))["family_goal"]["progress"] == 8
    await client.ok(
        "settings", family_goal={"name": "Movie night", "target": 20}, restart_goal=True
    )
    goal = (await client.ok("state"))["family_goal"]
    assert goal["progress"] == 0 and goal["reached"] is False

    res = await client("settings", family_goal={"name": "Nothing", "target": 0})
    assert not res["success"]
    await client.ok("settings", family_goal=None)
    assert (await client.ok("state"))["family_goal"] is None


async def test_speaker_reminder(hass: HomeAssistant, client, freezer):
    alex, sam = await _family(client)
    spoken = async_mock_service(hass, "tts", "speak")
    await client.ok("settings", reminder_tts="tts.piper")
    chore = await _chore(
        client,
        name="Set the table",
        members=[alex, sam],
        remind_time="17:30",
        remind_speakers=["media_player.kitchen", "light.not_a_speaker"],
    )
    assert chore["remind_speakers"] == ["media_player.kitchen"]
    manager = _manager(hass)

    day = dt_util.now().replace(hour=17, minute=0, second=0, microsecond=0)
    day += timedelta(days=1)
    freezer.move_to(day)
    manager.async_tick()
    await hass.async_block_till_done()
    assert not spoken  # not its time yet

    await client.ok("complete", member_id=sam, chore_id=chore["id"])
    freezer.move_to(day.replace(minute=30))
    manager.async_tick()
    manager.async_tick()  # the same minute twice: said once
    await hass.async_block_till_done()
    assert len(spoken) == 1
    call = spoken[0]
    assert call.data["media_player_entity_id"] == ["media_player.kitchen"]
    assert call.data["message"] == "Reminder for Alex: Set the table."
    assert call.data["entity_id"] in ("tts.piper", ["tts.piper"])

    # Done by everyone the next day: nothing is said.
    freezer.move_to(day.replace(minute=29) + timedelta(days=1))
    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await client.ok("complete", member_id=sam, chore_id=chore["id"])
    freezer.move_to(day.replace(minute=30) + timedelta(days=1))
    manager.async_tick()
    await hass.async_block_till_done()
    assert len(spoken) == 1


async def test_reminder_needs_a_voice(hass: HomeAssistant, client):
    res = await client("settings", reminder_tts="light.kitchen")
    assert not res["success"]
    choices = await client.ok("choices")
    assert "voices" in choices and "players" in choices
