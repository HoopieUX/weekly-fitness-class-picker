from dataclasses import replace
from datetime import time

import pytest

from weekly_picker.models import Settings
from tests.env import Env
from tests.world import WEEK


@pytest.fixture
def env():
    return Env()


def slots(env):
    return env.store.load_settings().slots


def test_add_day_picks_a_class_for_that_day_and_puts_it_on_the_calendar(env):
    env.run("sunday"); env.run("approve")
    out = env.run("add-day Thu 10:00 strength")
    assert out.startswith("Updated:\n* Thu 10:00: ")
    thu = next(p for p in env.store.load_picks() if p.slot == "Thu")
    assert thu.start.strftime("%a %H:%M") == "Thu 10:00" and thu.status == "scheduled" and env.calendar.created == 4
    assert env.world.labels[thu.class_id].main_goal == "strength"
    settings = env.store.load_settings()
    assert settings.slots["Thu"] == time(10, 0) and settings.slot_goals["Thu"] == "strength"
    assert settings.extra_days == {"Thu": "2026-10-16"}  # a temporary slot: it ends on the Friday of that week


def test_add_day_before_the_sunday_run_is_included_in_it(env):
    env.at("2026-10-10 18:00")  # Saturday
    assert env.run("add-day Thu 10:00 flexibility") == \
        "Okay, Thu 10:00 (flexibility) is added for next week. It will be in Sunday's picks."
    env.run("sunday")
    assert sorted(p.slot for p in env.store.load_picks() if p.week == WEEK) == ["Mon", "Thu", "Tue", "Wed"]


def test_add_day_refuses_a_day_that_already_has_a_class(env):
    env.run("sunday")
    assert env.run("add-day Tue 10:00 strength") == \
        "Tue already has a class. Use move Tue HH:MM or goal Tue <goal> instead."
    assert "Thu" not in slots(env)


@pytest.mark.parametrize("command, expected", [
    ("add-day Sat 10:00 strength", "I only know the weekdays Mon, Tue, Wed, Thu and Fri."),
    ("add-day Thu 25:00 strength", "I couldn't read that time. Use 24-hour HH:MM, like 14:00."),
    ("add-day Thu 10:00 zumba", "I don't know that goal."),
])
def test_add_day_rejects_bad_input(env, command, expected):
    assert env.run(command).startswith(expected)
    assert "Thu" not in slots(env)


def test_replies_work_on_an_extra_day(env):
    env.run("sunday"); env.run("approve"); env.run("add-day Thu 10:00 strength")
    assert env.run("more Thu").startswith("1.")
    env.run("choose Thu 1")
    assert env.run("skip Thu") == "Skipped Thu."
    assert env.calendar.live == 3


def test_an_extra_day_disappears_after_its_week(env):
    env.run("sunday"); env.run("add-day Thu 10:00 strength")
    env.at("2026-10-18 18:00")  # the next Sunday run
    out = env.run("sunday")
    assert "Thu" not in slots(env) and "Thu" not in env.store.load_settings().extra_days
    assert not any(line.startswith("* Thu") for line in out.splitlines())  # last week may list it; this week must not
    assert sorted(p.slot for p in env.week(WEEK.replace(day=19))) == ["Mon", "Tue", "Wed"]


def test_set_slot_adds_a_permanent_fourth_day(env):
    env.at("2026-10-10 18:00")
    assert env.run("set-slot Fri 08:00 strength").startswith("Fri 8:00 (strength) is now a weekly slot.")
    settings = env.store.load_settings()
    assert settings.slots["Fri"] == time(8, 0) and settings.extra_days == {}
    env.run("sunday")
    assert sorted(p.slot for p in env.week()) == ["Fri", "Mon", "Tue", "Wed"]
    env.at("2026-10-18 18:00"); env.run("sunday")  # still there the week after
    assert "Fri" in slots(env) and len(env.week(WEEK.replace(day=19))) == 4


def test_set_slot_turns_a_temporary_day_permanent(env):
    env.run("sunday"); env.run("add-day Thu 10:00 strength")
    env.run("set-slot Thu 10:00 strength")
    assert env.store.load_settings().extra_days == {}
    env.at("2026-10-18 18:00"); env.run("sunday")
    assert "Thu" in slots(env)


def test_set_slot_changes_an_existing_slot_time_and_goal(env):
    env.run("sunday")
    env.run("set-slot Tue 11:30 mobility")
    settings = env.store.load_settings()
    assert settings.slots["Tue"] == time(11, 30) and settings.slot_goals["Tue"] == "mobility"


def test_remove_slot(env):
    assert env.run("remove-slot Wed").startswith("Removed Wed from your weekly slots.")
    assert set(slots(env)) == {"Mon", "Tue"} and "Wed" not in env.store.load_settings().slot_goals


def test_remove_slot_keeps_at_least_one_and_knows_its_slots(env):
    assert env.run("remove-slot Thu") == "I don't have a Thu slot."
    env.run("remove-slot Wed"); env.run("remove-slot Tue")
    assert env.run("remove-slot Mon") == "You need at least one slot, so I can't remove Mon."
    assert set(slots(env)) == {"Mon"}


def test_settings_remember_extra_days():
    from weekly_picker.store import MemoryGrid, SheetsStore
    s = replace(Settings.default(), extra_days={"Thu": "2026-10-16"})
    assert SheetsStore.initialise(MemoryGrid(), [], s).load_settings() == s


def test_add_day_on_a_wednesday_afternoon_means_tomorrow_even_with_nothing_picked_yet(env):
    env.at("2026-10-14 15:00")  # Wednesday, after the 10:00 class
    out = env.run("add-day Thu 10:00 strength")
    assert out.startswith("Updated:\n* Thu 10:00: ")
    [thu] = env.week(WEEK)
    assert thu.slot == "Thu" and thu.status == "proposed"
    assert thu.start.strftime("%Y-%m-%d %H:%M") == "2026-10-15 10:00"
    assert env.store.load_settings().extra_days == {"Thu": "2026-10-16"}


def test_two_extra_days_this_week_with_a_multi_word_goal_then_ok_adds_both(env):
    env.at("2026-10-14 15:00")
    env.run("add-day Thu 10:00 strength")
    env.run("add-day Fri 10:00 sculpt and tone")
    picks = env.week(WEEK)
    assert [p.slot for p in picks] == ["Thu", "Fri"]
    assert env.world.labels[picks[1].class_id].main_goal == "sculpt and tone"
    assert env.world.classes_by_id[picks[0].class_id].instructor != env.world.classes_by_id[picks[1].class_id].instructor
    env.run("approve")
    assert env.calendar.created == 2 and [p.status for p in env.week(WEEK)] == ["scheduled", "scheduled"]


def test_multi_word_goals_work_for_goal_set_goal_and_set_slot(env):
    env.run("sunday")
    env.run("goal Tue sculpt and tone")
    assert env.world.labels[env.week()[1].class_id].main_goal == "sculpt and tone"
    assert env.run("set-goal Mon sculpt and tone") == "Mon is now a sculpt and tone day."
    assert env.run("set-slot Fri 10:00 sculpt and tone").startswith("Fri 10:00 (sculpt and tone) is now a weekly slot.")


def test_sunday_planning_ignores_reminder_style_events():
    env = Env()
    env.calendar.add_busy("Message Hex about karaoke", "2026-10-12 09:00", "2026-10-12 10:00")
    env.run("sunday")
    assert env.week()[0].start.strftime("%H:%M") == "10:00"


def test_ignore_events_adds_and_removes_words():
    env = Env()
    assert env.run("ignore-events text") == "Okay. Events starting with message, remind, text won't block your classes."
    env.calendar.add_busy("Text Sam back", "2026-10-12 09:00", "2026-10-12 10:00")
    env.run("sunday")
    assert env.week()[0].start.strftime("%H:%M") == "10:00"
    assert env.run("unignore-events text") == "Okay. Events starting with message, remind won't block your classes."
    assert env.run("unignore-events zebra") == "'zebra' wasn't on the list. Events starting with message, remind don't block your classes."


def test_ignore_list_is_remembered_and_defaults_to_message_and_remind():
    assert Settings.default().ignore_titles == ["message", "remind"]
    s = replace(Settings.default(), ignore_titles=["message", "text"])
    from tests.test_store import MemoryGrid, SheetsStore
    assert SheetsStore.initialise(MemoryGrid(), [], s).load_settings() == s
