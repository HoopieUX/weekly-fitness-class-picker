# Weekly fitness class picker: notes for Claude Code

- Run tests with `.venv/bin/python -m pytest -q`. The system `python3` has no pytest.
- Classes are placed 09:00 to 12:00, at 10:00 if free (`PLACE_*` in `weekly_picker/config.py`). The days and goals live in
  the Google Sheet settings; the per-day times there no longer set the start. `move <day> <HH:MM>` puts one class exactly
  where asked.
- The real class catalogue (`alo-scoring/`) is private and not in git. Tests that need it skip when it is absent.
- Agents (Instinct and others) read this repo for the code: see `docs/for-agents.md` for the schedule and commands.
- Built with Claude Code; I now talk to it through Instinct on WhatsApp.

## Favourites

Georgia can log classes she loves, and the picker leans towards them (the same 0.15 nudge as a liked class).
A favourite ignores the 10 to 30 minute length limit (equipment, style and the rest still apply).
They live in the Sheet's `favourites` tab, which is created the first time `fav` runs.

- `fav <title, class id or day>` adds one. A day (Tue, tues, Tuesday) means the last class that happened that day. `--note ...` adds a note (no quotes needed); `fav` again with a new note updates it.
- `unfav <title, class id or day>` removes one, including a class that has left the catalogue (by id). `favs` lists them, newest first.
- Liked and favourite boosts don't stack. If a long favourite won't fit the calendar, the picker uses the next class.
