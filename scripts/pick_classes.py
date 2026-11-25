"""Choose the classes for the sample, and join the made-up text back to their real IDs.

Two steps, both run on your own machine, with private files that are never committed:

  pick   chooses classes (all three slot goals, a spread of lengths and equipment) and writes
         `extract.csv` (numbered, no IDs, no links, no instructors) and `index.csv` (number -> real ID).
         Only extract.csv is meant to be shared, so someone can write titles and descriptions for it.
  apply  joins text written against those numbers (n,title,description) back to real IDs, producing the
         `sample_text.csv` that make_sample.py reads.
"""
import argparse
import csv
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from weekly_picker.catalogue import load_csv  # noqa: E402
from weekly_picker.models import Settings  # noqa: E402
from weekly_picker.rules import reasons_excluded  # noqa: E402
from weekly_picker.store import _row_to_label, _rows_to_settings  # noqa: E402


def pick_ids(classes, labels, settings: Settings, per_goal: int = 8) -> list[str]:
    chosen: list[str] = []
    for goal in dict.fromkeys(settings.slot_goals.values()):
        pool = sorted(
            (c for c in classes if c.id in labels and labels[c.id].main_goal == goal
             and not reasons_excluded(c, labels[c.id], settings, [], date.today())),
            key=lambda c: (c.mins, sorted(c.equipment), c.id))
        if len(pool) <= per_goal:
            chosen += [c.id for c in pool]
        else:
            chosen += [pool[round(i * (len(pool) - 1) / (per_goal - 1))].id for i in range(per_goal)]
    return chosen


def apply_text(index: list[list[str]], text: list[list[str]]) -> list[list[str]]:
    real = {r[0]: r[1] for r in index[1:]}
    rows = {r[0]: r for r in text[1:] if r}
    missing = [n for n in real if n not in rows]
    if missing:
        raise SystemExit(f"No text for numbers: {', '.join(missing)}")
    return [["real_id", "title", "description"], *[[real[n], rows[n][1], rows[n][2]] for n in real]]


def _read(path: str) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.reader(f) if any(c.strip() for c in r)]


def _write(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick")
    for flag in ("catalogue", "labels", "out"):
        p.add_argument(f"--{flag}", required=True)
    p.add_argument("--settings")
    p.add_argument("--per-goal", type=int, default=8)
    a = sub.add_parser("apply")
    for flag in ("index", "text", "out"):
        a.add_argument(f"--{flag}", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "apply":
        _write(Path(args.out), apply_text(_read(args.index), _read(args.text)))
        return 0

    out = Path(args.out)
    if REPO in out.resolve().parents or out.resolve() == REPO:
        ap.error("--out must be outside the repo: it links numbers back to real classes")
    classes = load_csv(Path(args.catalogue), encoding="utf-8-sig")
    labels = {r[0]: _row_to_label(r) for r in _read(args.labels)[1:]}
    settings = _rows_to_settings(_read(args.settings)) if args.settings else Settings.default()
    ids = pick_ids(classes, labels, settings, args.per_goal)
    by_id = {c.id: c for c in classes}
    extract = [["n", "main_goal", "mins", "difficulty", "style", "focus", "equipment", "title", "description"]]
    index = [["n", "real_id"]]
    for n, cid in enumerate(ids, start=1):
        c = by_id[cid]
        extract.append([str(n), labels[cid].main_goal, str(c.mins), c.difficulty, c.style, c.focus or "",
                        "; ".join(sorted(c.equipment)), c.title, c.description])
        index.append([str(n), cid])
    _write(out / "extract.csv", extract)
    _write(out / "index.csv", index)
    print(f"Picked {len(ids)} classes. Share only {out / 'extract.csv'}; keep index.csv private.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
