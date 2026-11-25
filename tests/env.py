import shlex
from datetime import date, datetime, timedelta

from weekly_picker.commands import main
from weekly_picker.config import TZ
from weekly_picker.gcal import BusyEvent
from weekly_picker.models import AloClass
from weekly_picker.store import InMemoryStore
from tests.helpers import lab
from tests.world import WEEK, World


class FakeCalendar:
    def __init__(self):
        self.events, self.created, self.busy_events, self.fail_create = {}, 0, [], False

    def add_busy(self, title, start, end):
        self.busy_events.append(BusyEvent(_t(start), _t(end), title, f"busy{len(self.busy_events)}"))

    def busy(self, start, end, ignore_ids=frozenset()):
        return [b for b in self.busy_events if b[0] < end and start < b[1] and b[3] not in ignore_ids]

    def create(self, c, start, reason):
        if self.fail_create:
            raise RuntimeError("calendar down")
        self.created += 1
        self.events[f"evt{self.created}"] = (c.id, start, reason)
        return f"evt{self.created}"

    def find(self, class_id, start):
        return next((eid for eid, (cid, s, _) in self.events.items() if cid == class_id and s.date() == start.date()),
                    None)

    def exists(self, event_id):
        return event_id in self.events

    def delete(self, event_id):
        self.events.pop(event_id, None)

    def move(self, event_id, start, minutes):
        self.events[event_id] = (self.events[event_id][0], start, self.events[event_id][2])

    @property
    def live(self):
        return len(self.events)


def _t(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=TZ)


class Env:
    def __init__(self, extra: list[AloClass] | None = None):
        self.world = World()
        for c in extra or []:
            self.world.classes.append(c)
            self.world.labels[c.id] = lab(class_id=c.id, main_goal="other", goal_probs={"other": 0.9}, strength=0.5)
        self.store = InMemoryStore(self.world.classes)
        self.store.save_labels(list(self.world.labels.values()))
        self.calendar = FakeCalendar()
        self.last = []
        self.now = datetime(2026, 10, 11, 18, 0, tzinfo=TZ)  # Sunday 6pm
        self.target = WEEK

    def run(self, *argv, **kw):
        args = [word for part in argv for word in shlex.split(part)]
        return main(args, store=self.store, calendar=self.calendar, now=self.now, **kw)

    def at(self, text: str):
        self.now = datetime.fromisoformat(text).replace(tzinfo=TZ)

    def week(self, week: date | None = None):
        order = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
        week = week or self.target
        return sorted((p for p in self.store.load_picks() if p.week == week), key=lambda p: order[p.slot])

    def finish_a_week(self):
        """Plan and approve the week of 12 Oct, then move to the Sunday after and plan 19 Oct (the new target)."""
        self.run("sunday"); self.run("approve")
        self.now = datetime(2026, 10, 18, 18, 0, tzinfo=TZ)
        self.run("sunday")
        self.last = self.week(WEEK)
        self.target = WEEK + timedelta(days=7)


