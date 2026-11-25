# How I tested it

The picker books real calendar events and messages a real person, so most of the tests are about things going
wrong in ordinary life. Each situation below names the test file that covers it. Run them all with
`python -m pytest -q`.

Eight tests need the full private class catalogue or the live sheet, so they skip themselves on a fresh clone.
Everything else runs with no keys and no network.

| # | Situation | What should happen | Tests |
| --- | --- | --- | --- |
| 1 | A new event lands on a booked class after Sunday | The class moves to the nearest free time that day, and the message says so. Reminder-style events ("remind", "message") never trigger a move | `test_clash.py` |
| 2 | The whole day is full | The class moves to another weekday in the same week, never onto another class | `test_clash.py`, `test_timeslots.py` |
| 3 | The clash checker runs twice, or nothing clashes | A second run moves nothing; no clash means silence. Past classes are never moved | `test_clash.py` |
| 4 | There is no free time anywhere | It says so and leaves the class where it is | `test_clash.py` |
| 5 | You reply "ok" twice, or after the 23:00 Sunday auto-add | Calendar events are created once; the second "ok" is harmless | `test_commands.py` |
| 5b | Auto-add at 23:00 on Sunday | Adds the week that is about to start (not the one ending), including a fourth day, and includes a change made at 22:55. If I already replied, it stays quiet. If the picks never ran, it stays quiet and the 19:00 check is the alarm | `test_commands.py` |
| 5c | The preview never reached me | No auto-add at 23:00; the message says why, and a manual "ok" still works. A fresh plan has to be delivered again before auto-add can use it | `test_commands.py` |
| 5d | Nothing fits between 09:00 and 12:00 | Classes never start before 09:00 or end after 12:00; 10:00 is preferred, then the nearest free 15 minutes; a class that cannot fit is left out and reported, and a swap never forces one in | `test_timeslots.py`, `test_picker.py`, `test_commands.py` |
| 6 | The Sunday job runs twice | Proposed picks are replaced, scheduled ones are kept, and one-off requests are not lost | `test_commands.py` |
| 7 | You ask for picks on a Monday, midweek or after the last slot | It plans the right week, and only the slots still ahead | `test_commands.py` |
| 8 | Jev is down | Plain rules still produce a week, and the message says "picked without Jev" | `test_commands.py`, `test_messages.py` |
| 9 | The calendar write fails | It names the class that did not save and keeps the pick as proposed | `test_commands.py`, `test_gcal.py` |
| 10 | Typos and odd replies ("Tue", "tues", "TUESDAY", nonsense) | Day names work any way you type them; bad input gets a one-line answer, never silence | `test_replies.py`, `test_commands.py` |
| 11 | A low-energy day or week, or a cycle start date | Slots in the window are re-picked as gentler classes with the same goal | `test_replies.py`, `test_picker.py` |
| 12 | Feedback and history | Disliked classes never come back; classes done in the last four weeks are skipped; a skipped class does not count as done; "too hard" nudges the strength level and is clamped | `test_rules.py`, `test_replies.py` |
| 13 | Partner workouts and heavy weights | Filtered out by plain rules, checked on titles and descriptions, with solo classes that merely mention a partner kept | `test_rules.py` |
| 14 | A favourite that is longer than the usual limit | It is allowed to be long, but equipment still rules it out, and if it will not fit the calendar the next class is used | `test_picker.py` |
| 15 | Messy data | Equipment spelt several ways, multi-area focus values, a sheet tab that does not exist yet, short rows, and Google errors that need retrying, with a failed write never wiping saved rows | `test_catalogue.py`, `test_store.py` |

## What the tests do not prove

- They use a fake calendar and a fake Jev, so they show the logic is right, not that Jev's judgements are good.
  I checked the labels by eye in the sheet instead.
- The sample in this repo ranks from Jev's saved labels, not a live Jev call.
