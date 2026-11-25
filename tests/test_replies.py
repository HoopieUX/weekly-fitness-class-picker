from datetime import date, time

import pytest

from tests.env import Env
from tests.helpers import cls, dt
from tests.world import WEEK


@pytest.fixture
def env():
    return Env()


def goal_of(env, p):
    return env.world.labels[p.class_id].main_goal


def test_undo_after_autoadd(env):
    env.run("sunday"); env.at("2026-10-12 08:00"); env.run("autoadd")
    assert env.calendar.live == 3
    assert env.run("undo") == "Removed this week's classes from your calendar."
    assert env.calendar.live == 0 and {p.status for p in env.week()} == {"proposed"}
    assert all(p.event_id == "" for p in env.week())


def test_undo_with_nothing_to_undo(env):
    env.run("sunday")
    assert env.run("undo") == "Nothing to undo."


def test_more_and_choose(env):
    env.run("sunday")
    text = env.run("more Tue")
    assert text.startswith("1.") and text.count("\n") >= 4 and text.endswith("Reply with a number to swap Tue.")
    offered = env.store.load_offers("Tue", WEEK)
    assert len(offered) == 5 and env.week()[1].class_id not in offered
    env.run("choose Tue 2")
    assert env.week()[1].class_id == offered[1] and env.week()[1].status == "proposed"


def test_choose_on_a_scheduled_slot_swaps_the_calendar_event(env):
    env.run("sunday"); env.run("approve"); env.run("more Tue")
    old_event = env.week()[1].event_id
    env.run("choose Tue 1")
    tue = env.week()[1]
    assert tue.status == "scheduled" and tue.event_id not in ("", old_event)
    assert env.calendar.live == 3 and env.calendar.created == 4


def test_choose_rejects_a_number_that_was_not_offered(env):
    env.run("sunday"); env.run("more Tue")
    assert env.run("choose Tue 9") == "Pick a number from 1 to 5."
    assert env.run("choose Mon 1") == "I haven't offered any alternatives for Mon. Reply more Mon first."


def test_goal_before_sunday_is_one_off(env):
    assert env.run("goal all strength") == "Okay, all slots will be strength next week."
    env.run("sunday")
    assert all(goal_of(env, p) == "strength" for p in env.week())
    assert env.store.load_settings().next_week == {}


def test_goal_after_sunday_repicks_only_that_slot(env):
    env.run("sunday")
    before = env.week()
    env.run("goal Tue strength")
    after = env.week()
    assert goal_of(env, after[1]) == "strength"
    assert (after[0].class_id, after[2].class_id) == (before[0].class_id, before[2].class_id)
    assert env.store.load_settings().next_week == {}


def test_goal_rejects_unknown_goal_and_slot(env):
    assert env.run("goal Tue zumba").startswith("I don't know that goal")
    assert env.run("goal Sat strength").startswith("I only know Mon, Tue and Wed")


def test_next_week_low_energy_before_and_after_picking(env):
    env.run("next-week low energy"); env.run("sunday")
    assert all(env.world.labels[p.class_id].low_energy >= 0.5 for p in env.week())
    other = Env(); other.run("sunday"); other.run("next-week low energy")
    assert all(other.world.labels[p.class_id].low_energy >= 0.5 for p in other.week())


def test_feedback_adjusts_strength_and_dislike_blocks(env):
    env.finish_a_week()
    env.run("feedback Mon too_hard"); env.run("feedback Tue dislike")
    assert env.store.load_settings().preferred_strength == 1.75
    disliked = env.last[1].class_id
    assert next(p for p in env.week(WEEK) if p.slot == "Tue").feedback == "dislike"
    env.run("sunday")
    assert disliked not in {p.class_id for p in env.week()}


def test_feedback_strength_is_clamped_to_the_score_range(env):
    env.finish_a_week()
    for _ in range(8):
        env.run("feedback Mon too_easy")
    assert env.store.load_settings().preferred_strength == 3.0
    for _ in range(20):
        env.run("feedback Mon too_hard")
    assert env.store.load_settings().preferred_strength == 0.0


def test_feedback_rejects_unknown_kind(env):
    env.finish_a_week()
    assert env.run("feedback Mon meh").startswith("Feedback can be")


def test_move_this_week_vs_permanent(env):
    env.run("sunday"); env.run("approve")
    env.run("move Tue 14:00")
    tue = env.week()[1]
    assert tue.start == dt(2026, 10, 13, 14, 0) and tue.prev_start == dt(2026, 10, 13, 10, 0)
    assert env.calendar.events[tue.event_id][1] == dt(2026, 10, 13, 14, 0)
    assert env.store.load_settings().slots["Tue"] == time(10, 0)
    env.run("move Tue 11:00 --permanent")
    assert env.store.load_settings().slots["Tue"] == time(11, 0) and env.week()[1].start.hour == 11


def test_move_to_another_day(env):
    env.run("sunday")
    env.run("move Tue 10:00 --day Thu")
    assert env.week()[1].start == dt(2026, 10, 15, 10, 0)


def test_move_rejects_a_bad_time(env):
    env.run("sunday")
    assert env.run("move Tue 25:99") == "I couldn't read that time. Use 24-hour HH:MM, like 14:00."


def test_undo_after_a_move_only_puts_that_class_back(env):
    env.run("sunday"); env.run("approve"); env.run("move Tue 14:00")
    assert env.run("undo") == "Put Tue back to 10:00."
    assert env.week()[1].start == dt(2026, 10, 13, 10, 0) and env.week()[1].prev_start is None
    assert env.calendar.live == 3 and [p.status for p in env.week()] == ["scheduled"] * 3


def test_repeat_bypasses_the_four_week_window(env):
    env.finish_a_week()
    last_mon = env.last[0].class_id
    env.run("repeat Mon --on Wed")
    wed = env.week()[2]
    assert wed.class_id == last_mon and wed.requested


def test_repeat_by_title_goes_to_the_first_free_slot(env):
    env.run("sunday"); env.run("approve")
    assert env.run("repeat flexibility-nothing").startswith("I couldn't find a class")
    env.run("skip Wed")
    env.run("repeat str-core-Ann")
    assert env.week()[2].class_id == "str-core-Ann" and env.week()[2].status == "scheduled"


def test_repeat_with_an_ambiguous_title_asks_which(env):
    env.run("sunday")
    text = env.run("repeat str-core")
    assert text.startswith("Which one?") and "str-core-Ann" in text


def test_low_energy_today_keeps_the_goal(env):
    env.run("sunday"); env.run("approve"); env.at("2026-10-12 08:30")
    old = env.week()[0]
    env.run("low-energy-today")
    mon = env.week()[0]
    assert mon.class_id != old.class_id and goal_of(env, mon) == "strength"
    assert env.world.labels[mon.class_id].low_energy >= 0.5
    assert mon.start == old.start and env.calendar.live == 3 and env.calendar.created == 4


def test_low_energy_today_with_no_class_today(env):
    env.run("sunday"); env.at("2026-10-15 08:00")  # Thursday: there are only Mon, Tue and Wed classes
    assert env.run("low-energy-today") == "You have no class today."


def test_skip_deletes_the_event(env):
    env.run("sunday"); env.run("approve")
    assert env.run("skip Tue") == "Skipped Tue."
    assert [p.status for p in env.week()] == ["scheduled", "skipped", "scheduled"] and env.calendar.live == 2


def test_skipped_marks_last_weeks_class(env):
    env.finish_a_week()
    env.run("skipped Tue")
    assert next(p for p in env.week(WEEK) if p.slot == "Tue").status == "skipped"


def test_unknown_slot_is_rejected(env):
    env.run("sunday")
    assert env.run("skip Sat").startswith("I only know Mon, Tue and Wed")


def test_period_started_repicks_the_slots_inside_the_window(env):
    env.run("sunday"); env.run("approve"); env.at("2026-10-12 08:00")
    env.run("period-started")
    assert env.store.load_cycle() == [date(2026, 10, 12)]
    assert all(env.world.labels[p.class_id].low_energy >= 0.5 for p in env.week())
    assert env.calendar.live == 3


def test_period_started_with_a_date_and_no_slots_affected(env):
    env.run("sunday")
    assert env.run("period-started 2026-10-01") == "Got it. I'll keep picks gentle for 3 days from 2026-10-01."


def test_set_goal_is_permanent(env):
    assert env.run("set-goal Mon flexibility") == "Mon is now a flexibility day."
    assert env.store.load_settings().slot_goals["Mon"] == "flexibility"


def test_request_style_pulls_in_an_on_request_class():
    inversions = [cls(id=f"inv-{i}", title=f"Headstand {i}", style="skills_inversions", focus="arms", instructor="Dee")
                  for i in range(3)]
    env = Env(extra=inversions)
    env.run("sunday")
    assert not any(p.class_id.startswith("inv") for p in env.week())  # never picked automatically
    env.run("request-style skills_inversions --on Mon")
    assert env.week()[0].class_id.startswith("inv-")
    assert env.run("request-style cartwheels").startswith("I don't know that style")


def test_skipped_midweek_marks_the_most_recent_class_not_last_weeks(env):
    env.finish_a_week()                      # weeks of 12 and 19 Oct both exist
    env.at("2026-10-21 10:00")               # Wednesday of the second week
    assert env.run("skipped Tue") == "Marked Tue as skipped."
    assert next(p for p in env.week(WEEK) if p.slot == "Tue").status == "scheduled"
    assert env.week()[1].status == "skipped"  # Tuesday 20 Oct


def test_repeat_a_slot_midweek_copies_this_weeks_class(env):
    env.finish_a_week()
    env.at("2026-10-21 10:00")
    this_mon = env.week()[0].class_id
    env.run("repeat Mon --on Wed")
    assert env.week()[2].class_id == this_mon


@pytest.mark.parametrize("command", ["more tue", "more TUE", "more Tuesday", "more tuesday"])
def test_day_names_can_be_typed_any_way(env, command):
    env.run("sunday")
    assert env.run(command).startswith("1.")


def test_lowercase_days_work_everywhere(env):
    env.run("sunday"); env.run("approve")
    assert env.run("skip wed") == "Skipped Wed."
    assert env.run("skipped tuesday") == "I don't have a Tue class that has happened yet."
    assert env.run("move tue 14:00 --day thursday").startswith("Moved Tue.")
    assert env.week()[1].start.strftime("%a %H:%M") == "Thu 14:00"
    assert env.run("goal ALL strength").startswith("Updated:")
    env.run("feedback mon LIKE")
    assert env.run("repeat monday --on wed") == "I don't have a Mon class that has happened yet."  # "monday" meant Mon
    assert env.run("add-day fri 10:00 strength").startswith("Updated:\n* Fri 10:00")


def test_unknown_words_still_get_the_clear_error(env):
    env.run("sunday")
    assert env.run("skip saturday").startswith("I only know Mon, Tue and Wed")
