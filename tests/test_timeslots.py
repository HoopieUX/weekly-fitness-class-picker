from datetime import date, time, timedelta

from weekly_picker.timeslots import find_same_day, overlaps, place_on_day, slot_start
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
    assert find_same_day(p, 20, busy) == london(2026, 10, 13, 10, 45)


def test_same_day_prefers_the_earlier_option_on_a_tie_and_later_when_nearer():
    p = london(2026, 10, 13, 9, 30)
    busy = [(london(2026, 10, 13, 8, 0), london(2026, 10, 13, 10, 30))]
    assert find_same_day(p, 20, busy) == london(2026, 10, 13, 10, 30)


def test_same_day_none_when_full():
    p = london(2026, 10, 13, 9, 30)
    assert find_same_day(p, 20, [(london(2026, 10, 13, 7, 0), london(2026, 10, 13, 21, 0))]) is None


def test_same_day_never_runs_past_the_latest_end():
    p = london(2026, 10, 13, 11, 50)
    got = find_same_day(p, 30, [])
    assert got is not None and got + timedelta(minutes=30) <= london(2026, 10, 13, 12, 0)


def test_busy_events_with_extra_fields_still_work():
    class Event(tuple):
        pass

    busy = [Event((london(2026, 10, 13, 9, 0), london(2026, 10, 13, 10, 45), "Dentist", "e1"))]
    assert find_same_day(london(2026, 10, 13, 9, 30), 20, busy) == london(2026, 10, 13, 10, 45)


def test_a_class_is_never_placed_before_9_or_after_12():
    for minutes in (10, 20, 30):
        got = find_same_day(london(2026, 10, 13, 10, 0), minutes, [])
        assert got is not None and london(2026, 10, 13, 9, 0) <= got
        assert got + timedelta(minutes=minutes) <= london(2026, 10, 13, 12, 0)


def test_a_preferred_time_outside_the_window_falls_back_to_10():
    assert find_same_day(london(2026, 10, 13, 7, 30), 20, []) == london(2026, 10, 13, 10, 0)
    assert find_same_day(london(2026, 10, 13, 18, 0), 20, []) == london(2026, 10, 13, 10, 0)


def test_when_10_is_busy_it_takes_the_nearest_free_quarter_hour_in_the_window():
    busy = [(london(2026, 10, 13, 10, 0), london(2026, 10, 13, 11, 0))]
    assert find_same_day(london(2026, 10, 13, 10, 0), 20, busy) == london(2026, 10, 13, 9, 30)


def test_a_busy_window_places_nothing():
    busy = [(london(2026, 10, 13, 9, 0), london(2026, 10, 13, 12, 0))]
    assert find_same_day(london(2026, 10, 13, 10, 0), 10, busy) is None


def test_a_30_minute_class_cannot_start_after_11_30():
    busy = [(london(2026, 10, 13, 9, 0), london(2026, 10, 13, 11, 15))]
    assert find_same_day(london(2026, 10, 13, 10, 0), 30, busy) == london(2026, 10, 13, 11, 15)
    busy = [(london(2026, 10, 13, 9, 0), london(2026, 10, 13, 11, 45))]
    assert find_same_day(london(2026, 10, 13, 10, 0), 30, busy) is None


def test_place_on_day_prefers_10_and_stays_between_9_and_12():
    day = date(2026, 10, 13)
    assert place_on_day(day, 20, []) == london(2026, 10, 13, 10, 0)
    # starts are on quarter-hours, so a 20-minute class starts 11:30 at the latest (11:45 would end at 12:05)
    assert place_on_day(day, 20, [(london(2026, 10, 13, 9, 0), london(2026, 10, 13, 11, 30))]) == london(2026, 10, 13, 11, 30)
    assert place_on_day(day, 20, [(london(2026, 10, 13, 9, 0), london(2026, 10, 13, 11, 31))]) is None
    assert place_on_day(day, 200, []) is None  # longer than the whole window
