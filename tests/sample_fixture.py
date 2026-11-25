"""Builds a small, made-up sample folder in the same shape as sample/, so demo tests don't depend on real data."""
import csv
import json
from pathlib import Path

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
                           "2.0" if goal == "strength" else "0.5", "none", "0.9", focus, "", "0"])
    _write(folder / "classes.csv", [CLASS_HEADER, *classes])
    _write(folder / "labels.csv", [LABEL_HEADER, *labels])
    _write(folder / "settings.csv", [["key", "value"]])
    _write(folder / "cycle.csv", [["start"], *[[d] for d in cycle_starts]])
    _write(folder / "favourites.csv", [["class_id", "title", "added", "note"]])
    return folder
