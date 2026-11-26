"""Pure free-time maths. A busy item is anything indexable as (start, end, ...), all timezone-aware."""
from datetime import date, datetime, time, timedelta

from weekly_picker.config import PLACE_EARLIEST, PLACE_LATEST_END, PLACE_PREFERRED, TZ

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
    earliest: time = PLACE_EARLIEST,
    latest_end: time = PLACE_LATEST_END,
) -> datetime | None:
    """Nearest free start to `preferred` on the same day (earlier wins a tie), or None if the window is full.

    A class starts no earlier than `earliest` and ends by `latest_end` (09:00 and 12:00 unless told otherwise).
    A preferred time outside that window is replaced by 10:00."""
    first = datetime.combine(preferred.date(), earliest, tzinfo=TZ)
    last_end = datetime.combine(preferred.date(), latest_end, tzinfo=TZ)
    length = timedelta(minutes=minutes)
    if not first <= preferred or preferred + length > last_end:
        preferred = datetime.combine(preferred.date(), PLACE_PREFERRED, tzinfo=TZ)
    if first <= preferred and preferred + length <= last_end and _free(preferred, minutes, busy):
        return preferred
    candidates = []
    t = first
    while t + length <= last_end:
        if _free(t, minutes, busy):
            candidates.append(t)
        t += _STEP
    return min(candidates, key=lambda c: (abs(c - preferred), c), default=None)


def place_on_day(day: date, minutes: int, busy) -> datetime | None:
    """Where a class goes on `day`: 10:00 if free, else the nearest free 15-minute start that still ends by 12:00
    and starts no earlier than 09:00 (earlier wins a tie). None when nothing fits: the class is not placed."""
    preferred = datetime.combine(day, PLACE_PREFERRED, tzinfo=TZ)
    return find_same_day(preferred, minutes, busy, earliest=PLACE_EARLIEST, latest_end=PLACE_LATEST_END)
