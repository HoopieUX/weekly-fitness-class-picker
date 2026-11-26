from datetime import time
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")
CARDIO_THRESHOLD = 0.4
REPEAT_DAYS = 28
# Classes are only ever placed automatically between 09:00 and 12:00, preferably starting at 10:00.
PLACE_EARLIEST = time(9, 0)
PLACE_LATEST_END = time(12, 0)
PLACE_PREFERRED = time(10, 0)
# On Sunday, auto-add only runs from this time: no reply to the preview by then counts as approval.
AUTOADD_FROM = time(23, 0)
