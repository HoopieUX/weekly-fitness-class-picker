import csv
import json
from pathlib import Path

from scripts.pick_classes import apply_text, main, pick_ids
from weekly_picker.models import Settings
from tests.helpers import cls, lab

GOALS = ["strength", "flexibility", "sculpt and tone"]


def _world(per_goal: int = 12):
    classes, labels = [], {}
    for g in GOALS:
        for i in range(per_goal):
            cid = f"{g[:3]}{i:02d}"
            classes.append(cls(id=cid, title=f"Class {g[0]}{i}", mins=10 + i * 2, equipment={"blocks"} if i % 2 else set()))
            labels[cid] = lab(class_id=cid, main_goal=g, goal_probs={g: 0.9})
    return classes, labels


def test_picks_cover_every_goal_and_spread_lengths():
    classes, labels = _world()
    ids = pick_ids(classes, labels, Settings.default(), per_goal=8)
    assert len(ids) == 24
    for g in GOALS:
        chosen = [c for c in classes if c.id in ids and labels[c.id].main_goal == g]
        assert len(chosen) == 8
        assert len({c.mins for c in chosen}) >= 6


def test_picks_skip_classes_the_rules_would_exclude():
    classes, labels = _world()
    classes[0] = cls(id=classes[0].id, title="Partner Plank", mins=20)
    classes[1] = cls(id=classes[1].id, title="Too short", mins=5)
    ids = pick_ids(classes, labels, Settings.default(), per_goal=12)
    assert classes[0].id not in ids and classes[1].id not in ids


def test_apply_text_joins_numbers_back_to_real_ids():
    index = [["n", "real_id"], ["1", "REAL-A"], ["2", "REAL-B"]]
    text = [["n", "title", "description"], ["2", "Two", "Second."], ["1", "One", "First."]]
    assert apply_text(index, text) == [["real_id", "title", "description"], ["REAL-A", "One", "First."],
                                       ["REAL-B", "Two", "Second."]]


def test_main_extract_has_no_real_ids(tmp_path):
    classes, labels = _world()
    cat = tmp_path / "cat.csv"
    with open(cat, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "mins", "difficulty", "intensity", "style", "categories", "equipment", "focus",
                    "series", "description", "url", "instructor"])
        for c in classes:
            w.writerow([c.id, c.title, c.mins, "beginner", 2, "pilates", "Pilates", "; ".join(c.equipment), "core",
                        "False", "Orig.", "https://x/" + c.id, "Jade"])
    lab_csv = tmp_path / "labels.csv"
    with open(lab_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class_id", "title", "main_goal", "goal_probs", "strength", "weight_needed", "low_energy",
                    "focus", "physio", "physio_feel"])
        for cid, l in labels.items():
            w.writerow([cid, cid, l.main_goal, json.dumps(l.goal_probs), l.strength, l.weight_needed, l.low_energy, "", "", 0])
    out = tmp_path / "private"
    assert main(["pick", "--catalogue", str(cat), "--labels", str(lab_csv), "--out", str(out)]) == 0
    extract = (out / "extract.csv").read_text()
    assert "https://" not in extract and "Jade" not in extract
    for c in classes:
        assert c.id not in extract
    assert len(list(csv.reader(open(out / "index.csv")))) == 25
