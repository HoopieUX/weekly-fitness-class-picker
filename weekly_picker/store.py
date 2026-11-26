"""The only module that touches storage. Swap Google Sheets for Supabase by rewriting `SheetsStore`/`GoogleGrid`."""
import json
import os
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
from typing import Protocol

from weekly_picker.config import TZ
from weekly_picker.models import AloClass, Favourite, Labels, Pick, Settings

ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = Path("~/.weekly_picker/google_token.json").expanduser()
CHUNK = 500
RETRIES = 5  # transient Google errors (429 quota, 5xx) are retried before giving up


class Store(Protocol):
    def load_classes(self) -> list[AloClass]: ...
    def load_labels(self) -> dict[str, Labels]: ...
    def save_labels(self, labels: list[Labels]) -> None: ...
    def load_settings(self) -> Settings: ...
    def save_settings(self, s: Settings) -> None: ...
    def load_picks(self) -> list[Pick]: ...
    def save_picks(self, picks: list[Pick]) -> None: ...
    def load_cycle(self) -> list[date]: ...
    def add_cycle_start(self, d: date) -> None: ...
    def load_favourites(self) -> list[Favourite]: ...
    def save_favourite(self, fav: Favourite) -> None: ...
    def remove_favourite(self, class_id: str) -> bool: ...
    def load_offers(self, slot: str, week: date) -> list[str]: ...
    def save_offers(self, slot: str, week: date, class_ids: list[str]) -> None: ...


class InMemoryStore:
    def __init__(self, classes: list[AloClass], settings: Settings | None = None):
        self._classes = list(classes)
        self._settings = settings or Settings.default()
        self._labels: dict[str, Labels] = {}
        self._picks: dict[tuple[date, str], Pick] = {}
        self._cycle: list[date] = []
        self._favourites: dict[str, Favourite] = {}
        self._offers: dict[tuple[str, date], list[str]] = {}

    def load_classes(self):
        return list(self._classes)

    def load_labels(self):
        return dict(self._labels)

    def save_labels(self, labels):
        for l in labels:
            self._labels[l.class_id] = l

    def load_settings(self):
        return self._settings

    def save_settings(self, s):
        self._settings = s

    def load_picks(self):
        return list(self._picks.values())

    def save_picks(self, picks):
        for p in picks:
            self._picks[(p.week, p.slot)] = p

    def load_cycle(self):
        return list(self._cycle)

    def add_cycle_start(self, d):
        self._cycle.append(d)

    def load_favourites(self):
        return list(self._favourites.values())

    def save_favourite(self, fav):
        self._favourites[fav.class_id] = fav

    def remove_favourite(self, class_id):
        return self._favourites.pop(class_id, None) is not None

    def load_offers(self, slot, week):
        return list(self._offers.get((slot, week), []))

    def save_offers(self, slot, week, class_ids):
        self._offers[(slot, week)] = list(class_ids)


# ---- row encoding (everything is written as text so Sheets never reinterprets it) ----

CLASS_COLS = ["id", "title", "mins", "difficulty", "intensity", "style", "categories", "equipment",
              "focus", "description", "url", "instructor"]
LABEL_COLS = ["class_id", "title", "main_goal", "goal_probs", "strength", "weight_needed", "low_energy", "focus", "physio", "physio_feel"]
PICK_COLS = ["week", "slot", "start", "class_id", "status", "feedback", "event_id",
             "requested", "prev_start", "prev_event_id"]
OFFER_COLS = ["week", "slot", "class_ids"]
FAV_COLS = ["class_id", "title", "added", "note"]
TABS = ["classes", "labels", "picks", "settings", "cycle", "offers", "favourites"]


def _bool(v: str) -> bool:
    return v.strip().upper() == "TRUE"


def _class_to_row(c: AloClass) -> list[str]:
    return [c.id, c.title, str(c.mins), c.difficulty, "" if c.intensity is None else str(c.intensity), c.style,
            "; ".join(c.categories), "; ".join(sorted(c.equipment)), c.focus or "", c.description, c.url,
            c.instructor or ""]


def _row_to_class(r: list[str]) -> AloClass:
    return AloClass(
        id=r[0], title=r[1], mins=int(r[2]), difficulty=r[3], intensity=int(r[4]) if r[4] else None, style=r[5],
        categories=tuple(p.strip() for p in r[6].split(";") if p.strip()),
        equipment=frozenset(p.strip() for p in r[7].split(";") if p.strip()),
        focus=r[8] or None, description=r[9], url=r[10], instructor=r[11] or None,
    )


def _label_to_row(l: Labels, title: str) -> list[str]:
    return [l.class_id, title, l.main_goal, json.dumps(l.goal_probs), str(l.strength), l.weight_needed,
            str(l.low_energy), l.focus or "", json.dumps(l.physio) if l.physio else "",
            str(l.physio_feel)]


def _physio_cell(text: str) -> dict[str, float]:
    """Physio answers as JSON (what the picker writes) or as whole percentages in area order, like "26 13 23 33 34"
    (a compact form that is quick to type or paste into the Sheet)."""
    from weekly_picker.jev import PHYSIO_AREAS

    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        return json.loads(text)
    return {area: int(n) / 100 for area, n in zip(PHYSIO_AREAS, text.split())}


def _row_to_label(r: list[str]) -> Labels:
    return Labels(class_id=r[0], main_goal=r[2], goal_probs=json.loads(r[3]), strength=float(r[4]),
                  weight_needed=r[5], low_energy=float(r[6]), focus=r[7] or None,
                  physio=_physio_cell(r[8]) if len(r) > 8 else {},
                  physio_feel=float(r[9]) if len(r) > 9 and r[9] else 0.0)


def _pick_to_row(p: Pick) -> list[str]:
    return [p.week.isoformat(), p.slot, p.start.isoformat(), p.class_id, p.status, p.feedback, p.event_id,
            str(p.requested).upper(), p.prev_start.isoformat() if p.prev_start else "", p.prev_event_id]


def _row_to_pick(r: list[str]) -> Pick:
    return Pick(
        week=date.fromisoformat(r[0]), slot=r[1], start=datetime.fromisoformat(r[2]).astimezone(TZ),
        class_id=r[3], status=r[4], feedback=r[5], event_id=r[6], requested=_bool(r[7]),
        prev_start=datetime.fromisoformat(r[8]).astimezone(TZ) if r[8] else None, prev_event_id=r[9],
    )


def _settings_to_rows(s: Settings) -> list[list[str]]:
    values = {
        "slots": {k: v.strftime("%H:%M") for k, v in s.slots.items()},
        "slot_goals": s.slot_goals,
        "min_mins": s.min_mins,
        "max_mins": s.max_mins,
        "equipment_owned": sorted(s.equipment_owned),
        "styles_in": sorted(s.styles_in),
        "styles_on_request": sorted(s.styles_on_request),
        "styles_out": sorted(s.styles_out),
        "low_energy_days": s.low_energy_days,
        "preferred_strength": s.preferred_strength,
        "next_week": s.next_week,
        "extra_days": s.extra_days,
        "ignore_titles": s.ignore_titles,
        "preview_sent": s.preview_sent,
        "preview_replied": s.preview_replied,
    }
    return [["key", "value"]] + [[k, json.dumps(v)] for k, v in values.items()]


def _rows_to_settings(rows: list[list[str]]) -> Settings:
    stored = {r[0]: json.loads(r[1]) for r in rows[1:] if len(r) >= 2 and r[0]}
    s = Settings.default()
    if "slots" in stored:
        s = replace(s, slots={k: time.fromisoformat(v) for k, v in stored["slots"].items()})
    for key in ("slot_goals", "next_week", "extra_days", "ignore_titles", "preview_sent", "preview_replied"):
        if key in stored:
            s = replace(s, **{key: stored[key]})
    for key in ("min_mins", "max_mins", "low_energy_days", "preferred_strength"):
        if key in stored:
            s = replace(s, **{key: stored[key]})
    for key in ("equipment_owned", "styles_in", "styles_on_request", "styles_out"):
        if key in stored:
            s = replace(s, **{key: frozenset(stored[key])})
    return s


# ---- grids: a tab of text rows, in memory (tests) or in a Google Sheet ----

class MemoryGrid:
    def __init__(self):
        self.tabs: dict[str, list[list[str]]] = {}

    def read(self, tab: str) -> list[list[str]]:
        return [list(r) for r in self.tabs.get(tab, [])]

    def write(self, tab: str, rows: list[list[str]]) -> None:
        self.tabs[tab] = [list(r) for r in rows]


class GoogleGrid:
    def __init__(self, spreadsheet_id: str, service):
        self.spreadsheet_id = spreadsheet_id
        self._sheets = service.spreadsheets()
        self._values = self._sheets.values()

    def read(self, tab: str) -> list[list[str]]:
        from googleapiclient.errors import HttpError

        try:
            rows = self._values.get(spreadsheetId=self.spreadsheet_id, range=tab).execute(num_retries=RETRIES).get("values", [])
        except HttpError as e:
            if e.resp.status == 400 and b"Unable to parse range" in (e.content or b""):  # the tab does not exist yet
                return []
            raise
        width = max((len(r) for r in rows), default=0)
        return [list(r) + [""] * (width - len(r)) for r in rows]

    def _ensure_rows(self, tab: str, needed: int) -> int:
        """Make sure the tab exists with at least `needed` rows (new Google sheets start with 1000).
        Returns how many rows the tab has afterwards (0 for a tab that was just created)."""
        for attempt in (0, 1):
            meta = self._sheets.get(spreadsheetId=self.spreadsheet_id, fields="sheets.properties").execute(
                num_retries=RETRIES)
            props = next((s["properties"] for s in meta["sheets"] if s["properties"]["title"] == tab), None)
            if props is None:
                if attempt:
                    return 0
                self._sheets.batchUpdate(spreadsheetId=self.spreadsheet_id, body={
                    "requests": [{"addSheet": {"properties": {"title": tab}}}]}).execute(num_retries=RETRIES)
                continue
            rows = props["gridProperties"]["rowCount"]
            if rows < needed:
                self._sheets.batchUpdate(spreadsheetId=self.spreadsheet_id, body={"requests": [{
                    "updateSheetProperties": {
                        "properties": {"sheetId": props["sheetId"], "gridProperties": {"rowCount": needed}},
                        "fields": "gridProperties.rowCount",
                    }}]}).execute(num_retries=RETRIES)
                rows = needed
            return rows
        return 0

    def write(self, tab: str, rows: list[list[str]]) -> None:
        """Land the new rows first, then clear only what is left below them, so a failure never loses saved data."""
        grid_rows = self._ensure_rows(tab, len(rows))
        data = [{"range": f"{tab}!A{start + 1}", "values": rows[start:start + CHUNK]}
                for start in range(0, len(rows), CHUNK)]
        if data:
            self._values.batchUpdate(
                spreadsheetId=self.spreadsheet_id, body={"valueInputOption": "RAW", "data": data},
            ).execute(num_retries=RETRIES)
        if len(rows) < grid_rows:  # Google rejects clearing a range that starts below the last row
            self._values.clear(spreadsheetId=self.spreadsheet_id, range=f"{tab}!A{len(rows) + 1}:Z", body={}
                               ).execute(num_retries=RETRIES)


class SheetsStore:
    def __init__(self, grid):
        self.grid = grid
        self._titles: dict[str, str] | None = None

    @property
    def spreadsheet_id(self) -> str | None:
        return getattr(self.grid, "spreadsheet_id", None)

    @classmethod
    def initialise(cls, grid, classes: list[AloClass], settings: Settings | None = None) -> "SheetsStore":
        grid.write("classes", [CLASS_COLS] + [_class_to_row(c) for c in classes])
        grid.write("labels", [LABEL_COLS])
        grid.write("picks", [PICK_COLS])
        grid.write("settings", _settings_to_rows(settings or Settings.default()))
        grid.write("cycle", [["start"]])
        grid.write("offers", [OFFER_COLS])
        grid.write("favourites", [FAV_COLS])
        return cls(grid)

    @classmethod
    def create(cls, title: str, classes: list[AloClass], creds) -> "SheetsStore":
        from googleapiclient.discovery import build

        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        made = service.spreadsheets().create(body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": t}} for t in TABS],
        }).execute()
        return cls.initialise(GoogleGrid(made["spreadsheetId"], service), classes)

    def _body(self, tab: str) -> list[list[str]]:
        return self.grid.read(tab)[1:]

    def load_classes(self):
        return [_row_to_class(r) for r in self._body("classes")]

    def _title(self, class_id: str) -> str:
        if self._titles is None:
            self._titles = {r[0]: r[1] for r in self._body("classes")}
        return self._titles.get(class_id, "")

    def load_labels(self):
        return {r[0]: _row_to_label(r) for r in self._body("labels") if r and r[0]}

    def save_labels(self, labels):
        rows = {r[0]: r for r in self._body("labels") if r and r[0]}
        for l in labels:
            rows[l.class_id] = _label_to_row(l, self._title(l.class_id))
        self.grid.write("labels", [LABEL_COLS] + list(rows.values()))

    def load_settings(self):
        return _rows_to_settings(self.grid.read("settings"))

    def save_settings(self, s):
        self.grid.write("settings", _settings_to_rows(s))

    def load_picks(self):
        return [_row_to_pick(r) for r in self._body("picks") if r and r[0]]

    def save_picks(self, picks):
        rows = {(r[0], r[1]): r for r in self._body("picks") if r and r[0]}
        for p in picks:
            rows[(p.week.isoformat(), p.slot)] = _pick_to_row(p)
        self.grid.write("picks", [PICK_COLS] + list(rows.values()))

    def load_cycle(self):
        return [date.fromisoformat(r[0]) for r in self._body("cycle") if r and r[0]]

    def load_favourites(self):
        return [Favourite(class_id=r[0], added=date.fromisoformat(r[2]) if len(r) > 2 and r[2] else date.min,
                          note=r[3] if len(r) > 3 else "")
                for r in self._body("favourites") if r and r[0]]

    def save_favourite(self, fav):
        rows = {r[0]: r for r in self._body("favourites") if r and r[0]}
        rows[fav.class_id] = [fav.class_id, self._title(fav.class_id), fav.added.isoformat(), fav.note]
        self.grid.write("favourites", [FAV_COLS] + list(rows.values()))

    def remove_favourite(self, class_id):
        rows = {r[0]: r for r in self._body("favourites") if r and r[0]}
        if class_id not in rows:
            return False
        del rows[class_id]
        self.grid.write("favourites", [FAV_COLS] + list(rows.values()))
        return True

    def load_offers(self, slot, week):
        for r in self._body("offers"):
            if r and r[0] == week.isoformat() and r[1] == slot:
                return json.loads(r[2])
        return []

    def save_offers(self, slot, week, class_ids):
        rows = {(r[0], r[1]): r for r in self._body("offers") if r and r[0]}
        rows[(week.isoformat(), slot)] = [week.isoformat(), slot, json.dumps(list(class_ids))]
        self.grid.write("offers", [OFFER_COLS] + list(rows.values()))

    def add_cycle_start(self, d):
        self.grid.write("cycle", [["start"]] + [[x.isoformat()] for x in sorted({*self.load_cycle(), d})])


def google_creds():
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_file(str(TOKEN_PATH))


def open_store() -> SheetsStore:
    from dotenv import load_dotenv
    from googleapiclient.discovery import build

    load_dotenv(ROOT / ".env")
    service = build("sheets", "v4", credentials=google_creds(), cache_discovery=False)
    return SheetsStore(GoogleGrid(os.environ["ALO_SHEET_ID"], service))
