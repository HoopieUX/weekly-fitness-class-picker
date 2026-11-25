from types import SimpleNamespace

from googleapiclient.errors import HttpError

from weekly_picker.gcal import Calendar
from tests.helpers import cls, dt


class _Request:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class FakeEvents:
    def __init__(self, items=(), get_result=None, get_error=None):
        self.items, self.get_result, self.get_error, self.calls = list(items), get_result, get_error, []

    def list(self, **kw):
        self.calls.append(("list", kw))
        return _Request({"items": self.items})

    def insert(self, **kw):
        self.calls.append(("insert", kw))
        return _Request({"id": "new-event"})

    def patch(self, **kw):
        self.calls.append(("patch", kw))
        return _Request({})

    def delete(self, **kw):
        self.calls.append(("delete", kw))
        return _Request({})

    def get(self, **kw):
        self.calls.append(("get", kw))
        return _Request(self.get_result, self.get_error)


def calendar(events: FakeEvents) -> Calendar:
    return Calendar(service=SimpleNamespace(events=lambda: events))


def timed(id, title, start, end, **extra):
    return {"id": id, "summary": title, "start": {"dateTime": start}, "end": {"dateTime": end}, **extra}


def test_busy_returns_timed_events_with_titles_and_tz():
    ev = FakeEvents([timed("e1", "Dentist", "2026-10-13T09:00:00+01:00", "2026-10-13T10:30:00+01:00")])
    [b] = calendar(ev).busy(dt(2026, 10, 13, 0, 0), dt(2026, 10, 14, 0, 0))
    assert (b.title, b.event_id) == ("Dentist", "e1")
    assert b.start == dt(2026, 10, 13, 9, 0) and b.end == dt(2026, 10, 13, 10, 30)
    assert ev.calls[0][1]["singleEvents"] is True and ev.calls[0][1]["calendarId"] == "primary"


def test_busy_ignores_all_day_free_cancelled_and_ignored_ids():
    ev = FakeEvents([
        {"id": "a", "summary": "Birthday", "start": {"date": "2026-10-13"}, "end": {"date": "2026-10-14"}},
        timed("b", "Maybe coffee", "2026-10-13T09:30:00+01:00", "2026-10-13T10:00:00+01:00", transparency="transparent"),
        timed("c", "Cancelled", "2026-10-13T09:30:00+01:00", "2026-10-13T10:00:00+01:00", status="cancelled"),
        timed("d", "My class", "2026-10-13T09:30:00+01:00", "2026-10-13T09:50:00+01:00"),
        timed("e", "Real meeting", "2026-10-13T11:00:00+01:00", "2026-10-13T12:00:00+01:00"),
    ])
    got = calendar(ev).busy(dt(2026, 10, 13, 0, 0), dt(2026, 10, 14, 0, 0), ignore_ids=frozenset({"d"}))
    assert [b.event_id for b in got] == ["e"]


def test_create_builds_the_event_from_alos_format():
    ev = FakeEvents()
    c = cls(id="9", title="Day 2: Quick Core", mins=9, equipment={"blocks", "weights"}, instructor="Jade Smith",
            url="https://example.com/classes/9")
    assert calendar(ev).create(c, dt(2026, 10, 13), "strength, core, weights") == "new-event"
    body = ev.calls[0][1]["body"]
    assert body["summary"] == "Day 2: Quick Core" and body["location"] == "ALO Wellness Club On-Demand"
    assert body["start"]["dateTime"] == dt(2026, 10, 13).isoformat() and body["start"]["timeZone"] == "Europe/London"
    assert body["end"]["dateTime"] == dt(2026, 10, 13, 9, 39).isoformat()
    assert body["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]}
    assert body["extendedProperties"]["private"]["alo_class_id"] == "9"
    assert body["description"] == (
        "Start Now: https://example.com/classes/9\n"
        "Class: Day 2: Quick Core\nInstructor: Jade Smith\nDuration: 9 mins\n"
        "Equipment: blocks, weights\nPicked: strength, core, weights"
    )


def test_create_with_unknown_instructor_and_no_equipment():
    ev = FakeEvents()
    calendar(ev).create(cls(), dt(2026, 10, 13), "calm")
    desc = ev.calls[0][1]["body"]["description"]
    assert "Instructor: unknown" in desc and "Equipment: none" in desc


def test_move_patches_start_and_end():
    ev = FakeEvents()
    calendar(ev).move("evt", dt(2026, 10, 13, 11, 0), 25)
    kw = ev.calls[0][1]
    assert kw["eventId"] == "evt" and kw["body"]["start"]["dateTime"] == dt(2026, 10, 13, 11, 0).isoformat()
    assert kw["body"]["end"]["dateTime"] == dt(2026, 10, 13, 11, 25).isoformat()


def test_delete_calls_delete():
    ev = FakeEvents()
    calendar(ev).delete("evt")
    assert ev.calls[0][0] == "delete" and ev.calls[0][1]["eventId"] == "evt"


def test_exists_true_false_for_missing_and_cancelled():
    assert calendar(FakeEvents(get_result={"id": "x", "status": "confirmed"})).exists("x") is True
    assert calendar(FakeEvents(get_result={"id": "x", "status": "cancelled"})).exists("x") is False
    gone = HttpError(SimpleNamespace(status=404, reason="Not Found"), b"")
    assert calendar(FakeEvents(get_error=gone)).exists("x") is False
    assert calendar(FakeEvents(get_result={})).exists("") is False


def test_find_looks_for_our_marker_on_that_day():
    ev = FakeEvents([timed("old", "Day 2: Quick Core", "2026-10-13T09:30:00+01:00", "2026-10-13T09:39:00+01:00")])
    assert calendar(ev).find("9", dt(2026, 10, 13)) == "old"
    kw = ev.calls[0][1]
    assert kw["privateExtendedProperty"] == "alo_class_id=9" and kw["singleEvents"] is True
    assert kw["timeMin"] == dt(2026, 10, 13, 0, 0).isoformat() and kw["timeMax"] == dt(2026, 10, 14, 0, 0).isoformat()


def test_find_returns_none_when_nothing_matches_or_it_was_cancelled():
    assert calendar(FakeEvents([])).find("9", dt(2026, 10, 13)) is None
    gone = timed("x", "t", "2026-10-13T09:30:00+01:00", "2026-10-13T10:00:00+01:00", status="cancelled")
    assert calendar(FakeEvents([gone])).find("9", dt(2026, 10, 13)) is None
