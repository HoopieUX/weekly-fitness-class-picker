"""Build the scrubbed sample/ folder from private exports.

Reads the real catalogue, labels, physio answers and settings from paths given on the command line (none of them are
committed), swaps real class IDs for demo IDs (C-001, C-002...), drops links and instructor names, and writes the
real-to-demo mapping to a file outside the repo.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LABEL_TITLE, LABEL_PHYSIO, LABEL_FEEL = 1, 8, 9
FAV_TITLE = 1


def assign_demo_ids(real_ids: list[str]) -> dict[str, str]:
    return {real: f"C-{n:03d}" for n, real in enumerate(real_ids, start=1)}


def scrub_class(row: dict, demo_id: str, title: str, description: str) -> dict:
    return {**row, "id": demo_id, "title": title, "description": description, "url": "", "instructor": ""}


def remap_ids(rows: list[list[str]], mapping: dict[str, str]) -> list[list[str]]:
    return [[mapping[r[0]], *r[1:]] for r in rows if r and r[0] in mapping]


def _read(path: str) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.reader(f) if any(c.strip() for c in r)]


def _write(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def _inside(path: Path, folder: Path) -> bool:
    return folder.resolve() in path.resolve().parents


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("catalogue", "labels", "physio", "settings", "cycle", "favourites", "text", "out", "mapping"):
        ap.add_argument(f"--{flag}", required=True)
    args = ap.parse_args(argv)
    if _inside(Path(args.mapping), REPO):
        ap.error("--mapping must be outside the repo: it links demo IDs back to real classes")

    text_rows = _read(args.text)[1:]
    text = {r[0]: (r[1], r[2]) for r in text_rows}
    mapping = assign_demo_ids([r[0] for r in text_rows])
    titles = {demo: text[real][0] for real, demo in mapping.items()}

    with open(args.catalogue, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        catalogue = {row["id"]: row for row in reader}
    missing = [real for real in mapping if real not in catalogue]
    if missing:
        ap.error(f"{len(missing)} chosen classes are not in the catalogue, first: {missing[0]}")
    for col in ("url", "instructor"):
        if col not in header:
            header.append(col)
    classes = [scrub_class(catalogue[real], demo, *text[real]) for real, demo in mapping.items()]

    physio = {}
    with open(args.physio, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                physio[d["class_id"]] = d

    labels_rows = _read(args.labels)
    labels = remap_ids(labels_rows[1:], {**mapping})
    real_of = {demo: real for real, demo in mapping.items()}
    for r in labels:
        r += [""] * (LABEL_FEEL + 1 - len(r))
        r[LABEL_TITLE] = titles[r[0]]
        answer = physio.get(real_of[r[0]])
        if answer:
            r[LABEL_PHYSIO], r[LABEL_FEEL] = json.dumps(answer["physio"]), str(answer["physio_feel"])
    labels.sort(key=lambda r: r[0])

    favourites = remap_ids(_read(args.favourites)[1:], mapping)
    for r in favourites:
        r[FAV_TITLE] = titles[r[0]]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "classes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(classes)
    _write(out / "labels.csv", [labels_rows[0], *labels])
    _write(out / "settings.csv", _read(args.settings))
    _write(out / "cycle.csv", _read(args.cycle))
    _write(out / "favourites.csv", [_read(args.favourites)[0], *favourites])

    Path(args.mapping).parent.mkdir(parents=True, exist_ok=True)
    _write(Path(args.mapping), [["real_id", "demo_id"], *mapping.items()])
    print(f"Wrote {len(classes)} classes to {out}. Mapping saved to {args.mapping} (keep it private).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
