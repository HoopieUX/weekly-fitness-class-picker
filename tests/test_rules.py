from datetime import date
from pathlib import Path

import pytest

from weekly_picker.models import Settings
from weekly_picker.rules import reasons_excluded
from tests.helpers import cls, dt, lab, pick

_UNSET = object()


def reasons(c, labels=_UNSET, history=(), today=date(2026, 10, 18), **kw):
    labels = lab(class_id=c.id) if labels is _UNSET else labels
    return reasons_excluded(c, labels, Settings.default(), list(history), today, **kw)


def test_length_bounds_inclusive():
    assert "length" not in reasons(cls(mins=10)) and "length" not in reasons(cls(mins=30))
    assert "length" in reasons(cls(mins=9)) and "length" in reasons(cls(mins=31))


def test_unowned_equipment_excluded():
    assert "equipment" in reasons(cls(equipment={"sliders"}))
    assert "equipment" not in reasons(cls(equipment={"weights", "blocks", "wall"}))


def test_style_rules():
    assert "style" in reasons(cls(style="skills_inversions"))
    assert "style" not in reasons(cls(style="skills_inversions"), requested_styles=frozenset({"skills_inversions"}))
    assert "style" in reasons(cls(style="skills_how to teach"), requested_styles=frozenset({"skills_how to teach"}))
    assert "style" not in reasons(cls(style="skills_flexibility"))
    assert "style" not in reasons(cls(style="fitness_pilates"))


def test_cardio_threshold():
    assert "cardio" in reasons(cls(), lab(goal_probs={"cardio": 0.4, "strength": 0.6}))
    assert "cardio" not in reasons(cls(), lab(goal_probs={"cardio": 0.39, "strength": 0.61}))
    assert "cardio" not in reasons(cls(), lab(goal_probs={"cardio": 0.9}), allow_cardio=True)


def test_heavy_weights_excluded():
    assert "heavy_weights" in reasons(cls(), lab(weight_needed="heavy"))


def test_repeat_window_and_requests():
    done = pick(class_id="c1", start=dt(2026, 9, 21), status="done")
    assert "recent_repeat" in reasons(cls(id="c1"), history=[done], today=date(2026, 10, 18))
    assert "recent_repeat" not in reasons(cls(id="c1"), history=[done], today=date(2026, 10, 20))
    assert "recent_repeat" not in reasons(
        cls(id="c1"), history=[done], today=date(2026, 10, 18), requested_ids=frozenset({"c1"})
    )


def test_skipped_pick_does_not_count_as_repeat():
    skipped = pick(class_id="c1", start=dt(2026, 10, 12), status="skipped")
    assert "recent_repeat" not in reasons(cls(id="c1"), history=[skipped])


def test_disliked_never_returns_even_if_ignore_repeats():
    bad = pick(class_id="c1", feedback="dislike", start=dt(2025, 1, 6))
    assert "disliked" in reasons(cls(id="c1"), history=[bad], ignore_repeats=True)


def test_unlabelled_excluded():
    assert "unlabelled" in reasons(cls(), None)


def test_clean_class_has_no_reasons():
    assert reasons(cls()) == []


def test_a_proposed_pick_never_added_does_not_block_a_class():
    never_added = pick(class_id="c1", start=dt(2026, 10, 12), status="proposed")
    assert "recent_repeat" not in reasons(cls(id="c1"), history=[never_added], today=date(2026, 10, 18))


@pytest.mark.parametrize("title", [
    "10-Minute Waterfall Workout for Two", "Partner Plank Work", "Perfect Duo: Strength & HIIT",
    "10-Minute Buddy Up with Tabata", "Partner Up: Drill Work",
])
def test_partner_classes_are_skipped_by_title(title):
    assert "partner" in reasons(cls(title=title))


@pytest.mark.parametrize("description", [
    "It's nonstop in this 10-minute partner workout! Grab a friend and get ready.",
    "Grab a partner and meet us on the mat for this 10-minute class.",
    "Hitting your workout at the gym or at home with a buddy? Start or finish your session with this.",
    "Twice the burn, but twice the fun. This workout for two involves combo moves like Beast to Side Plank.",
    "Travel for two! Tone, sculpt, and take in the sights of Big Sur.",
])
def test_partner_classes_are_skipped_by_description(description):
    assert "partner" in reasons(cls(title="10-Minute Team Workout", description=description))


@pytest.mark.parametrize("title, description", [
    ("Space Through Strength", "Grab a couple of blankets, and strap, and a partner if you'd like. See you on the mat!"),
    ("Let's Talk", "Communicating pleasure and boundaries with your partner to bridge the gap to pleasure."),
    ("Duality Flow", "A calm flow."),
    ("Partnership Mindset", "A talk about working with others."),
    ("HardCORE", "Prepare for two rounds of four ab-blasting moves with a medium dumbbell."),
    ("Cold Plunge: 2.5 Minutes", "Stay in for two and a half minutes. Hold each breath for two counts."),
])
def test_solo_classes_that_merely_mention_a_partner_are_kept(title, description):
    assert "partner" not in reasons(cls(title=title, description=description))


@pytest.mark.skipif(not (Path(__file__).resolve().parent.parent / "alo-scoring").exists(), reason="the real catalogue is private")
def test_the_partner_rule_flags_a_sensible_number_of_real_classes():
    from pathlib import Path

    from weekly_picker.catalogue import load_csv

    root = Path(__file__).resolve().parent.parent
    flagged = [c for c in load_csv(root / "alo-scoring" / "alo_classes.csv") if "partner" in reasons(c, None)]
    assert 25 <= len(flagged) <= 70, len(flagged)
