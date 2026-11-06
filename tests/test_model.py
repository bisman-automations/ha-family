"""The chore and points rules on their own."""

from datetime import datetime, timedelta

import pytest

from custom_components.family import model


def at(day, hour=12):
    return datetime(2026, 11, day, hour)


def test_todo_points():
    assert model.todo_points("Feed the dog [5]", 2) == ("Feed the dog", 5)
    assert model.todo_points("Feed the dog (5 points)", 2) == ("Feed the dog", 5)
    assert model.todo_points("Feed the dog - 10 pts", 2) == ("Feed the dog", 10)
    assert model.todo_points("Feed the dog", 2) == ("Feed the dog", 2)
    # A number that's part of the chore isn't points.
    assert model.todo_points("Walk 2 dogs", 3) == ("Walk 2 dogs", 3)


def test_period_start():
    # 2026-11-04 is a Wednesday.
    assert model.period_start(at(4, 15), model.REPEAT_DAILY) == datetime(2026, 11, 4)
    assert model.period_start(at(4, 15), model.REPEAT_WEEKLY) == datetime(2026, 11, 2)
    assert model.period_start(at(4, 15), model.REPEAT_ONCE) is None


def _done(member, day, chore_id="bed", review=model.REVIEW_PENDING):
    return {
        "kind": model.KIND_CHORE,
        "chore_id": chore_id,
        "member": member,
        "at": at(day).isoformat(),
        "review": review,
        "points": 5,
    }


def test_daily_chore_for_each_member():
    chore = {"id": "bed", "repeat": "daily", "members": ["a", "b"]}
    entries = [_done("a", 4)]
    done = model.done_by(chore, entries, at(4, 18))
    assert model.can_do("b", chore, done)
    assert not model.can_do("a", chore, done)
    assert not model.can_do("c", chore, done)  # not one of theirs
    # Tomorrow it's back.
    assert model.can_do("a", chore, model.done_by(chore, entries, at(5, 8)))


def test_chore_for_anyone_is_done_once():
    chore = {"id": "bed", "repeat": "weekly", "members": []}
    done = model.done_by(chore, [_done("a", 3)], at(4))
    assert not model.can_do("b", chore, done)


def test_didnt_happen_frees_the_chore_and_takes_points_back():
    chore = {"id": "bed", "repeat": "daily", "members": []}
    entries = [_done("a", 4, review=model.REVIEW_REJECTED)]
    assert model.can_do("a", chore, model.done_by(chore, entries, at(4, 18)))
    assert model.balance(entries, "a") == 0


def test_balance():
    entries = [
        _done("a", 4),
        {
            "kind": model.KIND_REWARD,
            "member": "a",
            "points": -3,
            "at": at(4).isoformat(),
        },
        _done("b", 4),
    ]
    assert model.balance(entries, "a") == 2
    assert model.balance(entries, "b") == 5


def test_disabled_and_once():
    chore = {"id": "bed", "repeat": "once", "members": [], "enabled": False}
    assert not model.can_do("a", chore, set())
    chore["enabled"] = True
    assert not model.can_do("a", chore, model.done_by(chore, [_done("a", 1)], at(20)))


def test_control_kinds_and_actions():
    assert model.control_kind("scene.movie_night") == model.CONTROL_RUN
    assert model.control_kind("light.playroom") == model.CONTROL_TOGGLE
    assert model.control_kind("sensor.outside") == model.CONTROL_VIEW
    assert model.control_kind("automation.morning") is None
    assert model.control_service("scene.movie_night", "run") == ("scene", "turn_on")
    assert model.control_service("button.doorbell", "run") == ("button", "press")
    assert model.control_service("light.playroom", "toggle") == ("light", "toggle")
    assert model.control_service("cover.blinds", "open") == ("cover", "open_cover")
    assert model.control_service("valve.garden", "close") == ("valve", "close_valve")
    assert model.control_service("lock.back_door", "unlock") == ("lock", "unlock")
    assert model.control_service("media_player.kitchen", "play_pause") == (
        "media_player",
        "media_play_pause",
    )
    for entity_id, action in (
        ("sensor.outside", "toggle"),
        ("light.playroom", "unlock"),
        ("scene.movie_night", "toggle"),
    ):
        with pytest.raises(ValueError):
            model.control_service(entity_id, action)


def test_reward_limits():
    reward = {"id": "ice", "limit": "weekly"}
    entries = [
        {"kind": "reward", "reward_id": "ice", "member": "a", "at": at(2).isoformat()},
        {"kind": "reward", "reward_id": "ice", "member": "b", "at": at(1).isoformat()},
        {"kind": "reward", "reward_id": "tv", "member": "c", "at": at(4).isoformat()},
    ]
    # 2026-11-02 is a Monday: the week starts then.
    assert model.reward_used_by(reward, entries, at(4)) == {"a"}
    assert model.reward_used_by({"id": "ice", "limit": "daily"}, entries, at(2)) == {
        "a"
    }
    assert model.reward_used_by({"id": "ice"}, entries, at(4)) == set()


def test_undo_and_auto_check():
    now = at(4, 12)
    chore = {"kind": "chore", "review": "pending", "at": at(4, 12).isoformat()}
    assert model.can_undo(chore, now)
    assert not model.can_undo({**chore, "review": "approved"}, now)
    assert not model.can_undo(chore, now + timedelta(seconds=61))
    given = {"kind": "reward", "given": "given", "at": now.isoformat()}
    assert not model.can_undo(given, now)
    assert model.can_undo({**given, "tv": "x"}, now)
    assert model.can_undo({**given, "given": "to_give"}, now)

    old = {**chore, "at": at(2).isoformat()}
    assert model.due_for_auto_check([chore, old], now, "day") == [old]
    assert model.due_for_auto_check([chore, old], now, "week") == []
    assert model.due_for_auto_check([chore, old], now, None) == []


def test_points_set_for_an_item():
    rated = {"feed the dog": 7}
    assert model.todo_item_points("Feed  the Dog [3]", 1, rated) == (
        "Feed  the Dog",
        7,
        True,
    )
    assert model.todo_item_points("Walk the dog [3]", 1, rated) == (
        "Walk the dog",
        3,
        False,
    )
    assert model.todo_item_points("Sweep", 1, None) == ("Sweep", 1, False)


def test_streaks_and_bonuses():
    def chore(day, member="a", review="approved"):
        return {
            "kind": "chore",
            "member": member,
            "review": review,
            "at": at(day).isoformat(),
        }

    entries = [
        chore(1),
        chore(2),
        chore(3),
        chore(3),
        chore(2, "b"),
        chore(4, review="rejected"),
    ]
    today = at(4).date()
    # Nothing today yet: still a 3-day streak, counted to yesterday.
    assert model.streak(entries, "a", today) == 3
    assert model.streak([*entries, chore(4)], "a", today) == 4
    assert model.streak(entries, "b", today) == 0
    assert len(model.chores_done_on(entries, at(3).date())) == 2
    assert model.chores_done_on(entries, today) == []

    bonus = {"kind": "bonus", "bonus": "streak", "member": "a", "at": at(4).isoformat()}
    assert model.bonus_given([bonus], "a", "streak", today)
    assert not model.bonus_given(
        [{**bonus, "review": "rejected"}], "a", "streak", today
    )
    assert not model.bonus_given([bonus], "a", "all_done", today)
    assert model.streak_bonus_due(6, 3)
    assert not model.streak_bonus_due(4, 3)
    assert not model.streak_bonus_due(3, 0)


def test_penalties():
    assert model.penalty_points(None, None, None) == 0
    assert model.penalty_points(None, None, 2) == 2
    assert model.penalty_points(None, 10, 2) == 10
    assert model.penalty_points(0, 10, 2) == 0
    assert model.optional_points("", "Penalty") is None
    assert model.optional_points("4", "Penalty") == 4


def test_chores_that_come_back_once_done():
    def done(day, hour=12, review="pending"):
        return {
            "kind": "chore",
            "chore_id": "c",
            "member": "a",
            "review": review,
            "at": at(day, hour).isoformat(),
        }

    # Back 3 days after the day it was done: done on the 2nd, back on the 5th.
    plants = {"id": "c", "repeat": "after_days", "repeat_days": 3}
    entries = [done(2, 20)]
    assert model.done_by(plants, entries, at(2)) == {"a", "*"}
    assert model.done_by(plants, entries, at(4, 23)) == {"a", "*"}
    assert model.done_by(plants, entries, at(5, 0)) == set()
    # Right away: never done.
    assert model.done_by({"id": "c", "repeat": "always"}, entries, at(2)) == set()
    # Once a parent checks it: done only while it's still to check.
    check = {"id": "c", "repeat": "after_check"}
    assert model.done_by(check, [done(1)], at(9)) == {"a", "*"}
    assert model.done_by(check, [done(1, review="approved")], at(1)) == set()
    assert model.done_by(check, [done(1, review="rejected")], at(1)) == set()
