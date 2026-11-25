import csv
import json
from datetime import date
from pathlib import Path

from weekly_picker.sample import load_sample

CLASS_HEADER = "id,title,mins,difficulty,intensity,style,categories,equipment,focus,series,description,url\n"
CLASS_ROWS = (
    "C-001,Alpha,20,beginner,2,strength,Strength,weights,core,False,One line.,\n"
    "C-002,Beta,15,beginner,1,yoga,Yoga,blocks,legs,False,Another line.,\n"
)
LABEL_HEADER = ["class_id", "title", "main_goal", "goal_probs", "strength", "weight_needed", "low_energy",
                "focus", "physio", "physio_feel"]


def _write_rows(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def make_folder(tmp_path: Path, classes_encoding: str = "utf-8") -> Path:
    (tmp_path / "classes.csv").write_text(CLASS_HEADER + CLASS_ROWS, encoding=classes_encoding)
    _write_rows(tmp_path / "labels.csv", [
        LABEL_HEADER,
        ["C-001", "Alpha", "strength", json.dumps({"strength": 0.9}), "2.0", "light", "0.2", "core", "", "0"],
        ["C-002", "Beta", "flexibility", json.dumps({"flexibility": 0.8}), "1.0", "none", "0.7", "legs", "", "0"],
    ])
    _write_rows(tmp_path / "settings.csv", [
        ["key", "value"],
        ["slot_goals", json.dumps({"Mon": "strength", "Tue": "flexibility", "Wed": "sculpt and tone"})],
    ])
    _write_rows(tmp_path / "cycle.csv", [["start"], ["2026-11-02"]])
    _write_rows(tmp_path / "favourites.csv", [["class_id", "title", "added", "note"],
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
