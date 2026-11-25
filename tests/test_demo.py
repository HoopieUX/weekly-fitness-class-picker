import csv
import json
import socket
from datetime import date
from pathlib import Path


from scripts.demo import run_demo

# A small, made-up sample in the same shape as sample/, so these tests never depend on real data.
CLASS_HEADER = ["id", "title", "mins", "difficulty", "intensity", "style", "categories", "equipment", "focus",
                "series", "description", "url", "instructor"]
LABEL_HEADER = ["class_id", "title", "main_goal", "goal_probs", "strength", "weight_needed", "low_energy",
                "focus", "physio", "physio_feel"]
GOALS = ["strength", "flexibility", "sculpt and tone"]
FOCUSES = ["core", "legs", "arms"]


def _write(path: Path, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def build_sample(folder: Path, cycle_starts: list[str] = ()) -> Path:
    classes, labels = [], []
    n = 0
    for goal in GOALS:
        for focus in FOCUSES:
            n += 1
            cid = f"C-{n:03d}"
            classes.append([cid, f"{goal.title()} {focus} {n}", "20", "beginner", "2", "pilates", "Pilates",
                            "blocks", focus, "False", "A made-up class.", "", ""])
            labels.append([cid, f"{goal.title()} {focus} {n}", goal, json.dumps({goal: 0.9, "other": 0.1}),
                           "2.0" if goal == "strength" else "0.5", "none", "0.1" if n == 1 else "0.9", focus, "", "0"])
    _write(folder / "classes.csv", [CLASS_HEADER, *classes])
    _write(folder / "labels.csv", [LABEL_HEADER, *labels])
    _write(folder / "settings.csv", [["key", "value"]])
    _write(folder / "cycle.csv", [["start"], *[[d] for d in cycle_starts]])
    _write(folder / "favourites.csv", [["class_id", "title", "added", "note"]])
    return folder


WEEK = date(2026, 11, 30)  # a Monday
TODAY = date(2026, 11, 29)


def test_demo_picks_one_class_per_slot(tmp_path):
    out = run_demo(build_sample(tmp_path), WEEK, TODAY)
    for slot in ("Mon", "Tue", "Wed"):
        assert slot in out
    assert "no_match" not in out


def test_demo_needs_no_network(tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the demo tried to use the network")

    monkeypatch.setattr(socket, "socket", refuse)
    assert "Mon" in run_demo(build_sample(tmp_path), WEEK, TODAY)


def test_demo_on_a_low_energy_week(tmp_path):
    out = run_demo(build_sample(tmp_path, cycle_starts=[WEEK.isoformat()]), WEEK, TODAY)
    assert "no_match" not in out
    assert out.count("min") >= 3


def test_demo_says_it_ranks_from_saved_labels(tmp_path):
    assert "Ranked from Jev's saved labels" in run_demo(build_sample(tmp_path), WEEK, TODAY)


def test_low_energy_week_avoids_a_class_that_is_not_gentle(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    normal = run_demo(build_sample(tmp_path / "a"), WEEK, TODAY)
    gentle = run_demo(build_sample(tmp_path / "b", cycle_starts=[WEEK.isoformat()]), WEEK, TODAY)
    assert "Strength core 1" in normal
    assert "Strength core 1" not in gentle
