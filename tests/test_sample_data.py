"""Checks on the committed sample/ folder. Skipped until the sample has been built with scripts/make_sample.py."""
import csv
import re
from pathlib import Path

import pytest

from weekly_picker.sample import load_sample

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
pytestmark = pytest.mark.skipif(not (SAMPLE / "classes.csv").exists(), reason="sample/ has not been built yet")


@pytest.fixture(scope="module")
def store():
    return load_sample(SAMPLE)


def test_sample_size(store):
    assert 20 <= len(store.load_classes()) <= 30


def test_no_links_or_instructors(store):
    assert all(c.url == "" and c.instructor is None for c in store.load_classes())


def test_every_id_is_a_demo_id():
    for name in ("classes", "labels", "favourites"):
        with open(SAMPLE / f"{name}.csv", newline="", encoding="utf-8-sig") as f:
            ids = [r[0] for r in list(csv.reader(f))[1:] if r]
        assert all(re.fullmatch(r"C-\d{3}", i) for i in ids), name


def test_every_class_has_a_label(store):
    assert set(store.load_labels()) == {c.id for c in store.load_classes()}


def test_every_slot_goal_has_a_candidate(store):
    labels = store.load_labels()
    for goal in store.load_settings().slot_goals.values():
        assert any(l.main_goal == goal for l in labels.values()), goal
