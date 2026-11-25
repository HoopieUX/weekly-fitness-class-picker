from dataclasses import replace
from datetime import date

import pytest

from weekly_picker import messages
from weekly_picker.store import InMemoryStore
from tests.env import Env
from tests.world import WEEK
from tests.fakes import FakeClient


@pytest.fixture
def env():
    return Env()


def test_sunday_proposes_three_picks_and_prints_the_message(env):
    text = env.run("sunday")
    assert [p.status for p in env.week()] == ["proposed"] * 3 and env.calendar.created == 0
    assert text.splitlines()[0].startswith("* Mon 9:30: ") and text.endswith("Reply ok, or more Mon / Tue / Wed for alternatives")


def test_approve_creates_the_events_with_a_reason(env):
    env.run("sunday"); env.run("approve")
    assert env.calendar.created == 3 and [p.status for p in env.week()] == ["scheduled"] * 3
    assert all(p.event_id for p in env.week())
    reasons = [r for _, _, r in env.calendar.events.values()]
    assert reasons[0].startswith("strength, ")


def test_approve_twice_creates_events_once(env):
    env.run("sunday"); env.run("approve")
    assert env.run("approve") == "Already added this week's classes."
    assert env.calendar.created == 3


def test_ok_after_autoadd_is_harmless(env):
    env.run("sunday"); env.at("2026-10-12 08:00")
    assert env.run("autoadd") == messages.autoadded()
    env.run("approve")
    assert env.calendar.created == 3


def test_autoadd_silent_when_already_approved(env):
    env.run("sunday"); env.run("approve"); env.at("2026-10-12 08:00")
    assert env.run("autoadd") == "" and env.calendar.created == 3


def test_check_ran(env):
    assert env.run("check-ran") == messages.not_run()
    env.run("sunday")
    assert env.run("check-ran") == ""


def test_jev_down_falls_back_to_plain_rules(env):
    env.client.fail = True
    text = env.run("sunday")
    assert text.endswith("Picked without Jev this week.")
    assert [p.status for p in env.week()] == ["proposed"] * 3 and not any(p.jev_used for p in env.week())


def test_running_sunday_twice_replaces_proposed_but_keeps_scheduled(env):
    env.run("sunday"); env.run("approve")
    scheduled = {p.slot: p.class_id for p in env.week()}
    env.run("pick")
    assert {p.slot: p.class_id for p in env.week()} == scheduled
    assert env.calendar.created == 3 and [p.status for p in env.week()] == ["scheduled"] * 3


def test_sunday_clears_the_one_off_changes_it_used(env):
    env.store.save_settings(replace(env.store.load_settings(), next_week={"all": "low energy"}))
    env.run("sunday")
    assert env.store.load_settings().next_week == {}
    assert all(env.world.labels[p.class_id].low_energy >= 0.5 for p in env.week())


def test_approve_reports_calendar_failures_and_keeps_the_pick_proposed(env):
    env.run("sunday"); env.calendar.fail_create = True
    text = env.run("approve")
    assert text.count("Couldn't save") == 3 and [p.status for p in env.week()] == ["proposed"] * 3


def test_label_command_labels_the_unlabelled_and_respects_limit():
    env = Env()
    env.store = InMemoryStore(env.world.classes)  # no labels yet
    out = env.run("label", "--limit", "2", label_client=FakeClient())
    assert out == "Labelled 2 classes (2 of 36 now labelled)." and len(env.store.load_labels()) == 2


def test_a_second_sunday_run_changes_nothing_and_does_not_lose_one_off_requests():
    env = Env()
    env.at("2026-10-10 18:00")  # Saturday
    env.run("next-week low energy")
    first = env.run("sunday")
    assert env.run("sunday") == first  # cron fired twice: the same message, the same picks
    assert all(env.world.labels[p.class_id].low_energy >= 0.5 for p in env.week())


def test_pick_forces_a_fresh_plan():
    env = Env()
    env.run("sunday")
    env.store.save_settings(replace(env.store.load_settings(), next_week={"all": "low energy"}))
    env.run("sunday")  # no-op
    assert not all(env.world.labels[p.class_id].low_energy >= 0.5 for p in env.week())
    env.run("pick")
    assert all(env.world.labels[p.class_id].low_energy >= 0.5 for p in env.week())


def test_pick_on_a_monday_morning_plans_this_week_not_the_next():
    env = Env()
    env.at("2026-10-12 09:00")
    env.run("pick")
    assert [p.slot for p in env.week()] == ["Mon", "Tue", "Wed"]


def test_pick_midweek_only_plans_the_slots_still_ahead():
    env = Env()
    env.at("2026-10-13 10:00")  # Tuesday, after Tuesday's 9:30
    env.run("pick")
    assert [p.slot for p in env.week()] == ["Wed"]


def test_pick_after_the_last_slot_plans_next_week():
    env = Env()
    env.at("2026-10-14 10:00")  # Wednesday, after Wednesday's 9:30
    env.run("pick")
    assert [p.slot for p in env.week()] == []
    assert [p.slot for p in env.week(WEEK + __import__("datetime").timedelta(days=7))] == ["Mon", "Tue", "Wed"]


def test_commands_queue_behind_a_lock(tmp_path, monkeypatch):
    import fcntl
    import threading

    from weekly_picker import commands

    monkeypatch.setattr(commands, "LOCK_PATH", tmp_path / "lock")
    env = Env()
    done = threading.Event()
    with open(tmp_path / "lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        worker = threading.Thread(target=lambda: (env.run("check-ran"), done.set()))
        worker.start()
        assert not done.wait(0.5)  # blocked while someone else holds the lock
        fcntl.flock(held, fcntl.LOCK_UN)
    assert done.wait(5)
    worker.join()


def test_approve_reuses_an_event_already_on_the_calendar(env_fixture=None):
    env = Env()
    env.run("sunday")
    mon = env.week()[0]
    stray = env.calendar.create(env.world.classes_by_id[mon.class_id], mon.start, "left over from a failed save")
    env.run("approve")
    assert env.calendar.created == 3  # the stray one plus two new, not four
    assert env.week()[0].event_id == stray and env.week()[0].status == "scheduled"


@pytest.mark.parametrize("command, expected", [
    ("period-started 3rd", "I couldn't read that date. Use YYYY-MM-DD, like 2026-10-03."),
    ("choose Tue two", "I couldn't understand that command"),
    ("dance", "I couldn't understand that command"),
])
def test_bad_input_gets_a_one_line_answer_instead_of_silence(command, expected):
    env = Env()
    env.run("sunday")
    assert env.run(command).startswith(expected)


def test_a_permanent_change_of_day_is_not_supported_and_changes_nothing():
    env = Env()
    env.run("sunday")
    out = env.run("move Tue 11:00 --day Thu --permanent")
    assert out.startswith("Changing the day for good isn't supported yet")
    assert set(env.store.load_settings().slots) == {"Mon", "Tue", "Wed"}


def test_show_repeats_the_weeks_message_without_changing_anything():
    env = Env()
    sent = env.run("sunday")
    before = [p for p in env.store.load_picks()]
    assert env.run("show") == sent and env.store.load_picks() == before and env.calendar.created == 0


def test_show_with_nothing_picked_says_so():
    assert Env().run("show") == "No classes picked yet. Reply pick to make some."


def test_import_physio_adds_answers_and_keeps_everything_else(env, tmp_path):
    labels = env.store.load_labels()
    first, second = sorted(labels)[:2]
    before = labels[first]
    f = tmp_path / "physio.jsonl"
    f.write_text('{"class_id": "%s", "physio": {"side_bend": 0.9}, "physio_feel": 0.6}\n'
                 '{"class_id": "not-a-class", "physio": {"hinge": 0.9}, "physio_feel": 0.1}\n' % first)
    text = env.run(f"import-physio {f}")
    after = env.store.load_labels()
    assert after[first].physio == {"side_bend": 0.9} and after[first].physio_feel == 0.6
    assert replace(after[first], physio={}, physio_feel=0.0) == before
    assert after[second].physio == {} and "not-a-class" not in after
    assert text.startswith("Added physio answers to 1 classes.")


def test_import_physio_says_when_the_file_is_missing(env, tmp_path):
    assert env.run(f"import-physio {tmp_path / 'nope.jsonl'}").startswith("I couldn't find")


def test_next_week_no_physio_runs_end_to_end(env):
    assert env.run("next-week no physio") == "Okay, no physio next week."
    assert env.store.load_settings().next_week == {"all": "no physio"}
    env.run("sunday")
    assert [p.status for p in env.week()] == ["proposed"] * 3


def test_fav_by_title_then_favs_lists_it_and_unfav_removes_it(env):
    first = env.store.load_classes()[0]
    assert env.run(f"fav {first.title}") == f"Added {first.title} to your favourites. I'll lean towards it when I pick."
    assert [f.class_id for f in env.store.load_favourites()] == [first.id]
    assert env.run(f"fav {first.title}") == f"{first.title} is already in your favourites."
    assert env.run("favs").splitlines()[0] == "Your favourites (1):" and first.title.strip() in env.run("favs")
    assert env.run(f"unfav {first.title}") == f"Removed {first.title} from your favourites."
    assert env.run("favs").startswith("No favourites yet")


def test_fav_with_a_note_and_by_id(env):
    first = env.store.load_classes()[0]
    env.run(f"fav {first.id} --note 'great for my back'")
    assert env.store.load_favourites()[0].note == "great for my back"
    assert "great for my back" in env.run("favs")


def test_fav_a_day_means_the_last_class_that_happened_that_day(env):
    env.finish_a_week()
    tue = [p for p in env.week(WEEK) if p.slot == "Tue"][0]
    assert env.run("fav tue").startswith("Added ") and env.store.load_favourites()[0].class_id == tue.class_id
    assert env.run("unfav tue").startswith("Removed ")


def test_fav_says_so_when_it_cannot_find_the_class(env):
    assert env.run("fav zzz no such class") == "I couldn't find a class called zzz no such class."
    assert env.run("fav Mon") == "I don't have a Mon class that has happened yet."
    assert env.run("unfav zzz") == "None of your favourites matches zzz."


def test_fav_takes_full_day_names_and_an_unquoted_note(env):
    env.finish_a_week()
    tue = [p for p in env.week(WEEK) if p.slot == "Tue"][0]
    assert env.run("fav Tuesday --note great for my lower back").startswith("Added ")
    fav = env.store.load_favourites()[0]
    assert fav.class_id == tue.class_id and fav.note == "great for my lower back"
    assert env.run("fav tues --note even better").startswith("Updated the note on ")
    assert env.store.load_favourites()[0].note == "even better"
    assert env.run("unfav Tuesday").startswith("Removed ")


def test_a_favourite_that_left_alo_is_listed_and_can_be_removed_by_id(env):
    from weekly_picker.models import Favourite
    first = env.store.load_classes()[0]
    env.store.save_favourite(Favourite(class_id="gone123", added=date(2026, 10, 1)))
    env.store.save_favourite(Favourite(class_id=first.id, added=date(2026, 10, 2)))
    text = env.run("favs")
    assert text.splitlines()[0] == "Your favourites (2):" and "class gone123 (no longer on Alo" in text
    assert env.run("unfav gone123").startswith("Removed class gone123")
    assert [f.class_id for f in env.store.load_favourites()] == [first.id]


def test_a_longer_class_put_into_a_booked_slot_does_not_run_into_the_next_event():
    from datetime import timedelta
    from tests.helpers import cls
    env = Env(extra=[cls(id="long", title="Long Favourite Flow", mins=60)])
    env.run("sunday")
    env.calendar.add_busy("Physio", "2026-10-13 10:00", "2026-10-13 11:00")
    env.run("repeat Long Favourite Flow --on Tue")
    tue = env.week()[1]
    assert tue.class_id == "long"
    end = tue.start + timedelta(minutes=60)
    assert end.hour * 60 + end.minute <= 10 * 60 or tue.start.hour >= 11


def test_autoadd_at_11pm_on_sunday_adds_the_week_that_is_about_to_start(env):
    env.run("sunday"); env.at("2026-10-11 23:00")
    assert env.run("autoadd") == messages.autoadded()
    assert env.calendar.created == 3 and {p.status for p in env.week()} == {"scheduled"}


def test_a_reply_before_11pm_means_autoadd_stays_quiet(env):
    env.run("sunday"); env.at("2026-10-11 22:00"); env.run("approve"); env.at("2026-10-11 23:00")
    assert env.run("autoadd") == "" and env.calendar.created == 3


def test_a_change_at_10_55pm_is_still_added_at_11pm(env):
    env.run("sunday"); env.at("2026-10-11 22:55"); env.run("low-energy-today")
    env.at("2026-10-11 23:00")
    assert env.run("autoadd") == messages.autoadded()
    assert env.calendar.created == 3


def test_autoadd_with_nothing_picked_is_silent_so_check_ran_is_the_alarm(env):
    env.at("2026-10-11 23:00")
    assert env.run("autoadd") == "" and env.calendar.created == 0
    assert env.run("check-ran") != ""


def test_autoadd_at_11pm_covers_a_fourth_day(env):
    env.run("set-slot Thu 09:30 strength"); env.run("sunday"); env.at("2026-10-11 23:00")
    env.run("autoadd")
    assert env.calendar.created == 4
