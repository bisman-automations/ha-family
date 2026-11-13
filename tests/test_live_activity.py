"""The parents' Live Activity of today's chores."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant
from tests.test_family import DOMAIN, Client, _family, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _chore(client: Client, **item) -> dict:
    return (await client.ok("save", collection="chores", item={"points": 2, **item}))[
        "item"
    ]


def _live(sent) -> list:
    return [c.data for c in sent if c.data.get("data", {}).get("live_update")]


async def test_live_activity(hass: HomeAssistant, client):
    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    alex, sam = await _family(client)
    bed = await _chore(client, name="Make your bed", members=[alex, sam])
    await _chore(client, name="Feed the cat", members=[alex])
    await client.ok("settings", notify_targets=["mobile_app_dads_phone"])
    await hass.async_block_till_done()
    assert not _live(sent)  # off until a parent turns it on

    await client.ok("settings", live_activity=True)
    await hass.async_block_till_done()
    [first] = _live(sent)
    assert first["title"] == "Today's chores"
    assert first["message"] == "Alex 0/2 · Sam 0/1"
    assert first["data"]["progress"] == 0 and first["data"]["progress_max"] == 3
    assert first["data"]["tag"].startswith("family-chores-")

    # Nothing it shows changed: nothing new is pushed.
    await client.ok("save", collection="members", item={"id": sam, "name": "Sam"})
    await hass.async_block_till_done()
    assert len(_live(sent)) == 1

    await client.ok("complete", member_id=sam, chore_id=bed["id"])
    await hass.async_block_till_done()
    assert _live(sent)[-1]["message"] == "Alex 0/2 · Sam ✓"
    assert _live(sent)[-1]["data"]["critical_text"] == "1/3"

    # Turned off: it's cleared from the phones.
    await client.ok("settings", live_activity=False)
    await hass.async_block_till_done()
    assert sent[-1].data["message"] == "clear_notification"
    assert sent[-1].data["data"]["tag"] == first["data"]["tag"]


async def test_live_activity_new_day(hass: HomeAssistant, client):
    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    alex, _sam = await _family(client)
    await _chore(client, name="Make your bed", members=[alex])
    await client.ok(
        "settings", notify_targets=["mobile_app_dads_phone"], live_activity=True
    )
    await hass.async_block_till_done()
    count = len(_live(sent))
    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    manager.live.new_day()
    await hass.async_block_till_done()
    assert any(c.data["message"] == "clear_notification" for c in sent)
    # And today's comes back straight away.
    assert len(_live(sent)) == count + 1


async def test_one_per_child(hass: HomeAssistant, client, freezer):
    from datetime import timedelta

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from homeassistant.util import dt as dt_util

    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    alex, sam = await _family(client)
    bed = await _chore(client, name="Make your bed", members=[alex, sam])
    await _chore(client, name="Feed the cat", members=[alex])
    await client.ok(
        "settings",
        notify_targets=["mobile_app_dads_phone"],
        live_activity=True,
        live_per_child=True,
    )
    await hass.async_block_till_done()
    by_tag = {c["data"]["tag"]: c for c in _live(sent)}
    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    family = manager.live.tag
    assert set(by_tag) == {family, f"{family}-{alex}", f"{family}-{sam}"}
    assert by_tag[f"{family}-{alex}"]["title"] == "Alex's chores"
    assert by_tag[f"{family}-{alex}"]["message"] == "0 of 2 done · 2 to go"

    # Sam finishes: "All done!", then it goes after a couple of minutes.
    await client.ok("complete", member_id=sam, chore_id=bed["id"])
    await hass.async_block_till_done()
    assert any(c["title"] == "Sam: all done! 🎉" for c in _live(sent))
    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert any(
        c.data["message"] == "clear_notification"
        and c.data["data"]["tag"] == f"{family}-{sam}"
        for c in sent
    )
    # The family one stays and keeps going.
    assert any(
        c["data"]["tag"] == family and c["message"] == "Alex 0/2 · Sam ✓"
        for c in _live(sent)
    )

    # One per child off: theirs go, the family one stays.
    before = len(sent)
    await client.ok("settings", live_per_child=False)
    await hass.async_block_till_done()
    cleared = {
        c.data["data"]["tag"]
        for c in sent[before:]
        if c.data["message"] == "clear_notification"
    }
    assert f"{family}-{alex}" in cleared and family not in cleared


async def test_show_from(hass: HomeAssistant, client, freezer):
    from homeassistant.util import dt as dt_util

    sent = async_mock_service(hass, "notify", "mobile_app_dads_phone")
    alex, _sam = await _family(client)
    await _chore(client, name="Make your bed", members=[alex])
    early = dt_util.now().replace(hour=5, minute=0, second=0, microsecond=0)
    freezer.move_to(early)
    await client.ok(
        "settings",
        notify_targets=["mobile_app_dads_phone"],
        live_activity=True,
        live_from="06:30",
    )
    await hass.async_block_till_done()
    assert not _live(sent)  # not yet

    res = await client("settings", live_from="half past six")
    assert not res["success"]

    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    freezer.move_to(early.replace(hour=6, minute=30))
    manager.async_tick()
    await hass.async_block_till_done()
    assert _live(sent)[-1]["message"] == "Alex 0/1"
