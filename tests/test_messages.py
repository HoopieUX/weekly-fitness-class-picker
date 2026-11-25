from dataclasses import replace
from datetime import date

from weekly_picker import messages
from tests.helpers import cls, dt, lab, pick

WEEK = date(2026, 10, 12)
CLASSES = {
    "s": cls(id="s", title="Strength Basics", mins=25, equipment={"weights"}),
    "h": cls(id="h", title="Hip Opening Flow", mins=20, equipment={"yoga strap"}),
    "p": cls(id="p", title="Pilates Sculpt", mins=15, equipment={"pilates ball"}),
}
LABELS = {"s": lab(class_id="s", weight_needed="light"), "h": lab(class_id="h"), "p": lab(class_id="p")}
THREE = [
    pick(week=WEEK, slot="Mon", start=dt(2026, 10, 12), class_id="s", status="proposed"),
    pick(week=WEEK, slot="Tue", start=dt(2026, 10, 13), class_id="h", status="proposed"),
    pick(week=WEEK, slot="Wed", start=dt(2026, 10, 14), class_id="p", status="proposed"),
]
LAST_WEEK = [replace(p, week=date(2026, 10, 5), start=p.start.replace(day=p.start.day - 7), status="done") for p in THREE]

EXPECTED = """Did you do all of last week's classes? Mon ✓ Tue ✓ Wed ✓
If you missed one, reply "skipped Tue". No reply means you did them all.

* Mon 10:00: Strength Basics (25 min, light weights)
* Tue 10:00: Hip Opening Flow (20 min, strap)
* Wed 10:00: Pilates Sculpt (15 min, ball)

Reply ok, or more Mon / Tue / Wed for alternatives"""


def test_sunday_message_exact():
    assert messages.sunday(LAST_WEEK, THREE, CLASSES, LABELS) == EXPECTED


def test_no_last_week_means_no_first_line():
    assert messages.sunday([], THREE, CLASSES, LABELS) == EXPECTED.split("\n\n", 1)[1]


def test_skipped_last_week_is_crossed():
    last = [replace(LAST_WEEK[0]), replace(LAST_WEEK[1], status="skipped"), replace(LAST_WEEK[2])]
    assert messages.sunday(last, THREE, CLASSES, LABELS).startswith("Did you do all of last week's classes? Mon ✓ Tue ✗ Wed ✓")


def test_moved_to_another_day_is_flagged():
    moved = replace(THREE[2], start=dt(2026, 10, 15))
    assert "* Thu 10:00: Pilates Sculpt (15 min, ball) (moved from Wed)" in messages.sunday([], [*THREE[:2], moved], CLASSES, LABELS)


def test_no_match_slot_line():
    nothing = pick(week=WEEK, slot="Tue", start=dt(2026, 10, 13), class_id="", status="no_match")
    assert "* Tue: nothing placed this week (no match, or no free time between 9:00 and 12:00), reply more Tue" in messages.sunday([], [THREE[0], nothing, THREE[2]], CLASSES, LABELS)


def test_equipment_text():
    assert messages.equipment_text(cls(equipment=set()), None) == "no equipment"
    assert messages.equipment_text(cls(equipment={"blocks", "weights"}), None) == "blocks"
    assert messages.equipment_text(cls(equipment={"weights"}), lab(weight_needed="medium")) == "medium weights"


def test_fixed_texts():
    assert messages.autoadded() == "Added this week's classes, reply undo to remove."
    assert messages.not_run() == "This week's classes weren't picked yet. Reply pick to run it now."
    assert messages.save_failed(cls(title="X", url="https://u")) == "Couldn't save X to your calendar: https://u"


def test_updated_lists_the_changed_picks():
    assert messages.updated([THREE[1]], CLASSES, LABELS) == "Updated:\n* Tue 10:00: Hip Opening Flow (20 min, strap)"


def test_moved_message_formats_times_and_flags_a_day_change():
    assert messages.moved("Tue", dt(2026, 10, 13, 11, 0), "Dentist") == \
        "Tue moved to 11am (clashes with Dentist). Reply undo to put it back."
    assert messages.moved("Tue", dt(2026, 10, 13, 14, 30), "Lunch") == \
        "Tue moved to 2:30pm (clashes with Lunch). Reply undo to put it back."
    assert messages.moved("Wed", dt(2026, 10, 15, 9, 30), "Away day") == \
        "Wed moved to 9:30am on Thu (clashes with Away day). Reply undo to put it back."
    assert messages.moved("Mon", dt(2026, 10, 12, 12, 0), "X").startswith("Mon moved to 12pm ")


def test_could_not_move_message():
    assert messages.could_not_move("Tue", "Dentist") == \
        "Tue clashes with Dentist and I couldn't find another time this week. Reply move Tue HH:MM to choose one."


def test_a_class_that_was_never_added_is_not_ticked():
    last = [replace(LAST_WEEK[0], status="proposed"), LAST_WEEK[1], replace(LAST_WEEK[2], status="scheduled")]
    assert messages.sunday(last, THREE, CLASSES, LABELS).startswith("Did you do all of last week's classes? Mon - Tue ✓ Wed ✓")
