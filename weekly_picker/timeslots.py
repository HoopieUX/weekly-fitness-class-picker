"""Pure free-time maths. A busy item is anything indexable as (start, end, ...), all timezone-aware."""
from datetime import date, datetime, time, timedelta

from weekly_picker.config import TZ

Busy = tuple[datetime, datetime]
_WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
_STEP = timedelta(minutes=15)


def slot_start(week: date, slot: str, at: time) -> datetime:
    """`week` is the Monday. Wall-clock time in London, so 9:30 stays 9:30 across a clock change."""
    return datetime.combine(week + timedelta(days=_WEEKDAYS[slot]), at, tzinfo=TZ)


def overlaps(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _free(start: datetime, minutes: int, busy) -> bool:
    window = (start, start + timedelta(minutes=minutes))
    return not any(overlaps(window, b) for b in busy)


def find_same_day(
    preferred: datetime,
    minutes: int,
    busy,
    earliest: time = time(7, 0),
    latest_end: time = time(21, 0),
) -> datetime | None:
    """Nearest free start to `preferred` on the same day (earlier wins a tie), or None if the day is full."""
    first = datetime.combine(preferred.date(), earliest, tzinfo=TZ)
    last_end = datetime.combine(preferred.date(), latest_end, tzinfo=TZ)
    length = timedelta(minutes=minutes)
    if first <= preferred and preferred + length <= last_end and _free(preferred, minutes, busy):
        return preferred
    candidates = []
    t = first
    while t + length <= last_end:
        if _free(t, minutes, busy):
            candidates.append(t)
        t += _STEP
    return min(candidates, key=lambda c: (abs(c - preferred), c), default=None)


def find_next_weekday(after: datetime, at: time, minutes: int, busy, taken_days: set[date]) -> datetime | None:
    """First free weekday after `after`, within the same Mon to Fri week, that is not already holding a class."""
    day = after.date() + timedelta(days=1)
    while day.weekday() <= 4 and day.weekday() > after.date().weekday():
        if day not in taken_days:
            found = find_same_day(datetime.combine(day, at, tzinfo=TZ), minutes, busy)
            if found:
                return found
        day += timedelta(days=1)
    return None
