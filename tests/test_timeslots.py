from datetime import date, time

from weekly_picker.timeslots import find_next_weekday, find_same_day, overlaps, slot_start
from tests.helpers import dt as london


def test_slot_start_across_clock_change():
    before = slot_start(date(2026, 10, 19), "Mon", time(9, 30))
    after = slot_start(date(2026, 10, 26), "Mon", time(9, 30))
    assert before.hour == after.hour == 9 and before.minute == after.minute == 30
    assert before.utcoffset() != after.utcoffset()


def test_slot_start_adds_the_weekday_offset():
    assert slot_start(date(2026, 10, 12), "Wed", time(9, 30)) == london(2026, 10, 14, 9, 30)


def test_overlaps_touching_ranges_do_not_overlap():
    a = (london(2026, 10, 13, 9, 0), london(2026, 10, 13, 10, 0))
    assert overlaps(a, (london(2026, 10, 13, 9, 30), london(2026, 10, 13, 10, 30)))
    assert not overlaps(a, (london(2026, 10, 13, 10, 0), london(2026, 10, 13, 11, 0)))


def test_same_day_keeps_preferred_when_free():
    p = london(2026, 10, 13, 9, 30)
    assert find_same_day(p, 20, []) == p


def test_same_day_moves_to_nearest_free():
    p = london(2026, 10, 13, 9, 30)
    busy = [(london(2026, 10, 13, 9, 0), london(2026, 10, 13, 10, 45))]
    assert find_same_day(p, 20, busy) == london(2026, 10, 13, 8, 30)


def test_same_day_prefers_the_earlier_option_on_a_tie_and_later_when_nearer():
    p = london(2026, 10, 13, 9, 30)
    busy = [(london(2026, 10, 13, 8, 0), london(2026, 10, 13, 10, 30))]
    assert find_same_day(p, 20, busy) == london(2026, 10, 13, 10, 30)


def test_same_day_none_when_full():
    p = london(2026, 10, 13, 9, 30)
    assert find_same_day(p, 20, [(london(2026, 10, 13, 7, 0), london(2026, 10, 13, 21, 0))]) is None


def test_same_day_never_runs_past_the_latest_end():
    p = london(2026, 10, 13, 20, 50)
    got = find_same_day(p, 30, [])
    assert got is not None and got <= london(2026, 10, 13, 20, 30)


def test_next_weekday_skips_taken_days():
    after = london(2026, 10, 14, 9, 30)  # Wed
    got = find_next_weekday(after, time(9, 30), 20, [], taken_days={date(2026, 10, 15)})
    assert got == london(2026, 10, 16, 9, 30)  # Fri


def test_next_weekday_stays_inside_the_week():
    assert find_next_weekday(london(2026, 10, 16, 9, 30), time(9, 30), 20, [], set()) is None


def test_next_weekday_skips_a_fully_busy_day():
    busy = [(london(2026, 10, 15, 7, 0), london(2026, 10, 15, 21, 0))]
    got = find_next_weekday(london(2026, 10, 14, 9, 30), time(9, 30), 20, busy, set())
    assert got == london(2026, 10, 16, 9, 30)


def test_busy_events_with_extra_fields_still_work():
    class Event(tuple):
        pass

    busy = [Event((london(2026, 10, 13, 9, 0), london(2026, 10, 13, 10, 45), "Dentist", "e1"))]
    assert find_same_day(london(2026, 10, 13, 9, 30), 20, busy) == london(2026, 10, 13, 8, 30)
