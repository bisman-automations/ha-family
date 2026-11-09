"""Own chores and chores up for grabs: what counts for the all-done bonus and streaks."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from tests.test_family import DOMAIN, Client, _family, _setup


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _chore(client: Client, **item) -> dict:
    return (await client.ok("save", collection="chores", item={"points": 2, **item}))[
        "item"
    ]


def _member(state: dict, member_id: str) -> dict:
    return next(m for m in state["members"] if m["id"] == member_id)


async def test_up_for_grabs_for_some_people(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    grab = await _chore(client, name="Pick up toys", members=[alex, sam], grab=True)
    assert grab["grab"] is True
    state = await client.ok("state")
    [chore] = [c for c in state["chores"] if c["id"] == grab["id"]]
    assert chore["grab"] is True
    assert sorted(chore["can"]) == sorted([alex, sam])
    # Whoever's first: once Alex has, it's gone for Sam too.
    await client.ok("complete", member_id=alex, chore_id=grab["id"])
    res = await client("complete", member_id=sam, chore_id=grab["id"])
    assert not res["success"]
    # Taking turns is always their own chore.
    turns = await _chore(
        client, name="Dishes", members=[alex, sam], grab=True, turns=True
    )
    assert turns["grab"] is False


async def test_only_own_chores_finish_the_day(hass: HomeAssistant, client):
    alex, sam = await _family(client)
    await client.ok("settings", bonus_all_done=5)
    bed = await _chore(client, name="Make your bed", members=[alex])
    teeth = await _chore(client, name="Brush teeth", members=[alex])
    grab = await _chore(client, name="Set the table", members=[alex, sam], grab=True)
    await _chore(client, name="Feed the cat")  # nobody picked: up for grabs

    own = _member(await client.ok("state"), alex)["own_today"]
    assert own == {"total": 2, "left": 2, "done": False}
    assert _member(await client.ok("state"), sam)["own_today"]["total"] == 0

    done = await client.ok("complete", member_id=alex, chore_id=grab["id"])
    assert not done["entry"].get("bonuses")
    await client.ok("complete", member_id=alex, chore_id=bed["id"])
    assert _member(await client.ok("state"), alex)["own_today"]["left"] == 1
    done = await client.ok("complete", member_id=alex, chore_id=teeth["id"])
    assert [b["title"] for b in done["entry"]["bonuses"]] == ["All done today!"]
    member = _member(await client.ok("state"), alex)
    assert member["own_today"] == {"total": 2, "left": 0, "done": True}
    assert member["streak"] == 1


async def test_a_streak_needs_all_own_chores(hass: HomeAssistant, client):
    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    alex, _sam = await _family(client)
    await _chore(client, name="Make your bed", members=[alex])
    # Yesterday and the day before were before the new rule: any chore counted.
    manager.settings["streak_rule_from"] = dt_util.now().date().isoformat()
    for days in (2, 1):
        manager.entries.append(
            {
                "id": f"old{days}",
                "at": (dt_util.now() - timedelta(days=days)).isoformat(),
                "kind": "chore",
                "member": alex,
                "title": "Anything",
                "points": 1,
                "chore_id": "gone",
                "review": "approved",
            }
        )
    assert _member(await client.ok("state"), alex)["streak"] == 2
    # From the new rule on, a chore up for grabs doesn't keep it going.
    manager.settings["streak_rule_from"] = (
        dt_util.now().date() - timedelta(days=1)
    ).isoformat()
    assert _member(await client.ok("state"), alex)["streak"] == 0


async def test_to_do_lists_can_be_up_for_grabs(hass: HomeAssistant, client):
    manager = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    alex, sam = await _family(client)
    hass.states.async_set("todo.chores", "1", {"friendly_name": "Chores"})
    await manager.async_save_todo_list(
        {"entity_id": "todo.chores", "members": [alex, sam], "grab": True}
    )
    assert manager.todo_lists[0]["grab"] is True
    await manager.async_save_todo_list(
        {"entity_id": "todo.chores", "members": [alex], "grab": False}
    )
    assert manager.todo_lists[0]["grab"] is False
