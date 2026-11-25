import csv
from pathlib import Path

from weekly_picker.models import AloClass

_SYNONYMS = {
    "block": "blocks",
    "band": "resistance bands",
    "bands": "resistance bands",
    "resistance band": "resistance bands",
    "ball": "pilates ball",
    "strap": "yoga strap",
    "weight": "weights",
    "kettlebell": "kettlebells",
}


def normalise_equipment(raw: str) -> frozenset[str]:
    items = set()
    for part in raw.split(";"):
        item = part.strip().lower()
        if not item or item == "none" or "(optional)" in item:
            continue
        items.add(_SYNONYMS.get(item, item))
    return frozenset(items)


_FOCUS = {
    "full body": "full body", "total body": "full body", "core": "core",
    "legs": "legs", "lower body": "legs", "hamstrings": "legs", "calves": "legs",
    "arms": "arms", "upper body": "arms", "shoulders": "arms", "chest": "arms", "back": "arms",
    "booty": "booty", "glutes": "booty", "hips": "booty",
}


def normalise_focus(raw: str) -> str | None:
    """Alo mixes cases and lists ("Legs; booty"). Use the first area, in the five names Jev also uses."""
    first = next((p.strip().lower() for p in raw.split(";") if p.strip()), "")
    return _FOCUS.get(first)


def _split(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in raw.split(";") if p.strip())


def _intensity(raw: str) -> int | None:
    raw = raw.strip()
    return int(raw) if raw.isdigit() else None


def load_csv(path: Path) -> list[AloClass]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            AloClass(
                id=row["id"],
                title=row["title"],
                mins=int(row["mins"]),
                difficulty=row["difficulty"],
                intensity=_intensity(row["intensity"]),
                style=row["style"],
                categories=_split(row["categories"]),
                equipment=normalise_equipment(row["equipment"]),
                focus=normalise_focus(row["focus"]),
                description=row["description"],
                url=row["url"],
                instructor=(row.get("instructor") or "").strip() or None,
            )
            for row in csv.DictReader(f)
        ]
