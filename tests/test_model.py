"""The chore and points rules on their own."""

from datetime import date, datetime, timedelta

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


def test_set_days_and_hours():
    # 2026-11-03 is a Tuesday (weekday 1).
    tuesday = {"days": [1]}
    assert model.available(tuesday, at(3))
    assert not model.available(tuesday, at(4))
    assert model.available({}, at(4))
    morning = {"from_time": "06:00", "until_time": "09:00"}
    assert model.available(morning, at(4, 7))
    assert not model.available(morning, at(4, 9))
    assert not model.available(morning, at(4, 5))
    # Only a start, or only an end.
    assert model.available({"from_time": "18:00"}, at(4, 20))
    assert not model.available({"from_time": "18:00"}, at(4, 17))
    assert not model.available({"until_time": "10:00"}, at(4, 11))
    # Across midnight: after midnight, the day it started counts.
    bedtime = {"days": [1], "from_time": "20:00", "until_time": "01:00"}
    assert model.available(bedtime, at(3, 21))
    assert model.available(bedtime, datetime(2026, 11, 4, 0, 30))
    assert not model.available(bedtime, datetime(2026, 11, 4, 21))
    assert not model.available(bedtime, at(3, 12))


def test_clean_days_and_times():
    assert model.clean_days(["1", 3, 3]) == [1, 3]
    assert model.clean_days(range(7)) == []  # every day
    with pytest.raises(ValueError):
        model.clean_days([7])
    assert model.clean_time("7:5", "From") == "07:05"
    assert model.clean_time("", "From") is None
    with pytest.raises(ValueError):
        model.clean_time("25:00", "From")
    with pytest.raises(ValueError):
        model.clean_time("soon", "From")


def _did(chore_id, day, member="a", review="pending"):
    return {
        "kind": "chore",
        "chore_id": chore_id,
        "member": member,
        "at": at(day).isoformat(),
        "review": review,
    }


def test_turns():
    chore = {
        "id": "dishes",
        "members": ["a", "b", "c"],
        "turns": True,
        "turn_first": "b",
        "turn_from": at(2, 8).isoformat(),  # a Monday
    }
    # Each time it's done: the next person, and a chore that didn't happen
    # doesn't move it on.
    assert model.turn_member(chore, [], at(2)) == "b"
    entries = [_did("dishes", 2, "b")]
    assert model.turn_member(chore, entries, at(2, 13)) == "c"
    entries.append(_did("dishes", 3, "c", review="rejected"))
    assert model.turn_member(chore, entries, at(3, 13)) == "c"
    entries.append(_did("dishes", 4, "c"))
    assert model.turn_member(chore, entries, at(4, 13)) == "a"
    # Done before the turns were set doesn't count.
    assert model.turn_member(chore, [_did("dishes", 1, "a")], at(2)) == "b"
    # Each day, or each week (from Monday).
    daily = {**chore, "turn_every": "day"}
    assert [model.turn_member(daily, [], at(d)) for d in (2, 3, 4, 5)] == [
        "b",
        "c",
        "a",
        "b",
    ]
    weekly = {**chore, "turn_every": "week"}
    assert model.turn_member(weekly, [], at(8)) == "b"  # Sunday: same week
    assert model.turn_member(weekly, [], at(9)) == "c"
    assert model.turn_member(weekly, [], at(16)) == "a"
    # Not in turns, or only one person: nobody's turn.
    assert model.turn_member({**chore, "turns": False}, [], at(2)) is None
    assert model.turn_member({**chore, "members": ["a"]}, [], at(2)) is None


def test_a_turn_is_done_once():
    chore = {"id": "dishes", "members": ["b"], "turns": True, "repeat": "daily"}
    done = model.done_by(chore, [_did("dishes", 4, "b")], at(4, 18))
    assert done == {"b", "*"}
    assert not model.can_do("b", chore, done)
    assert model.can_do("b", chore, set())
    assert not model.can_do("a", chore, set())


def test_week_summary():
    members = [{"id": "a", "name": "Alex"}, {"id": "b", "name": "Sam"}]
    entries = [
        {**_did("bed", 3, "a"), "points": 5},
        {**_did("bed", 4, "a", review="rejected"), "points": 5},
        {"kind": "reward", "member": "a", "points": -10, "at": at(4).isoformat()},
        {**_did("bed", 1, "b"), "points": 5},  # more than a week ago
    ]
    assert model.week_summary(members, entries, {"a": 20, "b": 5}, at(8, 18)) == [
        "Alex: 1 chore, +5, spent 10, 20 now",
        "Sam: 0 chores, +0, 5 now",
    ]


# ---- allowance, money, meals and notes --------------------------------------------------


def test_allowance_due_once_a_week():
    from datetime import date

    # Sunday 8:00 is the moment; 2026-11-08 is a Sunday.
    assert model.week_key(date(2026, 11, 8)) == "2026-W45"
    assert model.allowance_due(datetime(2026, 11, 8, 7, 59), 6, 8, None) is None
    assert model.allowance_due(datetime(2026, 11, 8, 8, 0), 6, 8, None) == "2026-W45"
    # Given already this week.
    assert model.allowance_due(datetime(2026, 11, 8, 9, 0), 6, 8, "2026-W45") is None
    # Monday's allowance: due from Monday morning, all week.
    assert (
        model.allowance_due(datetime(2026, 11, 6, 20, 0), 0, 6, "2026-W44")
        == "2026-W45"
    )


def test_point_value():
    assert model.clean_point_value("") is None
    assert model.clean_point_value("0.25") == 0.25
    for bad in ("0", "-1", "lots", 500):
        with pytest.raises(ValueError):
            model.clean_point_value(bad)


def test_meals_and_notes():
    from datetime import date

    assert model.clean_meals({"dinner": "  Tacos  ", "lunch": "", "snack": "x"}) == {
        "dinner": "Tacos"
    }
    with pytest.raises(ValueError):
        model.clean_meals({"dinner": "x" * 81})
    assert model.clean_note(" Dentist   at 4 ") == "Dentist at 4"
    for bad in ("", "x" * 201):
        with pytest.raises(ValueError):
            model.clean_note(bad)
    today = date(2026, 11, 7)
    assert model.note_current({"until": None}, today)
    assert model.note_current({"until": "2026-11-07"}, today)
    assert not model.note_current({"until": "2026-11-06"}, today)
    assert model.week_days(today, 3) == ["2026-11-07", "2026-11-08", "2026-11-09"]
    assert model.clean_day("2026-11-09T10:00") == "2026-11-09"
    with pytest.raises(ValueError):
        model.clean_day("someday")


def test_split_points_as_evenly_as_points_allow() -> None:
    assert model.split_points(10, [("a", 20), ("b", 20)]) == {"a": 5, "b": 5}
    assert model.split_points(11, [("a", 20), ("b", 20)]) == {"a": 6, "b": 5}
    assert model.split_points(25, [("a", 8), ("b", 30)]) == {"a": 8, "b": 17}
    assert model.split_points(9, [("a", 1), ("b", 4), ("c", 9)]) == {
        "a": 1,
        "b": 4,
        "c": 4,
    }
    assert model.split_points(30, [("a", 8), ("b", 20)]) is None
    assert model.split_points(0, [("a", 0), ("b", 0)]) == {"a": 0, "b": 0}


def test_names_text() -> None:
    assert model.names_text(["Alex"]) == "Alex"
    assert model.names_text(["Alex", "Sam"]) == "Alex and Sam"
    assert model.names_text(["Alex", "Sam", "Riley"]) == "Alex, Sam and Riley"


def test_event_days_within_the_next_few_days() -> None:
    today = date(2030, 1, 1)
    assert model.event_days(today, today, today, 7) == ["2030-01-01"]
    # Started yesterday, ends tomorrow.
    assert model.event_days(date(2029, 12, 31), date(2030, 1, 2), today, 7) == [
        "2030-01-01",
        "2030-01-02",
    ]
    # Past the window: cut at the last day.
    assert model.event_days(date(2030, 1, 6), date(2030, 1, 20), today, 7) == [
        "2030-01-06",
        "2030-01-07",
    ]
    assert model.event_days(date(2030, 1, 9), date(2030, 1, 9), today, 7) == []
