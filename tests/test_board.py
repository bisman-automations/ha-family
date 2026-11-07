"""Notes, meals, today's calendar and the weekly allowance."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.util import dt as dt_util
from tests.test_family import Client, _family, _next, _setup

CAL = "calendar.family"


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def test_notes_anyone_can_add_parents_notes_stay(
    hass: HomeAssistant, hass_ws_client, hass_read_only_access_token
):
    await _setup(hass)
    parent = Client(await hass_ws_client(hass))
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    alex, _sam = await _family(parent)

    mine = (await parent.ok("note/add", text="Dentist at 4", member_id=alex))["note"]
    assert mine["parent"] is True
    kid = (await kiosk.ok("note/add", text=" Soccer   bag by the door "))["note"]
    assert kid["text"] == "Soccer bag by the door" and kid["parent"] is False

    state = await kiosk.ok("state")
    assert [n["text"] for n in state["notes"]] == [
        "Soccer bag by the door",
        "Dentist at 4",
    ]

    # The shared screen can take down a kid's note, not a parent's.
    res = await kiosk("note/remove", note_id=mine["id"])
    assert res["error"]["message"] == "Only a parent can take down a parent's note"
    await kiosk.ok("note/remove", note_id=kid["id"])
    await parent.ok("note/remove", note_id=mine["id"])
    assert (await kiosk.ok("state"))["notes"] == []

    res = await kiosk("note/add", text="   ")
    assert not res["success"]
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    res = await kiosk("note/add", text="Old", until=yesterday)
    assert not res["success"]


async def test_meals_for_the_week(
    hass: HomeAssistant, hass_ws_client, hass_read_only_access_token
):
    await _setup(hass)
    parent = Client(await hass_ws_client(hass))
    kiosk = Client(await hass_ws_client(hass, hass_read_only_access_token))
    today = dt_util.now().date().isoformat()
    await parent.ok("meals", date=today, dinner="Tacos", lunch=" ")
    state = await kiosk.ok("state")
    assert len(state["meals"]) == 7
    assert state["meals"][0] == {"date": today, "dinner": "Tacos"}
    # Only parents plan meals.
    res = await kiosk("meals", date=today, dinner="Ice cream")
    assert res["error"]["code"] == "unauthorized"
    # Emptying a day clears it.
    await parent.ok("meals", date=today, dinner="")
    assert (await kiosk.ok("state"))["meals"][0] == {"date": today}


async def test_todays_calendar(hass: HomeAssistant, client):
    hass.states.async_set(CAL, "off", {"friendly_name": "Family"})
    events = [
        {
            "summary": "Swim lesson",
            "start": "2030-01-01T16:00:00-06:00",
            "end": "2030-01-01T17:00:00-06:00",
        },
        {"summary": "No school", "start": "2030-01-01", "end": "2030-01-02"},
    ]

    async def get_events(call):
        return {CAL: {"events": events}}

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    alex, _sam = await _family(client)
    choices = await client.ok("choices")
    assert choices["calendars"] == [{"entity_id": CAL, "name": "Family"}]
    await client.ok("settings", calendars=[{"entity_id": CAL, "member": alex}])
    await hass.async_block_till_done()
    state = await client.ok("state")
    # All-day events first.
    assert [(e["title"], e["all_day"], e["member"]) for e in state["today"]] == [
        ("No school", True, alex),
        ("Swim lesson", False, alex),
    ]
    assert state["settings"]["calendars"] == [{"entity_id": CAL, "member": alex}]

    # A calendar's event starting reads it again.
    events.append({"summary": "Piano", "start": "2030-01-01T18:00:00-06:00", "end": ""})
    hass.states.async_set(CAL, "on", {"friendly_name": "Family"})
    await hass.async_block_till_done()
    assert len((await client.ok("state"))["today"]) == 3

    # Removing the member keeps the calendar, for everyone.
    await client.ok("delete", collection="members", item_id=alex)
    assert (await client.ok("state"))["settings"]["calendars"][0]["member"] is None


async def test_weekly_allowance_and_money(hass: HomeAssistant, client, freezer):
    sunday = _next(6, 8)
    freezer.move_to(sunday - timedelta(hours=2))
    alex, sam = await _family(client)
    await client.ok(
        "save", collection="members", item={"id": alex, "name": "Alex", "allowance": 10}
    )
    await client.ok(
        "settings", allowance_day=6, allowance_hour=8, point_value=0.25, currency="$"
    )
    state = await client.ok("state")
    assert state["money"] == {"value": 0.25, "currency": "$"}
    assert {m["name"]: m["points"] for m in state["members"]} == {"Alex": 0, "Sam": 0}

    freezer.move_to(sunday + timedelta(minutes=1))
    async_fire_time_changed(hass, sunday + timedelta(hours=1))
    await hass.async_block_till_done()
    state = await client.ok("state")
    assert {m["name"]: m["points"] for m in state["members"]} == {"Alex": 10, "Sam": 0}
    assert state["recent"][0]["kind"] == "allowance"

    # Once a week only.
    freezer.move_to(sunday + timedelta(hours=3))
    async_fire_time_changed(hass, sunday + timedelta(hours=3))
    await hass.async_block_till_done()
    assert (await client.ok("state"))["members"][0]["points"] == 10

    res = await client("settings", point_value=-1)
    assert not res["success"]
    _ = sam
