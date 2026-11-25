"""Google Calendar adapter. Events copy Alo's own "Schedule > Google" format, with the time and length fixed."""
from datetime import datetime, time, timedelta
from typing import NamedTuple

from weekly_picker.config import TZ
from weekly_picker.models import AloClass

CALENDAR_ID = "primary"
LOCATION = "ALO Wellness Club On-Demand"


class BusyEvent(NamedTuple):
    start: datetime
    end: datetime
    title: str
    event_id: str


def _when(dt: datetime) -> dict:
    return {"dateTime": dt.isoformat(), "timeZone": "Europe/London"}


class Calendar:
    def __init__(self, creds=None, service=None):
        if service is None:
            from googleapiclient.discovery import build

            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self._events = service.events()

    def busy(self, start: datetime, end: datetime, ignore_ids: frozenset[str] = frozenset()) -> list[BusyEvent]:
        items = self._events.list(
            calendarId=CALENDAR_ID, timeMin=start.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, orderBy="startTime",
        ).execute().get("items", [])
        busy = []
        for item in items:
            if "dateTime" not in item.get("start", {}):  # all-day events never block a class
                continue
            if item.get("transparency") == "transparent" or item.get("status") == "cancelled":
                continue
            if item["id"] in ignore_ids:
                continue
            busy.append(BusyEvent(
                datetime.fromisoformat(item["start"]["dateTime"]).astimezone(TZ),
                datetime.fromisoformat(item["end"]["dateTime"]).astimezone(TZ),
                item.get("summary", "busy"), item["id"],
            ))
        return busy

    def create(self, c: AloClass, start: datetime, reason: str) -> str:
        body = {
            "summary": c.title,
            "location": LOCATION,
            "start": _when(start),
            "end": _when(start + timedelta(minutes=c.mins)),
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
            "extendedProperties": {"private": {"alo_class_id": c.id}},
            "description": "\n".join([
                f"Start Now: {c.url}",
                f"Class: {c.title}",
                f"Instructor: {c.instructor or 'unknown'}",
                f"Duration: {c.mins} mins",
                f"Equipment: {', '.join(sorted(c.equipment)) or 'none'}",
                f"Picked: {reason}",
            ]),
        }
        return self._events.insert(calendarId=CALENDAR_ID, body=body).execute()["id"]

    def find(self, class_id: str, start: datetime) -> str | None:
        """An event we already made for this class on that day (a failed sheet save can leave one behind)."""
        day = datetime.combine(start.date(), time(0, 0), tzinfo=TZ)
        items = self._events.list(
            calendarId=CALENDAR_ID, timeMin=day.isoformat(), timeMax=(day + timedelta(days=1)).isoformat(),
            privateExtendedProperty=f"alo_class_id={class_id}", singleEvents=True,
        ).execute().get("items", [])
        return next((i["id"] for i in items if i.get("status") != "cancelled"), None)

    def move(self, event_id: str, start: datetime, minutes: int) -> None:
        body = {"start": _when(start), "end": _when(start + timedelta(minutes=minutes))}
        self._events.patch(calendarId=CALENDAR_ID, eventId=event_id, body=body).execute()

    def delete(self, event_id: str) -> None:
        self._events.delete(calendarId=CALENDAR_ID, eventId=event_id).execute()

    def exists(self, event_id: str) -> bool:
        if not event_id:
            return False
        from googleapiclient.errors import HttpError

        try:
            event = self._events.get(calendarId=CALENDAR_ID, eventId=event_id).execute()
        except HttpError as e:
            if e.resp.status in (404, 410):
                return False
            raise
        return event.get("status") != "cancelled"
