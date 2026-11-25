"""Load a folder of sample CSVs into the in-memory store, so the picker runs with no Google account and no Jev key."""
import csv
from datetime import date
from pathlib import Path

from weekly_picker.catalogue import load_csv
from weekly_picker.models import Favourite
from weekly_picker.store import InMemoryStore, _row_to_label, _rows_to_settings

ENCODING = "utf-8-sig"  # a CSV saved from Excel or Sheets can start with a byte-order mark


def _rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with open(path, newline="", encoding=ENCODING) as f:
        return [r for r in csv.reader(f) if any(cell.strip() for cell in r)]


def load_sample(folder: Path) -> InMemoryStore:
    folder = Path(folder)
    settings_rows = _rows(folder / "settings.csv")
    store = InMemoryStore(load_csv(folder / "classes.csv", encoding=ENCODING),
                          _rows_to_settings(settings_rows) if settings_rows else None)
    store.save_labels([_row_to_label(r) for r in _rows(folder / "labels.csv")[1:]])
    for r in _rows(folder / "cycle.csv")[1:]:
        store.add_cycle_start(date.fromisoformat(r[0]))
    for r in _rows(folder / "favourites.csv")[1:]:
        store.save_favourite(Favourite(class_id=r[0], added=date.fromisoformat(r[2]) if len(r) > 2 and r[2] else date.min,
                                       note=r[3] if len(r) > 3 else ""))
    return store
