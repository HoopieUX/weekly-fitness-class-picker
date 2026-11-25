import csv
import json
from pathlib import Path

import pytest

from scripts.make_sample import assign_demo_ids, main, remap_ids, scrub_class

CAT_HEADER = ["id", "title", "mins", "difficulty", "intensity", "style", "categories", "equipment", "focus",
              "series", "description", "url", "instructor"]
LABEL_HEADER = ["class_id", "title", "main_goal", "goal_probs", "strength", "weight_needed", "low_energy",
                "focus", "physio", "physio_feel"]


def test_demo_ids_are_three_digit_and_in_order():
    assert assign_demo_ids(["9", "4"]) == {"9": "C-001", "4": "C-002"}


def test_scrub_removes_link_and_instructor():
    row = dict(zip(CAT_HEADER, ["90417", "Real Title", "20", "beginner", "2", "strength", "Strength", "weights",
                                "core", "False", "Real words.", "https://example.com/real", "Jade Smith"]))
    out = scrub_class(row, "C-001", "Made Up", "Fresh words.")
    assert (out["url"], out["instructor"]) == ("", "")
    assert (out["id"], out["title"], out["description"]) == ("C-001", "Made Up", "Fresh words.")
    for key in ("mins", "equipment", "style", "focus"):
        assert out[key] == row[key]


def test_remap_drops_unmapped_rows():
    assert remap_ids([["9", "x"], ["7", "y"]], {"9": "C-001"}) == [["C-001", "x"]]


def _write(path: Path, rows: list[list[str]]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return path


def test_main_writes_only_demo_ids(tmp_path):
    inputs, out, private = tmp_path / "in", tmp_path / "repo" / "sample", tmp_path / "private"
    inputs.mkdir(); private.mkdir()
    catalogue = _write(inputs / "cat.csv", [CAT_HEADER,
        ["90417", "Real One", "20", "beginner", "2", "strength", "Strength", "weights", "core", "False", "Orig.", "https://x/90417", "Jade"],
        ["90418", "Real Two", "15", "beginner", "1", "yoga", "Yoga", "blocks", "legs", "False", "Orig.", "https://x/90418", "Sam"],
        ["90419", "Not chosen", "10", "beginner", "1", "yoga", "Yoga", "", "legs", "False", "Orig.", "https://x/90419", "Al"]])
    labels = _write(inputs / "labels.csv", [LABEL_HEADER,
        ["90417", "Real One", "strength", json.dumps({"strength": 0.9}), "2.0", "light", "0.2", "core", "", "0"],
        ["90418", "Real Two", "flexibility", json.dumps({"flexibility": 0.8}), "1.0", "none", "0.7", "legs", "", "0"],
        ["90419", "Not chosen", "flexibility", "{}", "1.0", "none", "0.7", "legs", "", "0"]])
    physio = inputs / "physio.jsonl"
    physio.write_text(json.dumps({"class_id": "90417", "physio": {"hinge": 0.1}, "physio_feel": 0.5}) + "\n")
    settings = _write(inputs / "settings.csv", [["key", "value"], ["min_mins", "10"]])
    cycle = _write(inputs / "cycle.csv", [["start"], ["2026-11-02"]])
    favs = _write(inputs / "favs.csv", [["class_id", "title", "added", "note"],
                                         ["90418", "Real Two", "2026-11-03", ""], ["90419", "Not chosen", "2026-11-03", ""]])
    text = _write(inputs / "text.csv", [["real_id", "title", "description"],
                                         ["90417", "Made Up One", "Fresh one."], ["90418", "Made Up Two", "Fresh two."]])
    mapping = private / "map.csv"
    rc = main(["--catalogue", str(catalogue), "--labels", str(labels), "--physio", str(physio),
               "--settings", str(settings), "--cycle", str(cycle), "--favourites", str(favs), "--text", str(text),
               "--out", str(out), "--mapping", str(mapping)])
    assert rc == 0
    blob = "".join(p.read_text() for p in out.iterdir())
    for real in ("90417", "90418", "90419", "Real One", "Real Two", "Jade", "https://"):
        assert real not in blob
    assert "C-001" in blob and "C-002" in blob and "Made Up One" in blob
    assert "0.5" in (out / "labels.csv").read_text()  # physio merged in
    assert "90417" in mapping.read_text()


def test_refuses_a_mapping_file_inside_the_repo():
    with pytest.raises(SystemExit):
        main(["--catalogue", "a", "--labels", "a", "--physio", "a", "--settings", "a", "--cycle", "a",
              "--favourites", "a", "--text", "a", "--out", "x", "--mapping", str(Path(__file__).resolve().parent.parent / "map.csv")])
