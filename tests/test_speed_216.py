"""2.16.0: less work for the same answers.

The ledger takes new entries without regrouping, streaks and family/state
answers are kept until something they depend on changes, points sensors
write only when what they show changed, to-do lists aren't read again for
Family's own changes, the reads of other integrations wait for Home
Assistant to start and calendars are read together, the hourly jobs share
one timer, old history is folded in every hour, and the card's loader is the
only Family script on every dashboard page.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import random
from typing import Any
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.family import (
    ledger as ledger_module,
    manager as manager_module,
    model,
    photos,
)
from custom_components.family.const import DOMAIN, KEEP_HISTORY_DAYS, SIGNAL_CHANGED
from custom_components.family.ledger import Ledger
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, SupportsResponse, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from .test_family import Client, FakeTodoList, _setup, _sync

START = datetime(2026, 10, 1, 7, tzinfo=dt_util.UTC)


def _random_entries(rng: random.Random, start: int, count: int) -> list[dict]:
    """Entries like the ledger's, some without a time and some at equal times."""
    entries = []
    for i in range(start, start + count):
        entry: dict[str, Any] = {
            "id": f"e{i}",
            "member": rng.choice("abc"),
            "kind": rng.choice(["chore", "bonus", "reward"]),
        }
        if rng.random() < 0.8:
            entry["chore_id"] = rng.choice(["x", "y", "z"])
        roll = rng.random()
        if roll < 0.9:
            # Mostly newer, sometimes older than the end (a late review), and
            # sometimes exactly the same time as another.
            hours = rng.choice([rng.randint(0, 2000), 1000])
            entry["at"] = (START + timedelta(hours=hours)).isoformat()
        elif roll < 0.95:
            entry["at"] = "not a time"
        entries.append(entry)
    return entries


def _groups(view: Ledger) -> dict[str, Any]:
    """Everything a ledger hands out, by id, to compare two of them."""

    def ids(items) -> list[str]:
        return [e["id"] for e in items]

    return {
        "chore": {k: ids(v) for k, v in view._by_chore.items()},
        "member": {k: ids(v) for k, v in view._by_member.items()},
        "day": {k: ids(v) for k, v in view._by_day.items()},
        "kind": {k: ids(v) for k, v in view._by_kind.items()},
        "times": list(view._times),
        "in_time": ids(view._in_time),
        "chore_times": {k: list(v) for k, v in view._chore_times.items()},
        "chore_in_time": {k: ids(v) for k, v in view._chore_in_time.items()},
    }


def test_ledger_takes_new_entries_without_regrouping(monkeypatch) -> None:
    """Entries added at the end give the same groups as grouping it all."""
    rng = random.Random(21)
    entries = _random_entries(rng, 0, 50)
    view = Ledger()
    view.current(entries)
    builds: list[int] = []
    real = Ledger._build

    def counted(self, items):
        if self is view:  # not the fresh ledgers it's compared with
            builds.append(len(items))
        return real(self, items)

    monkeypatch.setattr(Ledger, "_build", counted)
    for round_ in range(30):
        version = view.version
        entries.extend(_random_entries(rng, 1000 + round_ * 10, rng.randint(1, 6)))
        view.current(entries)
        assert view.version == version + 1
        assert _groups(view) == _groups(Ledger().current(list(entries)))
    assert builds == []  # every one folded in
    since = START + timedelta(hours=700)
    assert [e["id"] for e in view.since(since)] == [
        e["id"] for e in Ledger().current(list(entries)).since(since)
    ]
    assert view.newest(5) == Ledger().current(list(entries)).newest(5)


def test_ledger_still_regroups_after_a_removal(monkeypatch) -> None:
    rng = random.Random(5)
    entries = _random_entries(rng, 0, 20)
    view = Ledger()
    view.current(entries)
    builds: list[int] = []
    real = Ledger._build
    watched: list[Ledger] = [view]
    monkeypatch.setattr(
        Ledger,
        "_build",
        lambda self, items: (
            builds.append(1) if any(self is w for w in watched) else None,
            real(self, items),
        ),
    )
    # One removed and two added: longer, but the old end moved.
    entries.pop(3)
    entries.extend(_random_entries(rng, 100, 2))
    view.current(entries)
    assert builds == [1]
    assert _groups(view) == _groups(Ledger().current(list(entries)))
    # The last one replaced and one added: the old end isn't the same dict.
    entries[-1] = dict(entries[-1], id="other")
    entries.extend(_random_entries(rng, 200, 1))
    view.current(entries)
    assert builds == [1, 1]
    assert _groups(view) == _groups(Ledger().current(list(entries)))
    # Starting from nothing groups the whole list.
    fresh: list[dict] = []
    other = Ledger()
    watched.append(other)
    other.current(fresh)
    fresh.extend(_random_entries(rng, 300, 3))
    other.current(fresh)
    assert builds == [1, 1, 1, 1]  # the empty list, then the whole list


def _manager(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data


async def _client(hass: HomeAssistant, hass_ws_client) -> Client:
    await _setup(hass)
    return Client(await hass_ws_client(hass))


async def _member(client: Client, name: str) -> str:
    return (await client.ok("save", collection="members", item={"name": name}))["item"][
        "id"
    ]


def _chore_entry(member: str, days_ago: int, chore_id: str) -> dict[str, Any]:
    return {
        "id": f"s{member}{days_ago}{chore_id}",
        "at": (dt_util.now() - timedelta(days=days_ago, minutes=1)).isoformat(),
        "kind": "chore",
        "member": member,
        "title": "Bed",
        "points": 1,
        "chore_id": chore_id,
        "review": "approved",
    }


async def test_streak_kept_until_something_changes(
    hass: HomeAssistant, hass_ws_client, freezer
) -> None:
    client = await _client(hass, hass_ws_client)
    alex = await _member(client, "Alex")
    manager = _manager(hass)
    # Before the rule's day any chore keeps a streak going.
    manager.settings["streak_rule_from"] = (
        dt_util.now().date() + timedelta(days=1)
    ).isoformat()
    chore = (
        await client.ok(
            "save", collection="chores", item={"name": "Bed", "members": [alex]}
        )
    )["item"]
    for days in (3, 2, 1):
        manager.entries.append(_chore_entry(alex, days, chore["id"]))
    manager.changed()
    worked: list[str] = []
    real = model.streak

    def counted(entries, member_id, *args, **kwargs):
        worked.append(member_id)
        return real(entries, member_id, *args, **kwargs)

    manager._streaks.clear()
    with patch.object(manager_module.model, "streak", counted):
        assert manager.streak(alex) == 3
        assert manager.streak(alex) == 3
        assert len(worked) == 1  # kept
        # Done today: a new entry, worked out again.
        manager.entries.append(_chore_entry(alex, 0, chore["id"]))
        assert manager.streak(alex) == 4
        assert len(worked) == 2
        # A chore changed (saved): its days can change the streak.
        manager.changed()
        manager.streak(alex)
        assert len(worked) == 3
        # done_today is its own answer.
        manager.streak(alex, done_today=True)
        assert len(worked) == 4
        # The streak rule, then the next day.
        manager.settings["streak_rule_from"] = dt_util.now().date().isoformat()
        manager.streak(alex)
        assert len(worked) == 5
        freezer.tick(timedelta(days=1))
        manager.streak(alex)
        assert len(worked) == 6


async def test_state_shared_until_a_change(hass: HomeAssistant, hass_ws_client):
    client = await _client(hass, hass_ws_client)
    alex = await _member(client, "Alex")
    manager = _manager(hass)
    made: list[int] = []
    real = manager._snapshot

    def counted(*args, **kwargs):
        made.append(1)
        return real(*args, **kwargs)

    manager._snapshot = counted
    first = await client.ok("state")
    second = await client.ok("state")
    assert len(made) == 1 and first == second  # the same moment: shared
    # A change told to the dashboards: a new answer, with its revision.
    revision = first["revision"]
    await client.ok("adjust", member_id=alex, points=3, reason="Nice")
    third = await client.ok("state")
    assert len(made) == 2 and third["revision"] > revision
    # Saved without telling anyone (a setting): still a new answer.
    manager.settings["shopping_list"] = "todo.shopping"
    manager.save()
    assert (await client.ok("state"))["revision"] == third["revision"]
    assert len(made) == 3
    # Not for long: past the share time it's worked out again.
    with patch.object(manager_module, "SNAPSHOT_SHARE_SECONDS", 0):
        await client.ok("state")
    assert len(made) == 4


async def test_push_says_the_revision(hass: HomeAssistant, hass_ws_client):
    client = await _client(hass, hass_ws_client)
    alex = await _member(client, "Alex")
    await client.ws.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.ws.receive_json())["success"]
    await client.ws.send_json_auto_id(
        {"type": f"{DOMAIN}/adjust", "member_id": alex, "points": 2}
    )
    got = [await client.ws.receive_json(), await client.ws.receive_json()]
    event = next(m for m in got if m["type"] == "event")["event"]
    state = await client.ok("state")
    # The state read after the change has the revision the push said.
    assert event["changed"] is True
    assert state["revision"] == event["revision"]


async def test_points_sensor_writes_only_when_it_changes(
    hass: HomeAssistant, hass_ws_client
):
    client = await _client(hass, hass_ws_client)
    alex = await _member(client, "Alex")
    sam = await _member(client, "Sam")
    await hass.async_block_till_done()
    writes: list[str] = []
    hass.bus.async_listen(
        "state_changed",
        lambda event: writes.append(event.data["entity_id"]),
    )
    manager = _manager(hass)
    # Something that changes neither one's points, rewards or chores.
    manager.changed()
    await hass.async_block_till_done()
    assert writes == []
    before = [s.last_reported for s in hass.states.async_all("sensor")]
    manager.changed()
    await hass.async_block_till_done()
    # Not even written again with the same state.
    assert [s.last_reported for s in hass.states.async_all("sensor")] == before
    await client.ok("adjust", member_id=alex, points=5)
    await hass.async_block_till_done()
    alex_sensor = next(
        s for s in hass.states.async_all("sensor") if s.attributes["member"] == "Alex"
    )
    assert alex_sensor.state == "5"
    assert writes == [alex_sensor.entity_id]  # only Alex's
    assert sam  # Sam's sensor stays as it was


async def test_own_todo_change_not_read_twice(hass: HomeAssistant, hass_ws_client):
    client = await _client(hass, hass_ws_client)
    alex = await _member(client, "Alex")
    todo = FakeTodoList(hass, "todo.kids")
    todo.items.append({"uid": "a", "summary": "Tidy up", "status": "needs_action"})
    todo._state()
    await client.ok(
        "save",
        collection="todo_lists",
        item={"entity_id": "todo.kids", "points": 2, "members": [alex]},
    )
    await _sync(hass)
    manager = _manager(hass)
    reads: list[str] = []
    real = manager.async_refresh_todo

    async def counted(only=None):
        reads.append(only)
        await real(only)

    manager.async_refresh_todo = counted
    told: list[int] = []
    async_dispatcher_connect(hass, SIGNAL_CHANGED, callback(lambda: told.append(1)))
    # Ticking it off from Family reads the list once, not again for its event.
    await client.ok("complete", member_id=alex, chore_id="todo:todo.kids:a")
    await _sync(hass)
    assert reads == ["todo.kids"]
    # A change on the list itself (another app) is read.
    reads.clear()
    todo.items.append({"uid": "b", "summary": "Dishes", "status": "needs_action"})
    todo._state()
    await _sync(hass)
    assert reads == ["todo.kids"]
    assert any(i["uid"] == "b" for i in manager.todo_items["todo.kids"])
    # A state change with the same items: read, but nobody is told.
    reads.clear()
    told.clear()
    hass.states.async_set("todo.kids", "1", {"friendly_name": "Kids", "x": 1})
    await _sync(hass)
    assert reads == ["todo.kids"]
    assert told == []


async def test_waits_for_start_and_reads_calendars_together(hass: HomeAssistant):
    """To-do lists, calendars and Assist are read after Home Assistant has
    started, and every calendar is asked at the same time."""
    for cal in ("calendar.one", "calendar.two"):
        hass.states.async_set(cal, "off", {"friendly_name": cal})
    waiting: list[str] = []
    release = asyncio.Event()

    async def get_events(call):
        waiting.append(call.data["entity_id"])
        await release.wait()
        return {call.data["entity_id"]: {"events": []}}

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Family", data={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    hass.set_state(CoreState.starting)
    with patch.object(
        manager_module.FamilyManager, "async_refresh_todo", AsyncMock()
    ) as refresh:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        manager = entry.runtime_data
        manager.settings["calendars"] = [
            {"entity_id": "calendar.one"},
            {"entity_id": "calendar.two"},
        ]
        refresh.assert_not_awaited()  # not while starting
        assert waiting == []
        hass.set_state(CoreState.running)
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        for _ in range(20):
            await asyncio.sleep(0)
            if len(waiting) == 2:
                break
        # Both calendars asked before either answered.
        assert sorted(waiting) == ["calendar.one", "calendar.two"]
        release.set()
        await hass.async_block_till_done()
        refresh.assert_awaited()


async def test_calendar_refresh_asked_meanwhile_runs_again(
    hass: HomeAssistant, hass_ws_client
):
    await _client(hass, hass_ws_client)
    hass.states.async_set("calendar.one", "off")
    gate = asyncio.Event()
    asked: list[int] = []

    async def get_events(call):
        asked.append(1)
        if len(asked) == 1:
            await gate.wait()
        return {"calendar.one": {"events": []}}

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    manager = _manager(hass)
    manager.settings["calendars"] = [{"entity_id": "calendar.one"}]
    first = hass.async_create_task(manager.calendar.async_refresh())
    await asyncio.sleep(0)
    await manager.calendar.async_refresh()  # while the first one is reading
    gate.set()
    await first
    assert len(asked) == 2  # once more, not dropped


async def test_hourly_jobs_share_one_timer(hass: HomeAssistant, hass_ws_client):
    await _client(hass, hass_ws_client)
    manager = _manager(hass)
    ran: list[str] = []
    with (
        patch.object(manager, "async_auto_check", lambda now=None: ran.append("check")),
        patch.object(manager, "async_allowance", lambda now=None: ran.append("pay")),
        patch.object(manager.todo_sync, "schedule", lambda: ran.append("todo")),
    ):
        # The timer was made at setup with the real methods' wrapper: it calls
        # them through the manager, so the patched ones run.
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1, seconds=1))
        await hass.async_block_till_done()
    assert ran[:3] == ["check", "todo", "pay"]


async def test_old_history_folded_in_every_hour(hass: HomeAssistant, hass_ws_client):
    client = await _client(hass, hass_ws_client)
    alex = await _member(client, "Alex")
    manager = _manager(hass)
    old = {
        "id": "ancient",
        "at": (dt_util.now() - timedelta(days=KEEP_HISTORY_DAYS + 2)).isoformat(),
        "kind": "chore",
        "member": alex,
        "title": "Long ago",
        "points": 7,
        "review": "approved",
    }
    new = dict(old, id="recent", at=dt_util.now().isoformat(), points=1)
    manager.entries[:0] = [old]
    manager.entries.append(new)
    manager.changed()
    assert manager.points(alex) == 8
    manager.async_allowance()
    assert [e["id"] for e in manager.entries] == ["recent"]
    assert manager.carried[alex] == 7
    assert manager.points(alex) == 8  # the same points
    assert manager._prune() is False  # nothing more to fold in


async def test_card_loader_on_every_page_with_cache(hass: HomeAssistant):
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")
    with (
        patch(
            "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths",
            AsyncMock(),
        ) as static,
        patch(
            "homeassistant.components.panel_custom.async_register_panel", AsyncMock()
        ),
        patch("homeassistant.components.frontend.add_extra_js_url") as add_card,
        patch("homeassistant.components.frontend.remove_extra_js_url"),
        patch("homeassistant.components.frontend.async_remove_panel"),
    ):
        entry = await _setup(hass)
        assert await hass.config_entries.async_unload(entry.entry_id)
    (config,) = static.await_args.args[0]
    assert config.cache_headers is True  # every URL has the version
    assert add_card.call_args.args[1].startswith("/family_static/family-card.js?v=")


async def test_photo_prune_skips_files_removed_meanwhile(
    hass: HomeAssistant, hass_ws_client, own_photo_folder, monkeypatch
):
    await _client(hass, hass_ws_client)
    manager = _manager(hass)
    own_photo_folder.mkdir(parents=True, exist_ok=True)
    gone = own_photo_folder / "abc.jpg"
    gone.write_bytes(b"x")
    real_glob = type(own_photo_folder).glob

    def glob_then_remove(self, pattern):
        found = list(real_glob(self, pattern))
        gone.unlink()  # removed by someone else after it was listed
        return iter(found)

    monkeypatch.setattr(type(own_photo_folder), "glob", glob_then_remove)
    await manager.photos.async_prune()  # no FileNotFoundError
    assert photos.KEEP_DAYS > 0


def test_save_delay_folds_bursts() -> None:
    assert manager_module.SAVE_DELAY == 10
    assert ledger_module.Ledger().version == 0
