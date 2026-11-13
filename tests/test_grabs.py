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
    assert own == {"total": 2, "left": 2, "done": False, "missed": 0}
    assert _member(await client.ok("state"), sam)["own_today"]["total"] == 0

    done = await client.ok("complete", member_id=alex, chore_id=grab["id"])
    assert not done["entry"].get("bonuses")
    await client.ok("complete", member_id=alex, chore_id=bed["id"])
    assert _member(await client.ok("state"), alex)["own_today"]["left"] == 1
    done = await client.ok("complete", member_id=alex, chore_id=teeth["id"])
    assert [b["title"] for b in done["entry"]["bonuses"]] == ["All done today!"]
    member = _member(await client.ok("state"), alex)
    assert member["own_today"] == {"total": 2, "left": 0, "done": True, "missed": 0}
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


async def test_lists_can_show_only_items_due(hass: HomeAssistant, client, freezer):
    from homeassistant.core import ServiceCall, SupportsResponse
    from tests.test_family import TODO

    freezer.move_to(
        dt_util.start_of_local_day(dt_util.now() + timedelta(days=30)).replace(hour=10)
    )
    today = dt_util.now().date()
    at = lambda h: dt_util.start_of_local_day(today).replace(hour=h).isoformat()  # noqa: E731
    items = [
        {"uid": "1", "summary": "No date", "status": "needs_action"},
        {
            "uid": "2",
            "summary": "Overdue",
            "status": "needs_action",
            "due": (today - timedelta(days=2)).isoformat(),
        },
        {
            "uid": "3",
            "summary": "Today",
            "status": "needs_action",
            "due": today.isoformat(),
        },
        {"uid": "4", "summary": "This morning", "status": "needs_action", "due": at(9)},
        {"uid": "5", "summary": "Tonight", "status": "needs_action", "due": at(18)},
        {
            "uid": "6",
            "summary": "Later",
            "status": "needs_action",
            "due": (today + timedelta(days=5)).isoformat(),
        },
    ]

    async def get_items(call: ServiceCall):
        return {TODO: {"items": items}}

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set(TODO, "6", {"friendly_name": "Chores"})
    await _family(client)

    async def names() -> set[str]:
        return {c["name"] for c in (await client.ok("state"))["chores"]}

    await client.ok(
        "save", collection="todo_lists", item={"entity_id": TODO, "points": 1}
    )
    assert len(await names()) == 6
    await client.ok(
        "save",
        collection="todo_lists",
        item={"entity_id": TODO, "points": 1, "due_only": True},
    )
    assert await names() == {"No date", "Overdue", "Today", "This morning"}
    # Its time comes.
    freezer.move_to(dt_util.start_of_local_day(today).replace(hour=18, minute=1))
    assert "Tonight" in await names()


async def test_done_today_stays_done_and_late_ones_are_missed(
    hass: HomeAssistant, client, freezer
):
    freezer.move_to(
        dt_util.start_of_local_day(dt_util.now() + timedelta(days=30)).replace(hour=7)
    )
    alex, sam = await _family(client)
    ready = await _chore(
        client,
        name="Get ready",
        members=[alex, sam],
        repeat="after_check",
        from_time="06:30",
        until_time="08:00",
    )
    await client.ok("complete", member_id=alex, chore_id=ready["id"])
    state = await client.ok("state")
    # Checked: it comes back, but Alex has done it today.
    await client.ok("review", entry_id=state["to_check"][0]["id"], approved=True)
    freezer.move_to(dt_util.now().replace(hour=9))
    state = await client.ok("state")
    assert _member(state, alex)["own_today"]["left"] == 0
    # Sam didn't, and its hours are over: missed.
    assert _member(state, sam)["own_today"] == {
        "total": 1,
        "left": 1,
        "done": False,
        "missed": 1,
    }


async def test_a_parents_chores_need_no_checking(
    hass: HomeAssistant, client, hass_admin_user, hass_read_only_user
):
    hass.states.async_set("person.dad", "home", {"user_id": hass_admin_user.id})
    hass.states.async_set("person.kid", "home", {"user_id": hass_read_only_user.id})
    dad = (
        await client.ok(
            "save", collection="members", item={"name": "Dad", "person": "person.dad"}
        )
    )["item"]["id"]
    kid = (
        await client.ok(
            "save", collection="members", item={"name": "Kid", "person": "person.kid"}
        )
    )["item"]["id"]
    vitamins = await _chore(client, name="Vitamins", members=[dad, kid])
    done = await client.ok("complete", member_id=dad, chore_id=vitamins["id"])
    assert done["entry"]["review"] == "approved"
    await client.ok("complete", member_id=kid, chore_id=vitamins["id"])
    to_check = (await client.ok("state"))["to_check"]
    assert [e["member"] for e in to_check] == [kid]


async def test_a_chore_uses_the_item_already_on_its_list(hass: HomeAssistant, client):
    from tests.test_family import FakeTodoList, _sync

    alex, _sam = await _family(client)
    todo = FakeTodoList(hass, "todo.house")
    tomorrow = (dt_util.now().date() + timedelta(days=1)).isoformat()
    todo.items.append(
        {
            "uid": "mine",
            "summary": "Vacuum all carpet",
            "status": "needs_action",
            "due": tomorrow,
        }
    )
    chore = await _chore(
        client,
        name="Vacuum All Carpet",
        members=[alex],
        todo_list="todo.house",
        due_only=True,
    )
    await _sync(hass)
    # The item that was there is used, not a second one.
    assert len(todo.items) == 1
    names = lambda state: [c["name"] for c in state["chores"]]  # noqa: E731
    # Due tomorrow: not shown yet.
    assert "Vacuum All Carpet" not in names(await client.ok("state"))

    # Due today on the list: it shows once the list is read again.
    todo.items[0]["due"] = dt_util.now().date().isoformat()
    hass.config_entries.async_entries("family")[0].runtime_data.todo_sync.schedule()
    await _sync(hass)
    assert "Vacuum All Carpet" in names(await client.ok("state"))

    await client.ok("complete", member_id=alex, chore_id=chore["id"])
    await _sync(hass)
    assert todo.items[0]["status"] == "completed"

    # The chore goes: the item was there before, so it stays on the list.
    await client.ok("delete", collection="chores", item_id=chore["id"])
    await _sync(hass)
    assert [i["uid"] for i in todo.items] == ["mine"]


async def test_section_order(hass: HomeAssistant, client):
    settings = await client.ok(
        "settings", section_order=["lately", "notes", "lately", "nope"]
    )
    order = settings["settings"]["section_order"]
    # Known sections once each, the rest after them in the usual order.
    assert order[:2] == ["lately", "notes"]
    assert sorted(order) == sorted(
        [
            "going",
            "chores",
            "grabs",
            "notes",
            "today",
            "meals",
            "done",
            "rewards",
            "home",
            "lately",
        ]
    )
    assert (await client.ok("state"))["section_order"] == order


async def test_one_tile_per_chore(hass: HomeAssistant, client):
    from tests.test_family import FakeTodoList, _sync

    alex, _sam = await _family(client)
    todo = FakeTodoList(hass, "todo.house")
    for uid, name in [
        ("a", "Set table"),
        ("b", "Wipe counters"),
        ("c", "wipe  Counters"),
        ("d", "Feed the dog"),
    ]:
        todo.items.append({"uid": uid, "summary": name, "status": "needs_action"})
    await client.ok(
        "save", collection="todo_lists", item={"entity_id": "todo.house", "points": 1}
    )
    await _chore(client, name="Set Table", members=[alex])
    await _chore(client, name="Feed the cat", members=[alex], todo_list="todo.house")
    await _sync(hass)
    chores = (await client.ok("state"))["chores"]
    names = [c["name"] for c in chores]
    # The dashboard chore first; its namesake on the list and the list's
    # repeated item aren't shown again.
    assert names.index("Set Table") < names.index("Wipe counters")
    assert "Set table" not in names
    assert names.count("Wipe counters") + names.count("wipe  Counters") == 1
    assert "Feed the dog" in names
    # A dashboard chore kept on a list shows that list's name.
    cat = next(c for c in chores if c["name"] == "Feed the cat")
    assert cat["on_list"] == hass.states.get("todo.house").name


async def test_hide_empty_sections(hass: HomeAssistant, client):
    assert (await client.ok("state"))["hide_empty_sections"] is False
    await client.ok("settings", hide_empty_sections=True)
    assert (await client.ok("state"))["hide_empty_sections"] is True


async def test_leave_out_items(hass: HomeAssistant, client):
    from tests.test_family import FakeTodoList, _sync

    await _family(client)
    todo = FakeTodoList(hass, "todo.house")
    for uid, name in [("a", "Pay the bill"), ("b", "Feed the dog")]:
        todo.items.append({"uid": uid, "summary": name, "status": "needs_action"})
    await client.ok(
        "save",
        collection="todo_lists",
        item={
            "entity_id": "todo.house",
            "points": 1,
            "item_skip": {"pay the bill": True},
        },
    )
    await _sync(hass)
    names = [c["name"] for c in (await client.ok("state"))["chores"]]
    assert "Pay the bill" not in names and "Feed the dog" in names
    # Still on the list, and back once it's unticked.
    assert len(todo.items) == 2
    await client.ok(
        "save",
        collection="todo_lists",
        item={
            "entity_id": "todo.house",
            "points": 1,
            "item_skip": {"Pay the bill": False},
        },
    )
    names = [c["name"] for c in (await client.ok("state"))["chores"]]
    assert "Pay the bill" in names


async def test_quick_points(hass: HomeAssistant, client):
    alex, _sam = await _family(client)
    settings = await client.ok(
        "settings",
        quick_points=[
            {"label": " Kind to a sibling ", "emoji": "💛", "points": 2},
            {"label": "Not listening", "points": -1},
            {"label": "", "points": 3},  # no label: dropped
            {"label": "Nothing", "points": 0},  # no points: dropped
        ],
    )
    assert settings["settings"]["quick_points"] == [
        {"label": "Kind to a sibling", "emoji": "💛", "points": 2},
        {"label": "Not listening", "emoji": "", "points": -1},
    ]
    state = await client.ok("state")
    assert len(state["settings"]["quick_points"]) == 2
    # A tap is a points change with the button's name, so it shows in History.
    before = next(m for m in state["members"] if m["id"] == alex)["points"]
    reply = await client.ok("adjust", member_id=alex, points=-1, reason="Not listening")
    assert reply["points"] == before - 1
    assert reply["entry"]["title"] == "Not listening"
