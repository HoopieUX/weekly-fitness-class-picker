import pytest

from weekly_picker import messages
from tests.env import Env
from tests.helpers import dt


@pytest.fixture
def env():
    e = Env()
    e.run("sunday"); e.run("approve"); e.at("2026-10-12 07:00")
    return e


def test_new_busy_event_moves_the_class_to_the_nearest_free_time(env):
    env.calendar.add_busy("Dentist", "2026-10-13 08:00", "2026-10-13 10:30")
    assert env.run("clash-check") == "Tue moved to 10:30am (clashes with Dentist). Reply undo to put it back."
    tue = env.week()[1]
    assert tue.start == dt(2026, 10, 13, 10, 30) and tue.prev_start == dt(2026, 10, 13, 10, 0)
    assert env.calendar.events[tue.event_id][1] == dt(2026, 10, 13, 10, 30)


def test_nothing_clashing_means_silence(env):
    env.calendar.add_busy("Dentist", "2026-10-13 11:00", "2026-10-13 12:00")
    before = [p.start for p in env.week()]
    assert env.run("clash-check") == "" and [p.start for p in env.week()] == before


def test_past_classes_are_never_moved(env):
    env.at("2026-10-13 12:00")
    env.calendar.add_busy("Late add", "2026-10-13 09:00", "2026-10-13 10:00")
    assert env.run("clash-check") == "" and env.week()[1].start == dt(2026, 10, 13, 10, 0)


def test_a_full_morning_never_moves_the_class_to_another_day(env):
    env.calendar.add_busy("Away day", "2026-10-13 09:00", "2026-10-13 12:00")
    assert env.run("clash-check") == messages.could_not_move("Tue", "Away day")
    assert env.week()[1].start == dt(2026, 10, 13, 10, 0)


def test_a_moved_class_stays_between_9_and_12(env):
    env.calendar.add_busy("Long meeting", "2026-10-13 09:00", "2026-10-13 11:30")
    assert env.run("clash-check") == "Tue moved to 11:30am (clashes with Long meeting). Reply undo to put it back."
    assert env.week()[1].start == dt(2026, 10, 13, 11, 30)  # a 20-minute class, so it ends 11:50


def test_no_free_time_anywhere_says_so_and_leaves_the_class(env):
    for day in (13, 14, 15, 16):
        env.calendar.add_busy("Conference", f"2026-10-{day} 07:00", f"2026-10-{day} 21:00")
    assert env.run("clash-check") == messages.could_not_move("Tue", "Conference") + "\n" + \
        messages.could_not_move("Wed", "Conference")
    assert env.week()[1].start == dt(2026, 10, 13, 10, 0)


def test_two_clashes_give_two_lines(env):
    env.calendar.add_busy("A", "2026-10-12 10:00", "2026-10-12 11:00")
    env.calendar.add_busy("B", "2026-10-14 10:00", "2026-10-14 11:00")
    out = env.run("clash-check").splitlines()
    assert len(out) == 2 and out[0].startswith("Mon moved") and out[1].startswith("Wed moved")


def test_a_moved_class_does_not_land_on_another_class(env):
    env.calendar.add_busy("Big", "2026-10-13 07:00", "2026-10-13 21:00")
    env.run("clash-check")
    starts = [p.start for p in env.week()]
    assert len({(s.date(), s.hour, s.minute) for s in starts}) == 3
    assert len({s.date() for s in starts}) == 3  # one class per day


def test_running_twice_does_not_move_it_again(env):
    env.calendar.add_busy("Dentist", "2026-10-13 08:00", "2026-10-13 10:30")
    env.run("clash-check")
    assert env.run("clash-check") == ""


def test_undo_puts_a_clash_move_back(env):
    env.calendar.add_busy("Dentist", "2026-10-13 08:00", "2026-10-13 10:30")
    env.run("clash-check")
    assert env.run("undo") == "Put Tue back to 10:00."
    assert env.week()[1].start == dt(2026, 10, 13, 10, 0) and env.week()[1].prev_start is None


def test_proposed_classes_are_left_for_the_sunday_run(env):
    env.run("undo")  # back to proposed, no events
    env.calendar.add_busy("Dentist", "2026-10-13 08:00", "2026-10-13 10:30")
    assert env.run("clash-check") == "" and env.week()[1].start == dt(2026, 10, 13, 10, 0)


def test_reminder_style_events_never_trigger_a_move(env):
    env.calendar.add_busy("Message Hex about karaoke", "2026-10-13 09:00", "2026-10-13 10:00")
    env.calendar.add_busy("Remind me to book the dentist", "2026-10-13 10:00", "2026-10-13 10:30")
    assert env.run("clash-check") == "" and env.week()[1].start == dt(2026, 10, 13, 10, 0)


def test_a_real_event_still_moves_a_class_next_to_a_reminder(env):
    env.calendar.add_busy("Message Hex", "2026-10-13 10:00", "2026-10-13 11:00")
    env.calendar.add_busy("Dentist", "2026-10-13 10:15", "2026-10-13 11:00")
    assert env.run("clash-check").startswith("Tue moved to")
