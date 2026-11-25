from dataclasses import replace
from datetime import date, time
from types import SimpleNamespace

import pytest
from googleapiclient.errors import HttpError

from weekly_picker.models import Settings
from weekly_picker.store import GoogleGrid, InMemoryStore, MemoryGrid, SheetsStore
from tests.helpers import cls, dt, lab, pick

CLASSES = [
    cls(id="1", title="Alpha", equipment={"weights", "blocks"}, instructor="Jade Smith", focus=None, intensity=None),
    cls(id="2", title="Beta", description="line one\nline two; with, punctuation"),
]


@pytest.fixture(params=["memory", "sheets"])
def store(request):
    if request.param == "memory":
        return InMemoryStore(CLASSES)
    return SheetsStore.initialise(MemoryGrid(), CLASSES)


def test_classes_round_trip(store):
    assert store.load_classes() == CLASSES


def test_labels_upsert(store):
    store.save_labels([lab(class_id="1", main_goal="strength")])
    store.save_labels([lab(class_id="1", main_goal="flexibility", goal_probs={"flexibility": 0.9}, focus="core")])
    got = store.load_labels()
    assert len(got) == 1
    assert got["1"].main_goal == "flexibility" and got["1"].goal_probs == {"flexibility": 0.9} and got["1"].focus == "core"


def test_labels_round_trip_all_fields(store):
    original = lab(class_id="2", main_goal="calm", goal_probs={"calm": 0.7, "other": 0.3}, strength=1.25,
                   weight_needed="light", low_energy=0.81, focus=None)
    store.save_labels([original])
    assert store.load_labels()["2"] == original


def test_physio_answers_round_trip_and_old_rows_read_as_empty(store):
    store.save_labels([lab(class_id="1", physio={"side_bend": 0.9, "hinge": 0.1}, physio_feel=0.5),
                       lab(class_id="2")])
    got = store.load_labels()
    assert got["1"].physio == {"side_bend": 0.9, "hinge": 0.1} and got["1"].physio_feel == 0.5
    assert got["2"].physio == {} and got["2"].physio_feel == 0.0


def test_picks_upsert_by_week_and_slot(store):
    p = pick(week=date(2026, 10, 12), slot="Mon", class_id="a", start=dt(2026, 10, 12))
    store.save_picks([p])
    store.save_picks([replace(p, class_id="b")])
    assert [x.class_id for x in store.load_picks()] == ["b"]


def test_picks_round_trip_all_fields(store):
    p = pick(week=date(2026, 10, 12), slot="Tue", start=dt(2026, 10, 13), class_id="2", status="scheduled",
             feedback="like", event_id="evt1", requested=True,
             prev_start=dt(2026, 10, 13, 8, 0), prev_event_id="evt0")
    store.save_picks([p])
    assert store.load_picks() == [p]


def test_settings_round_trip(store):
    s = replace(Settings.default(), next_week={"all": "low energy"}, preferred_strength=1.75,
                slots={"Mon": time(9, 30), "Tue": time(11, 0), "Wed": time(9, 30)})
    store.save_settings(s)
    assert store.load_settings() == s


def test_default_settings_before_anything_saved(store):
    assert store.load_settings() == Settings.default()


def test_offers_round_trip(store):
    assert store.load_offers("Tue", date(2026, 10, 12)) == []
    store.save_offers("Tue", date(2026, 10, 12), ["a", "b"])
    assert store.load_offers("Tue", date(2026, 10, 12)) == ["a", "b"]
    assert store.load_offers("Mon", date(2026, 10, 12)) == []
    store.save_offers("Tue", date(2026, 10, 12), ["c"])
    assert store.load_offers("Tue", date(2026, 10, 12)) == ["c"]


def test_cycle_dates(store):
    assert store.load_cycle() == []
    store.add_cycle_start(date(2026, 10, 3))
    assert store.load_cycle() == [date(2026, 10, 3)]


class FakeService:
    """Records Sheets API calls; `values.get` returns a canned grid; a tab has `row_count` rows."""

    def __init__(self, values=None, row_count=1000, tabs=("classes",), read_error=None):
        self.calls, self.canned, self.row_count = [], values or [], row_count
        self.tabs, self.read_error, self.retries, self.batch_error = tabs, read_error, [], None

    def spreadsheets(self):
        return FakeSpreadsheets(self)


class _Request:
    def __init__(self, result, error=None, svc=None):
        self.result, self.error, self.svc = result, error, svc

    def execute(self, num_retries=0):
        if self.svc is not None:
            self.svc.retries.append(num_retries)
        if self.error:
            raise self.error
        return self.result


class FakeSpreadsheets:
    def __init__(self, svc):
        self.svc = svc

    def values(self):
        return FakeValues(self.svc)

    def get(self, **kw):
        self.svc.calls.append(("sheet_get", kw))
        sheets = [{"properties": {"title": t, "sheetId": 7 + i, "gridProperties": {"rowCount": self.svc.row_count}}}
                  for i, t in enumerate(self.svc.tabs)]
        return _Request({"sheets": sheets}, svc=self.svc)

    def batchUpdate(self, **kw):
        self.svc.calls.append(("batchUpdate", kw))
        return _Request({}, svc=self.svc)


class FakeValues:
    def __init__(self, svc):
        self.svc = svc

    def get(self, **kw):
        self.svc.calls.append(("get", kw))
        return _Request({"values": self.svc.canned}, self.svc.read_error, self.svc)

    def clear(self, **kw):
        self.svc.calls.append(("clear", kw))
        return _Request({}, svc=self.svc)

    def batchUpdate(self, **kw):
        self.svc.calls.append(("values_batch", kw))
        return _Request({}, self.svc.batch_error, self.svc)


def test_google_grid_read_pads_short_rows_and_handles_empty_tab():
    g = GoogleGrid("sheet-id", FakeService([["a", "b", "c"], ["1"], ["2", "3"]]))
    assert g.read("classes") == [["a", "b", "c"], ["1", "", ""], ["2", "3", ""]]
    assert GoogleGrid("sheet-id", FakeService([])).read("classes") == []


def test_google_grid_write_lands_the_data_before_clearing_the_tail():
    svc = FakeService(row_count=5000)
    rows = [["h"]] + [[str(i)] for i in range(1200)]
    GoogleGrid("sheet-id", svc).write("classes", rows)
    assert [n for n, _ in svc.calls] == ["sheet_get", "values_batch", "clear"]
    body = [kw for n, kw in svc.calls if n == "values_batch"][0]["body"]
    assert body["valueInputOption"] == "RAW"
    assert [len(d["values"]) for d in body["data"]] == [500, 500, 201]
    assert [d["range"] for d in body["data"]] == ["classes!A1", "classes!A501", "classes!A1001"]
    clear = [kw for n, kw in svc.calls if n == "clear"][0]
    assert clear["range"] == "classes!A1202:Z"  # only what is below the new data


def test_google_grid_write_skips_the_clear_when_the_data_fills_the_tab():
    svc = FakeService(row_count=3)  # Google rejects clearing a range that starts below the last row
    GoogleGrid("sheet-id", svc).write("classes", [["h"], ["1"], ["2"]])
    assert [n for n, _ in svc.calls] == ["sheet_get", "values_batch"]


def test_google_grid_a_failed_write_never_clears_the_old_rows():
    svc = FakeService(row_count=5000)
    svc.batch_error = HttpError(SimpleNamespace(status=429, reason="Too Many Requests"), b"quota")
    with pytest.raises(HttpError):
        GoogleGrid("sheet-id", svc).write("labels", [["h"], ["1"]])
    assert "clear" not in [n for n, _ in svc.calls]


def test_google_grid_retries_transient_errors():
    svc = FakeService(row_count=5000)
    GoogleGrid("sheet-id", svc).write("labels", [["h"], ["1"]])
    GoogleGrid("sheet-id", svc).read("labels")
    assert svc.retries and all(r >= 3 for r in svc.retries)


def test_google_grid_write_grows_a_tab_that_is_too_short():
    svc = FakeService(row_count=1000)
    GoogleGrid("sheet-id", svc).write("classes", [["h"]] + [[str(i)] for i in range(4745)])
    [(_, grow)] = [c for c in svc.calls if c[0] == "batchUpdate"]
    req = grow["body"]["requests"][0]["updateSheetProperties"]
    assert req["properties"] == {"sheetId": 7, "gridProperties": {"rowCount": 4746}}
    assert req["fields"] == "gridProperties.rowCount"
    names = [n for n, _ in svc.calls]
    assert names.index("batchUpdate") < names.index("values_batch")


def test_google_grid_read_of_a_missing_tab_is_empty():
    missing = HttpError(SimpleNamespace(status=400, reason="Bad Request"), b"Unable to parse range: offers")
    assert GoogleGrid("sheet-id", FakeService(read_error=missing)).read("offers") == []


def test_google_grid_write_creates_a_missing_tab_first():
    svc = FakeService(tabs=("classes",))
    GoogleGrid("sheet-id", svc).write("offers", [["week", "slot", "class_ids"]])
    first = [c for c in svc.calls if c[0] == "batchUpdate"][0][1]["body"]["requests"][0]
    assert first == {"addSheet": {"properties": {"title": "offers"}}}
    names = [n for n, _ in svc.calls]
    assert names.index("batchUpdate") < names.index("values_batch")


def test_physio_can_be_stored_as_compact_percentages():
    grid = MemoryGrid()
    store = SheetsStore.initialise(grid, CLASSES)
    store.save_labels([lab(class_id="1")])
    row = grid.tabs["labels"][1]
    row[8], row[9] = "26 13 23 33 34", "0.54"
    grid.tabs["labels"][1] = row
    got = store.load_labels()["1"]
    assert got.physio == {"shoulder_stability": 0.26, "hinge": 0.13, "balance": 0.23, "side_bend": 0.33,
                          "spine_twist": 0.34} and got.physio_feel == 0.54


def test_favourites_save_list_and_remove(store):
    from weekly_picker.models import Favourite
    store.save_favourite(Favourite(class_id="1", added=date(2026, 11, 18), note="loved the twists"))
    store.save_favourite(Favourite(class_id="2", added=date(2026, 11, 19)))
    store.save_favourite(Favourite(class_id="1", added=date(2026, 11, 20), note="again"))  # same class: updates
    got = {f.class_id: f for f in store.load_favourites()}
    assert set(got) == {"1", "2"} and got["1"].note == "again" and got["1"].added == date(2026, 11, 20)
    assert store.remove_favourite("1") is True and store.remove_favourite("1") is False
    assert [f.class_id for f in store.load_favourites()] == ["2"]


def test_a_live_sheet_without_a_favourites_tab_reads_empty_and_creates_it_on_first_save():
    from weekly_picker.models import Favourite
    grid = MemoryGrid()
    store = SheetsStore.initialise(grid, CLASSES)
    del grid.tabs["favourites"]  # Sheets made before favourites existed
    assert store.load_favourites() == [] and store.remove_favourite("1") is False
    store.save_favourite(Favourite(class_id="1", added=date(2026, 11, 18), note="hi"))
    assert grid.tabs["favourites"] == [["class_id", "title", "added", "note"], ["1", "Alpha", "2026-11-18", "hi"]]
