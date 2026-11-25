"""Tests for the sample pipeline: the loader, the two scripts that build the sample, and the committed sample itself."""
import csv
import json
import re
from datetime import date
from pathlib import Path

import pytest

from scripts.make_sample import assign_demo_ids, main, remap_ids, scrub_class
from scripts.pick_classes import apply_text, pick_ids
from scripts.pick_classes import main as pick_main
from tests.helpers import cls, lab
from weekly_picker.models import Settings
from weekly_picker.sample import load_sample

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
real_sample = pytest.mark.skipif(not (SAMPLE / "classes.csv").exists(), reason="sample/ has not been built yet")



# ---- loading a sample folder ----

LD_CLASS_HEADER = "id,title,mins,difficulty,intensity,style,categories,equipment,focus,series,description,url\n"
CLASS_ROWS = (
    "C-001,Alpha,20,beginner,2,strength,Strength,weights,core,False,One line.,\n"
    "C-002,Beta,15,beginner,1,yoga,Yoga,blocks,legs,False,Another line.,\n"
)
LD_LABEL_HEADER = ["class_id", "title", "main_goal", "goal_probs", "strength", "weight_needed", "low_energy",
                "focus", "physio", "physio_feel"]


def _ld_write_rows(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def make_folder(tmp_path: Path, classes_encoding: str = "utf-8") -> Path:
    (tmp_path / "classes.csv").write_text(LD_CLASS_HEADER + CLASS_ROWS, encoding=classes_encoding)
    _ld_write_rows(tmp_path / "labels.csv", [
        LD_LABEL_HEADER,
        ["C-001", "Alpha", "strength", json.dumps({"strength": 0.9}), "2.0", "light", "0.2", "core", "", "0"],
        ["C-002", "Beta", "flexibility", json.dumps({"flexibility": 0.8}), "1.0", "none", "0.7", "legs", "", "0"],
    ])
    _ld_write_rows(tmp_path / "settings.csv", [
        ["key", "value"],
        ["slot_goals", json.dumps({"Mon": "strength", "Tue": "flexibility", "Wed": "sculpt and tone"})],
    ])
    _ld_write_rows(tmp_path / "cycle.csv", [["start"], ["2026-11-02"]])
    _ld_write_rows(tmp_path / "favourites.csv", [["class_id", "title", "added", "note"],
                                              ["C-002", "Beta", "2026-11-03", "lovely"]])
    return tmp_path


def test_loads_classes_labels_settings(tmp_path):
    store = load_sample(make_folder(tmp_path))
    assert len(store.load_classes()) == 2
    assert set(store.load_labels()) == {"C-001", "C-002"}
    assert store.load_settings().slot_goals["Mon"] == "strength"


def test_loads_cycle_and_favourites(tmp_path):
    store = load_sample(make_folder(tmp_path))
    assert store.load_cycle() == [date(2026, 11, 2)]
    assert [f.class_id for f in store.load_favourites()] == ["C-002"]


def test_reads_a_file_with_a_byte_order_mark(tmp_path):
    store = load_sample(make_folder(tmp_path, classes_encoding="utf-8-sig"))
    assert len(store.load_classes()) == 2


# ---- make_sample.py: real IDs in, demo IDs out ----

MK_CAT_HEADER = ["id", "title", "mins", "difficulty", "intensity", "style", "categories", "equipment", "focus",
              "series", "description", "url", "instructor"]
MK_LABEL_HEADER = ["class_id", "title", "main_goal", "goal_probs", "strength", "weight_needed", "low_energy",
                "focus", "physio", "physio_feel"]


def test_demo_ids_are_three_digit_and_in_order():
    assert assign_demo_ids(["9", "4"]) == {"9": "C-001", "4": "C-002"}


def test_scrub_removes_link_and_instructor():
    row = dict(zip(MK_CAT_HEADER, ["REAL-A", "Real Title", "20", "beginner", "2", "strength", "Strength", "weights",
                                "core", "False", "Real words.", "https://example.com/real", "Jade Smith"]))
    out = scrub_class(row, "C-001", "Made Up", "Fresh words.")
    assert (out["url"], out["instructor"]) == ("", "")
    assert (out["id"], out["title"], out["description"]) == ("C-001", "Made Up", "Fresh words.")
    for key in ("mins", "equipment", "style", "focus"):
        assert out[key] == row[key]


def test_remap_drops_unmapped_rows():
    assert remap_ids([["9", "x"], ["7", "y"]], {"9": "C-001"}) == [["C-001", "x"]]


def _mk_write(path: Path, rows: list[list[str]]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return path


def test_main_writes_only_demo_ids(tmp_path):
    inputs, out, private = tmp_path / "in", tmp_path / "repo" / "sample", tmp_path / "private"
    inputs.mkdir(); private.mkdir()
    catalogue = _mk_write(inputs / "cat.csv", [MK_CAT_HEADER,
        ["REAL-A", "Real One", "20", "beginner", "2", "strength", "Strength", "weights", "core", "False", "Orig.", "https://x/REAL-A", "Jade"],
        ["REAL-B", "Real Two", "15", "beginner", "1", "yoga", "Yoga", "blocks", "legs", "False", "Orig.", "https://x/REAL-B", "Sam"],
        ["REAL-C", "Not chosen", "10", "beginner", "1", "yoga", "Yoga", "", "legs", "False", "Orig.", "https://x/REAL-C", "Al"]])
    labels = _mk_write(inputs / "labels.csv", [MK_LABEL_HEADER,
        ["REAL-A", "Real One", "strength", json.dumps({"strength": 0.9}), "2.0", "light", "0.2", "core", "", "0"],
        ["REAL-B", "Real Two", "flexibility", json.dumps({"flexibility": 0.8}), "1.0", "none", "0.7", "legs", "", "0"],
        ["REAL-C", "Not chosen", "flexibility", "{}", "1.0", "none", "0.7", "legs", "", "0"]])
    physio = inputs / "physio.jsonl"
    physio.write_text(json.dumps({"class_id": "REAL-A", "physio": {"hinge": 0.1}, "physio_feel": 0.5}) + "\n")
    settings = _mk_write(inputs / "settings.csv", [["key", "value"], ["min_mins", "10"]])
    cycle = _mk_write(inputs / "cycle.csv", [["start"], ["2026-11-02"]])
    favs = _mk_write(inputs / "favs.csv", [["class_id", "title", "added", "note"],
                                         ["REAL-B", "Real Two", "2026-11-03", ""], ["REAL-C", "Not chosen", "2026-11-03", ""]])
    text = _mk_write(inputs / "text.csv", [["real_id", "title", "description"],
                                         ["REAL-A", "Made Up One", "Fresh one."], ["REAL-B", "Made Up Two", "Fresh two."]])
    mapping = private / "map.csv"
    rc = main(["--catalogue", str(catalogue), "--labels", str(labels), "--physio", str(physio),
               "--settings", str(settings), "--cycle", str(cycle), "--favourites", str(favs), "--text", str(text),
               "--out", str(out), "--mapping", str(mapping)])
    assert rc == 0
    blob = "".join(p.read_text() for p in out.iterdir())
    for real in ("REAL-A", "REAL-B", "REAL-C", "Real One", "Real Two", "Jade", "https://"):
        assert real not in blob
    assert "C-001" in blob and "C-002" in blob and "Made Up One" in blob
    assert "0.5" in (out / "labels.csv").read_text()  # physio merged in
    assert "REAL-A" in mapping.read_text()


def test_refuses_a_mapping_file_inside_the_repo():
    with pytest.raises(SystemExit):
        main(["--catalogue", "a", "--labels", "a", "--physio", "a", "--settings", "a", "--cycle", "a",
              "--favourites", "a", "--text", "a", "--out", "x", "--mapping", str(Path(__file__).resolve().parent.parent / "map.csv")])


# ---- pick_classes.py: choosing the classes ----

PK_GOALS = ["strength", "flexibility", "sculpt and tone"]


def _pk_world(per_goal: int = 12):
    classes, labels = [], {}
    for g in PK_GOALS:
        for i in range(per_goal):
            cid = f"{g[:3]}{i:02d}"
            classes.append(cls(id=cid, title=f"Class {g[0]}{i}", mins=10 + i * 2, equipment={"blocks"} if i % 2 else set()))
            labels[cid] = lab(class_id=cid, main_goal=g, goal_probs={g: 0.9})
    return classes, labels


def test_picks_cover_every_goal_and_spread_lengths():
    classes, labels = _pk_world()
    ids = pick_ids(classes, labels, Settings.default(), per_goal=8)
    assert len(ids) == 24
    for g in PK_GOALS:
        chosen = [c for c in classes if c.id in ids and labels[c.id].main_goal == g]
        assert len(chosen) == 8
        assert len({c.mins for c in chosen}) >= 6


def test_picks_skip_classes_the_rules_would_exclude():
    classes, labels = _pk_world()
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
    classes, labels = _pk_world()
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
    assert pick_main(["pick", "--catalogue", str(cat), "--labels", str(lab_csv), "--out", str(out)]) == 0
    extract = (out / "extract.csv").read_text()
    assert "https://" not in extract and "Jade" not in extract
    for c in classes:
        assert c.id not in extract
    assert len(list(csv.reader(open(out / "index.csv")))) == 25


# ---- the committed sample/ folder (skipped until it has been built) ----

@pytest.fixture(scope="module")
def sample_store():
    return load_sample(SAMPLE)


@real_sample
def test_sample_size(sample_store):
    assert 20 <= len(sample_store.load_classes()) <= 30


@real_sample
def test_no_links_or_instructors(sample_store):
    assert all(c.url == "" and c.instructor is None for c in sample_store.load_classes())


@real_sample
def test_every_id_is_a_demo_id():
    for name in ("classes", "labels", "favourites"):
        with open(SAMPLE / f"{name}.csv", newline="", encoding="utf-8-sig") as f:
            ids = [r[0] for r in list(csv.reader(f))[1:] if r]
        assert all(re.fullmatch(r"C-\d{3}", i) for i in ids), name


@real_sample
def test_every_class_has_a_label(sample_store):
    assert set(sample_store.load_labels()) == {c.id for c in sample_store.load_classes()}


@real_sample
def test_every_slot_goal_has_a_candidate(sample_store):
    labels = sample_store.load_labels()
    for goal in sample_store.load_settings().slot_goals.values():
        assert any(l.main_goal == goal for l in labels.values()), goal
