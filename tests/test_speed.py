"""2.15.1: the dashboard does the same work with less: ledger lookups, one
"changed" per moment, badges only when the ledger changed, goals read from
their start, and a busy ledger's snapshot answers like reading it all."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import random

import pytest

from custom_components.family import model
from custom_components.family.const import SIGNAL_CHANGED
from custom_components.family.ledger import Ledger
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .test_family import Client, _setup


def _entry(i: int, at: str, **more) -> dict:
    return {"id": f"e{i}", "at": at, "member": "a", "kind": "chore", **more}


def test_ledger_groups_and_rebuilds() -> None:
    entries = [
        _entry(1, "2026-11-10T08:00:00+00:00", chore_id="dishes"),
        _entry(2, "2026-11-11T08:00:00+00:00", chore_id="bins", member="b"),
        _entry(3, "2026-11-11T09:00:00+00:00", kind="bonus"),
    ]
    ledger = Ledger()
    view = ledger.current(entries)
    assert [e["id"] for e in view.chore("dishes")] == ["e1"]
    assert [e["id"] for e in view.member("a")] == ["e1", "e3"]
    assert [e["id"] for e in view.day(date(2026, 11, 11))] == ["e2", "e3"]
    assert [e["id"] for e in view.kind("bonus")] == ["e3"]
    assert view.chore("nothing") == ()
    since = datetime.fromisoformat("2026-11-11T08:00:00+00:00")
    assert [e["id"] for e in view.since(since)] == ["e2", "e3"]
    version = view.version
    # Nothing changed: the same groups.
    assert ledger.current(entries).version == version
    # A review edits the entry in place; the groups hold the same dict.
    entries[0]["review"] = "rejected"
    assert ledger.current(entries).chore("dishes")[0]["review"] == "rejected"
    # Added, removed, swapped or another list: rebuilt.
    entries.append(_entry(4, "2026-11-12T08:00:00+00:00", chore_id="dishes"))
    assert [e["id"] for e in ledger.current(entries).chore("dishes")] == ["e1", "e4"]
    entries.remove(entries[1])
    assert ledger.current(entries).member("b") == ()
    entries[-1] = _entry(5, "2026-11-12T08:00:00+00:00", chore_id="bins")
    assert [e["id"] for e in ledger.current(entries).chore("bins")] == ["e5"]
    assert [e["id"] for e in ledger.current([]).member("a")] == []
    assert ledger.version > version


def test_ledger_answers_like_the_whole_list() -> None:
    """The model's helpers give the same answer from a group as from all."""
    rng = random.Random(4)
    start = datetime(2026, 10, 1, 7, tzinfo=dt_util.UTC)
    entries = [
        {
            "id": f"e{i}",
            "at": (start + timedelta(hours=rng.randint(0, 900))).isoformat(),
            "member": rng.choice("abc"),
            "kind": rng.choice(["chore", "chore", "bonus", "reward"]),
            "chore_id": rng.choice(["x", "y", "z"]),
            "bonus": "all_done",
            "points": rng.randint(1, 5),
            "review": rng.choice(["approved", "pending", "rejected"]),
        }
        for i in range(400)
    ]
    view = Ledger().current(entries)
    now = start + timedelta(days=20)
    chore = {"id": "x", "repeat": "weekly", "members": ["a", "b"]}
    assert model.done_by(chore, view.chore("x"), now) == model.done_by(
        chore, entries, now
    )
    for member in "abc":
        assert model.balance(view.member(member), member) == model.balance(
            entries, member
        )
        assert model.all_done_days(view.member(member), member) == (
            model.all_done_days(entries, member)
        )
        assert model.streak(view.member(member), member, now.date()) == (
            model.streak(entries, member, now.date())
        )
    day = (start + timedelta(days=5)).date()
    assert model.chores_done_on(view.day(day), day, "a") == model.chores_done_on(
        entries, day, "a"
    )
    since = (start + timedelta(days=12)).isoformat()
    assert model.goal_progress(
        view.since(datetime.fromisoformat(since)), since
    ) == model.goal_progress(entries, since)


@pytest.fixture
async def client(hass: HomeAssistant, hass_ws_client):
    await _setup(hass)
    return Client(await hass_ws_client(hass))


def _manager(hass: HomeAssistant):
    return hass.config_entries.async_entries("family")[0].runtime_data


async def test_one_changed_per_moment(hass: HomeAssistant, client) -> None:
    """Checking several chores at once tells the dashboards once."""
    await client.ok("save", collection="members", item={"name": "Alex"})
    manager = _manager(hass)
    await hass.async_block_till_done()
    told = []
    unsub = async_dispatcher_connect(
        hass, SIGNAL_CHANGED, callback(lambda: told.append(1))
    )
    manager.changed()
    manager.changed()
    manager.changed()
    assert told == []  # told after the moment, not three times inside it
    await hass.async_block_till_done()
    assert told == [1]
    manager.changed()
    await hass.async_block_till_done()
    assert told == [1, 1]
    unsub()


async def test_badges_only_when_the_ledger_changed(hass: HomeAssistant, client) -> None:
    alex = (await client.ok("save", collection="members", item={"name": "Alex"}))[
        "item"
    ]["id"]
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Dishes", "points": 2, "members": [alex]},
        )
    )["item"]
    manager = _manager(hass)
    calls = []
    real = manager.streak

    def counted(member_id, done_today=False):
        calls.append(member_id)
        return real(member_id, done_today)

    manager.streak = counted
    manager.changed()
    assert calls == []  # nothing new since the last check
    reply = await client.ok("complete", member_id=alex, chore_id=chore["id"])
    assert calls  # a chore done: checked, and the first badge comes back
    assert any(b["key"] == "first_chore" for b in reply["badges"])
    calls.clear()
    manager.changed()
    assert calls == []


async def test_busy_snapshot_matches(hass: HomeAssistant, client) -> None:
    """A long ledger: points, today's counts and goals as before."""
    ids = [
        (await client.ok("save", collection="members", item={"name": n}))["item"]["id"]
        for n in ("Alex", "Sam")
    ]
    chore = (
        await client.ok(
            "save",
            collection="chores",
            item={"name": "Dishes", "points": 3, "members": ids},
        )
    )["item"]
    await client.ok("family_goal/save", name="Pizza", target=10_000)
    manager = _manager(hass)
    now = dt_util.now()
    for i in range(1500):
        manager.entries.append(
            {
                "id": f"old{i}",
                "at": (now - timedelta(hours=3 * i + 1)).isoformat(),
                "kind": "chore",
                "member": ids[i % 2],
                "title": "Dishes",
                "points": 3,
                "chore_id": chore["id"],
                "review": "rejected" if i % 7 == 0 else "approved",
            }
        )
    manager.changed()
    await hass.async_block_till_done()
    state = await client.ok("state")
    for member in state["members"]:
        assert member["points"] == model.balance(manager.entries, member["id"])
        assert member["done_today"] == len(
            model.chores_done_on(manager.entries, now.date(), member["id"])
        )
    goal = state["family_goals"][0]
    assert goal["progress"] == model.goal_progress(manager.entries, goal["since"])
    assert [e["id"] for e in state["recent"]] == [
        e["id"] for e in sorted(manager.entries, key=lambda e: e["at"], reverse=True)
    ][:30]


def test_chore_since_reads_only_the_period() -> None:
    """``done_by`` from a chore's entries since its period began is the same
    as from all of them, for every kind of repeat."""
    rng = random.Random(9)
    start = datetime(2026, 10, 1, 7, tzinfo=dt_util.UTC)
    entries = [
        {
            "id": f"e{i}",
            "at": (start + timedelta(hours=rng.randint(0, 1200))).isoformat(),
            "member": rng.choice("abc"),
            "kind": "chore",
            "chore_id": "x",
            "review": rng.choice(["approved", "pending", "rejected"]),
        }
        for i in range(300)
    ]
    view = Ledger().current(entries)
    now = start + timedelta(days=30, hours=5)
    for chore in (
        {"id": "x", "repeat": "daily", "members": ["a", "b"]},
        {"id": "x", "repeat": "weekly"},
        {"id": "x", "repeat": "once", "members": ["c"]},
        {"id": "x", "repeat": "after_days", "repeat_days": 3},
        {"id": "x", "repeat": "after_check"},
        {"id": "x", "repeat": "always"},
    ):
        recent = view.chore_since("x", model.done_since(chore, now))
        assert model.done_by(chore, recent, now) == model.done_by(chore, entries, now)
    assert view.chore_since("nothing", now) == ()
