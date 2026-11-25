"""The CLI. Every command returns the text the chat agent should send back (empty string = say nothing)."""
import argparse
import asyncio
import fcntl
import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from weekly_picker import messages
from weekly_picker.config import TZ
from weekly_picker.jev import GOALS, make_ranker
from weekly_picker.labeller import label_all, label_all_async
from weekly_picker.models import AloClass, Favourite, Labels, Pick
from weekly_picker.picker import alternatives, focus_of, label_ranker, plan_week
from weekly_picker.store import ROOT
from weekly_picker.timeslots import find_next_weekday, find_same_day, overlaps, slot_start

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
LOCK_PATH = ROOT / ".alo.lock"  # commands queue behind this, so cron jobs and replies never interleave
_FEEDBACK = ("like", "dislike", "too_hard", "too_easy")
_STRENGTH_STEP = 0.25
_STRENGTH_RANGE = (0.0, 3.0)  # Jev Scores are 0-indexed: none=0 ... heavy=3
_DAY_BY_KEY = {d.casefold(): d for d in _DAYS}  # replies arrive lowercase ("more thu"), slots are "Thu"


def _day(value: str) -> str:
    """Canonicalise a day name from a reply: "thu", "THURSDAY" -> "Thu", otherwise unchanged
    so the caller's own error message reads back what was actually sent."""
    return _DAY_BY_KEY.get(value.strip().casefold(), value)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def current_week(now: datetime) -> date:
    return _monday(now.date())


def next_week(now: datetime) -> date:
    return current_week(now) + timedelta(days=7)


def target_week(now: datetime, settings) -> date:
    """The week to plan: this week while any slot is still ahead, otherwise the next one."""
    for week in (current_week(now), next_week(now)):
        if any(slot_start(week, slot, at) > now for slot, at in settings.slots.items()):
            return week
    return next_week(now)


def _active_week(picks: list[Pick], now: datetime) -> date | None:
    """The earliest week that still has a weekday left (so Sunday belongs to the week about to start)."""
    return min((p.week for p in picks if p.week + timedelta(days=4) >= now.date()), default=None)


class _Context:
    def __init__(self, store, calendar, client, label_client, now):
        self._store, self._calendar, self._client, self.label_client = store, calendar, client, label_client
        self.now = now

    @property
    def store(self):
        if self._store is None:
            from weekly_picker.store import open_store

            self._store = open_store()
        return self._store

    @property
    def calendar(self):
        if self._calendar is None:
            from weekly_picker.gcal import Calendar
            from weekly_picker.store import google_creds

            self._calendar = Calendar(google_creds())
        return self._calendar

    def jev_client(self):
        if self._client is None:
            from dotenv import load_dotenv
            from typesafe_sdk import TypeSafeClient

            from weekly_picker.store import ROOT

            load_dotenv(ROOT / ".env")
            self._client = TypeSafeClient()
        return self._client


def _by_slot(picks: list[Pick]) -> list[Pick]:
    return sorted(picks, key=lambda p: _DAYS.index(p.slot))


def _ranker(ctx: _Context, labels: dict[str, Labels]):
    """Jev ranking that quietly falls back to the saved labels when TypeSafe is unavailable."""
    fallback, state = label_ranker(labels), {"jev": True}

    def ranker(goal, modifiers, candidates):
        if state["jev"]:
            try:
                return make_ranker(ctx.jev_client())(goal, modifiers, candidates)
            except Exception:  # noqa: BLE001  (TypeSafe down, no key, rate limit)
                state["jev"] = False
        return fallback(goal, modifiers, candidates)

    return ranker, state


def _week_window(week: date) -> tuple[datetime, datetime]:
    start = datetime.combine(week, time(0, 0), tzinfo=TZ)
    return start, start + timedelta(days=5)


def _reason(c: AloClass, labels: dict[str, Labels]) -> str:
    return ", ".join([labels[c.id].main_goal, focus_of(c, labels) or "full body",
                      messages.equipment_text(c, labels[c.id])])


def _slot_error(settings, slot: str) -> str | None:
    if slot in settings.slots:
        return None
    names = sorted(settings.slots, key=_DAYS.index)
    return f"I only know {', '.join(names[:-1])} and {names[-1]}."


def _busy(ctx: _Context, settings, start: datetime, end: datetime, ignore_ids: frozenset[str] = frozenset()):
    """Calendar events that block a class: not our own, and not reminders ("Message Hex...", "Remind me...")."""
    words = tuple(w.lower() for w in settings.ignore_titles)
    return [b for b in ctx.calendar.busy(start, end, ignore_ids=ignore_ids)
            if not (words and b.title.strip().lower().startswith(words))]


def _prune_extra_days(ctx: _Context, settings):
    """Temporary extra days end on the Friday of their week; drop any that are over."""
    over = [day for day, last in settings.extra_days.items() if date.fromisoformat(last) < ctx.now.date()]
    if not over:
        return settings
    cleaned = replace(
        settings,
        slots={d: t for d, t in settings.slots.items() if d not in over},
        slot_goals={d: g for d, g in settings.slot_goals.items() if d not in over},
        extra_days={d: v for d, v in settings.extra_days.items() if d not in over},
    )
    ctx.store.save_settings(cleaned)
    return cleaned


class _Data:
    """Everything a command needs, loaded once."""

    def __init__(self, ctx: _Context):
        store = ctx.store
        self.classes_list = store.load_classes()
        self.classes = {c.id: c for c in self.classes_list}
        self.labels, self.settings = store.load_labels(), _prune_extra_days(ctx, store.load_settings())
        self.picks, self.cycle = store.load_picks(), store.load_cycle()
        self.favourites = frozenset(f.class_id for f in store.load_favourites())


def _merge(next_week_settings: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    merged = dict(next_week_settings)
    for key, text in overrides.items():
        merged[key] = f"{merged[key]}, {text}" if merged.get(key) else text
    return merged


def _create_event(ctx: _Context, c: AloClass, start: datetime, labels) -> tuple[str, str | None]:
    try:
        return ctx.calendar.find(c.id, start) or ctx.calendar.create(c, start, _reason(c, labels)), None
    except Exception:  # noqa: BLE001  (one failed class must not stop the others)
        return "", messages.save_failed(c)


def _place(ctx: _Context, data: _Data, old: Pick | None, new: Pick) -> tuple[Pick, str | None]:
    """Replace `old` by `new` in storage and the calendar. A week already on the calendar keeps new classes on it."""
    if old is not None and old.status == "scheduled" and old.event_id:
        ctx.calendar.delete(old.event_id)
    on_calendar = any(p.week == new.week and p.status == "scheduled" for p in data.picks)
    failure = None
    if on_calendar and new.class_id:
        event_id, failure = _create_event(ctx, data.classes[new.class_id], new.start, data.labels)
        new = replace(new, status="scheduled" if event_id else "proposed", event_id=event_id)
    elif new.class_id:
        new = replace(new, status="proposed", event_id="")
    ctx.store.save_picks([new])
    return new, failure


# ---------------------------------------------------------------- weekly runs

def _render_week(data: "_Data", week: date, picks: list[Pick], jev_used: bool) -> str:
    this_week = _by_slot([p for p in picks if p.week == week])
    last_week = _by_slot([p for p in data.picks if p.week == week - timedelta(days=7)])
    return messages.sunday(last_week, this_week, data.classes, data.labels, jev_used)


def cmd_sunday(ctx: _Context, force: bool) -> str:
    """Plan the coming week. `sunday` (the cron job) is safe to run twice; `pick` always plans afresh."""
    store, now = ctx.store, ctx.now
    data = _Data(ctx)
    week = target_week(now, data.settings)
    existing = [p for p in data.picks if p.week == week]
    if existing and not force:
        return _render_week(data, week, data.picks, all(p.jev_used for p in existing))
    kept = {p.slot for p in existing if p.status in ("scheduled", "done")}
    ahead = [slot for slot, at in data.settings.slots.items() if slot_start(week, slot, at) > now]
    start, end = _week_window(week)
    busy = _busy(ctx, data.settings, start, end, frozenset(p.event_id for p in existing if p.event_id))
    ranker, state = _ranker(ctx, data.labels)
    keep = [p for p in existing if p.class_id and (p.slot in kept or p.slot not in ahead)]
    planned = plan_week(week, data.classes_list, data.labels, data.settings, data.picks, busy, ranker,
                        today=now.date(), cycle=data.cycle, keep=keep, only=ahead, favourites=data.favourites)
    store.save_picks([replace(p, jev_used=state["jev"]) for p in planned if p.slot not in kept])
    if data.settings.next_week:
        store.save_settings(replace(data.settings, next_week={}))
    return _render_week(data, week, store.load_picks(), state["jev"])


def _approve_week(ctx: _Context, week: date) -> tuple[list[Pick], list[str]]:
    data = _Data(ctx)
    added, failures = [], []
    for p in _by_slot([p for p in data.picks if p.week == week and p.status == "proposed" and p.class_id]):
        if p.event_id and ctx.calendar.exists(p.event_id):
            ctx.store.save_picks([replace(p, status="scheduled")])
            continue
        event_id, failure = _create_event(ctx, data.classes[p.class_id], p.start, data.labels)
        if failure:
            failures.append(failure)
            continue
        done = replace(p, status="scheduled", event_id=event_id)
        ctx.store.save_picks([done])
        added.append(done)
    return added, failures


def _pending_week(ctx: _Context) -> date | None:
    weeks = [p.week for p in ctx.store.load_picks() if p.status == "proposed" and p.class_id
             and p.week + timedelta(days=4) >= ctx.now.date()]
    return min(weeks, default=None)


def cmd_approve(ctx: _Context) -> str:
    week = _pending_week(ctx)
    if week is None:
        return "Already added this week's classes."
    added, failures = _approve_week(ctx, week)
    data = _Data(ctx)
    lines = ([messages.added(added, data.classes, data.labels)] if added else []) + failures
    return "\n".join(lines)


def cmd_autoadd(ctx: _Context) -> str:
    """Add whatever is still only proposed. Runs at 11pm on Sunday, when "this week" is the one that is ending,
    so it uses the same week as `approve`: the earliest week with proposed picks and a weekday left."""
    week = _pending_week(ctx)
    if week is None:
        return ""
    _, failures = _approve_week(ctx, week)
    return "\n".join([messages.autoadded(), *failures])


def cmd_show(ctx: _Context) -> str:
    """Repeat the message for the week in progress (or the one about to start). Changes nothing."""
    data = _Data(ctx)
    week = _active_week(data.picks, ctx.now)
    if week is None:
        return "No classes picked yet. Reply pick to make some."
    return _render_week(data, week, data.picks, all(p.jev_used for p in data.picks if p.week == week))


def cmd_check_ran(ctx: _Context) -> str:
    week = target_week(ctx.now, ctx.store.load_settings())
    return "" if any(p.week == week for p in ctx.store.load_picks()) else messages.not_run()


def cmd_clash_check(ctx: _Context) -> str:
    """Move any future scheduled class that something new now overlaps. Silent when nothing clashes."""
    data = _Data(ctx)
    upcoming = sorted((p for p in data.picks if p.status == "scheduled" and p.class_id and p.event_id
                       and p.start > ctx.now), key=lambda p: p.start)
    if not upcoming:
        return ""
    own = frozenset(p.event_id for p in data.picks if p.status == "scheduled" and p.event_id)
    first = datetime.combine(upcoming[0].start.date(), time(0, 0), tzinfo=TZ)
    week_end = datetime.combine(_monday(upcoming[-1].start.date()) + timedelta(days=5), time(0, 0), tzinfo=TZ)
    busy = _busy(ctx, data.settings, first, week_end, own)  # up to Friday night: a class can move that far
    windows = {p.event_id: (p.start, p.start + timedelta(minutes=data.classes[p.class_id].mins)) for p in upcoming}
    lines = []
    for p in upcoming:
        c = data.classes[p.class_id]
        clash = next((b for b in busy if overlaps(windows[p.event_id], b)), None)
        if clash is None:
            continue
        others = [w for eid, w in windows.items() if eid != p.event_id]
        blocked = busy + others
        new = find_same_day(p.start, c.mins, blocked) or find_next_weekday(
            p.start, data.settings.slots[p.slot], c.mins, blocked, {w[0].date() for w in others})
        if new is None:
            lines.append(messages.could_not_move(p.slot, clash.title))
            continue
        ctx.calendar.move(p.event_id, new, c.mins)
        ctx.store.save_picks([replace(p, start=new, prev_start=p.start, prev_event_id=p.event_id)])
        windows[p.event_id] = (new, new + timedelta(minutes=c.mins))
        lines.append(messages.moved(p.slot, new, clash.title))
    return "\n".join(lines)


def cmd_label(ctx: _Context, limit: int | None) -> str:
    store = ctx.store
    classes = store.load_classes()
    if ctx.label_client is not None:
        n = label_all(classes, store, ctx.label_client, limit=limit)
    else:
        from dotenv import load_dotenv
        from typesafe_sdk import AsyncTypeSafeClient

        from weekly_picker.store import ROOT

        load_dotenv(ROOT / ".env")

        async def run() -> int:
            async with AsyncTypeSafeClient() as client:
                return await label_all_async(classes, store, client, limit=limit)

        n = asyncio.run(run())
    return f"Labelled {n} classes ({len(store.load_labels())} of {len(classes)} now labelled)."


def cmd_import_physio(ctx: _Context, path: str | None) -> str:
    """Add physio answers that were asked of Jev elsewhere (one JSON line per class) to the saved labels.
    Every other answer in a label stays as it was. Classes with no label yet are skipped: `label` asks them
    everything, physio included."""
    file = Path(path) if path else ROOT / "data" / "physio_labels.jsonl"
    if not file.exists():
        return f"I couldn't find {file}."
    answers = {}
    for line in file.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            answers[row["class_id"]] = row
    labels = ctx.store.load_labels()
    updated = [replace(l, physio=answers[cid]["physio"], physio_feel=answers[cid]["physio_feel"])
               for cid, l in labels.items() if cid in answers]
    if updated:
        ctx.store.save_labels(updated)
    missing = len(labels) - len(updated)
    extra = f" {missing} labelled classes had no physio answers; run label to ask them." if missing else ""
    return f"Added physio answers to {len(updated)} classes.{extra}"


# ---------------------------------------------------------------- replies

def _repick(ctx: _Context, week: date, slots: list[str], *, overrides: dict[str, str] | None = None,
            exclude_old: bool = False, prefer_same_focus: bool = False) -> str:
    """Re-plan some slots of an existing week, keeping the others, and update the calendar for any that changed."""
    data = _Data(ctx)
    this_week = {p.slot: p for p in data.picks if p.week == week}
    keep = [p for s, p in this_week.items() if s not in slots and p.class_id and p.status != "skipped"]
    old = {s: this_week[s] for s in slots if s in this_week}
    settings = replace(data.settings, next_week=_merge(data.settings.next_week, overrides or {}))
    ranker, state = _ranker(ctx, data.labels)
    start, end = _week_window(week)
    busy = _busy(ctx, data.settings, start, end, frozenset(p.event_id for p in old.values() if p.event_id))
    prefer = {s: focus_of(data.classes[o.class_id], data.labels) for s, o in old.items()
              if prefer_same_focus and o.class_id}
    exclude = frozenset(o.class_id for o in old.values() if o.class_id) if exclude_old else frozenset()
    planned = plan_week(week, data.classes_list, data.labels, settings, data.picks, busy, ranker,
                        today=ctx.now.date(), cycle=data.cycle, keep=keep, only=slots, exclude_ids=exclude,
                        prefer_focus=prefer, favourites=data.favourites)
    result, failures = [], []
    for p in planned:
        p, failure = _place(ctx, data, old.get(p.slot), replace(p, jev_used=state["jev"]))
        result.append(p)
        failures += [failure] if failure else []
    return "\n".join([messages.updated(result, data.classes, data.labels), *failures])


def _apply_modifier(ctx: _Context, key: str, text: str, description: str) -> str:
    data = _Data(ctx)
    week = _active_week(data.picks, ctx.now)
    slots = sorted(data.settings.slots, key=_DAYS.index) if key == "all" else [key]
    if week is None:
        ctx.store.save_settings(replace(data.settings, next_week=_merge(data.settings.next_week, {key: text})))
        return f"Okay, {description} next week."
    return _repick(ctx, week, slots, overrides={key: text})


def cmd_goal(ctx: _Context, slot: str, goal: str) -> str:
    settings = ctx.store.load_settings()
    if slot != "all" and (error := _slot_error(settings, slot)):
        return error
    if goal not in GOALS:
        return f"I don't know that goal. Try: {', '.join(GOALS)}."
    return _apply_modifier(ctx, slot, goal, f"{'all slots' if slot == 'all' else slot} will be {goal}")


def cmd_next_week(ctx: _Context, text: str) -> str:
    return _apply_modifier(ctx, "all", text.strip().lower(), text.strip().lower())


def cmd_set_goal(ctx: _Context, slot: str, goal: str) -> str:
    settings = ctx.store.load_settings()
    if error := _slot_error(settings, slot):
        return error
    if goal not in GOALS:
        return f"I don't know that goal. Try: {', '.join(GOALS)}."
    ctx.store.save_settings(replace(settings, slot_goals={**settings.slot_goals, slot: goal}))
    return f"{slot} is now a {goal} day."


def _clock(t: time) -> str:
    return f"{t.hour}:{t.minute:02d}"


def _check_new_slot(day: str, at: str, goal: str) -> tuple[time | None, str | None]:
    if day not in _DAYS:
        return None, f"I only know the weekdays {', '.join(_DAYS[:-1])} and {_DAYS[-1]}."
    new_time = _parse_time(at)
    if new_time is None:
        return None, "I couldn't read that time. Use 24-hour HH:MM, like 14:00."
    if goal not in GOALS:
        return None, f"I don't know that goal. Try: {', '.join(GOALS)}."
    return new_time, None


def cmd_add_day(ctx: _Context, day: str, at: str, goal: str) -> str:
    """An extra class on one day of the coming week only (a temporary slot that ends on that week's Friday)."""
    data = _Data(ctx)
    new_time, error = _check_new_slot(day, at, goal)
    if error:
        return error
    if day in data.settings.slots:
        return f"{day} already has a class. Use move {day} HH:MM or goal {day} <goal> instead."
    this_week = current_week(ctx.now)
    week = this_week if slot_start(this_week, day, new_time) > ctx.now else target_week(ctx.now, data.settings)
    ctx.store.save_settings(replace(
        data.settings,
        slots={**data.settings.slots, day: new_time},
        slot_goals={**data.settings.slot_goals, day: goal},
        extra_days={**data.settings.extra_days, day: (week + timedelta(days=4)).isoformat()},
    ))
    if week != this_week and not any(p.week == week for p in data.picks):  # Sunday's run will plan it
        return f"Okay, {day} {_clock(new_time)} ({goal}) is added for next week. It will be in Sunday's picks."
    return _repick(ctx, week, [day])


def cmd_set_slot(ctx: _Context, day: str, at: str, goal: str) -> str:
    """Add or change a weekly slot for good."""
    data = _Data(ctx)
    new_time, error = _check_new_slot(day, at, goal)
    if error:
        return error
    ctx.store.save_settings(replace(
        data.settings,
        slots={**data.settings.slots, day: new_time},
        slot_goals={**data.settings.slot_goals, day: goal},
        extra_days={d: v for d, v in data.settings.extra_days.items() if d != day},
    ))
    text = f"{day} {_clock(new_time)} ({goal}) is now a weekly slot."
    week = target_week(ctx.now, data.settings)
    has_picks = any(p.week == week for p in data.picks)
    if has_picks and not any(p.week == week and p.slot == day for p in data.picks) \
            and slot_start(week, day, new_time) > ctx.now:
        text += "\n" + _repick(ctx, week, [day])
    return text


def _ignore_text(words: list[str]) -> str:
    if not words:
        return "No events are ignored now, so every event blocks your classes."
    return f"Events starting with {', '.join(words)}"


def cmd_ignore_events(ctx: _Context, words: list[str]) -> str:
    settings = ctx.store.load_settings()
    listed = list(settings.ignore_titles) + [w for w in (x.lower() for x in words) if w not in settings.ignore_titles]
    ctx.store.save_settings(replace(settings, ignore_titles=listed))
    return f"Okay. {_ignore_text(listed)} won't block your classes."


def cmd_unignore_events(ctx: _Context, words: list[str]) -> str:
    settings = ctx.store.load_settings()
    gone = [w.lower() for w in words]
    unknown = [w for w in gone if w not in settings.ignore_titles]
    listed = [w for w in settings.ignore_titles if w not in gone]
    ctx.store.save_settings(replace(settings, ignore_titles=listed))
    if unknown:
        return f"'{unknown[0]}' wasn't on the list. {_ignore_text(listed)} don't block your classes."
    return f"Okay. {_ignore_text(listed)} won't block your classes."


def cmd_remove_slot(ctx: _Context, day: str) -> str:
    data = _Data(ctx)
    if day not in data.settings.slots:
        return f"I don't have a {day} slot."
    if len(data.settings.slots) == 1:
        return f"You need at least one slot, so I can't remove {day}."
    ctx.store.save_settings(replace(
        data.settings,
        slots={d: t for d, t in data.settings.slots.items() if d != day},
        slot_goals={d: g for d, g in data.settings.slot_goals.items() if d != day},
        extra_days={d: v for d, v in data.settings.extra_days.items() if d != day},
    ))
    return f"Removed {day} from your weekly slots. This week's {day} class stays unless you say skip {day}."


def _this_week(ctx: _Context, data: _Data, slot: str) -> tuple[date | None, Pick | None, str | None]:
    if error := _slot_error(data.settings, slot):
        return None, None, error
    week = _active_week(data.picks, ctx.now)
    pick = next((p for p in data.picks if p.week == week and p.slot == slot), None)
    return week, pick, None


def cmd_more(ctx: _Context, slot: str) -> str:
    data = _Data(ctx)
    week, _, error = _this_week(ctx, data, slot)
    if error or week is None:
        return error or "There are no picks yet. Reply pick to make some."
    ranker, _ = _ranker(ctx, data.labels)
    current = [p for p in data.picks if p.week == week]
    found = alternatives(slot, week, data.classes_list, data.labels, data.settings, data.picks, ranker,
                         today=ctx.now.date(), current=current, cycle=data.cycle, favourites=data.favourites)
    if not found:
        return f"No other classes fit {slot}."
    ctx.store.save_offers(slot, week, [c.id for c in found])
    lines = [f"{i}. {c.title} ({c.mins} min, {messages.equipment_text(c, data.labels.get(c.id))})"
             for i, c in enumerate(found, 1)]
    return "\n".join([*lines, f"Reply with a number to swap {slot}."])


def _put(ctx: _Context, data: _Data, week: date, slot: str, c: AloClass, *, requested: bool) -> str:
    """Put class `c` in `slot`, keeping that slot's time when it has a pick, and updating the calendar."""
    old = next((p for p in data.picks if p.week == week and p.slot == slot), None)
    old_class = data.classes.get(old.class_id) if old and old.class_id else None
    if old and old.class_id and (old_class is None or c.mins <= old_class.mins):
        start = old.start
    elif old and old.class_id:  # a longer class (a long favourite, say) must not run into the next event
        start_of_week, end = _week_window(week)
        busy = _busy(ctx, data.settings, start_of_week, end, frozenset({old.event_id} - {""}))
        start = find_same_day(old.start, c.mins, busy)
    else:
        start_of_week, end = _week_window(week)
        busy = _busy(ctx, data.settings, start_of_week, end)
        preferred = slot_start(week, slot, data.settings.slots[slot])
        start = find_same_day(preferred, c.mins, busy)
    if start is None:  # nothing fits between 9:00 and 12:00: leave the slot as it was, and say so
        return messages.no_room(slot, c.title)
    new = Pick(week=week, slot=slot, start=start, class_id=c.id, requested=requested,
               jev_used=old.jev_used if old else True)
    new, failure = _place(ctx, data, old, new)
    return "\n".join([messages.updated([new], data.classes, data.labels), *([failure] if failure else [])])


def cmd_choose(ctx: _Context, slot: str, number: int) -> str:
    data = _Data(ctx)
    week, _, error = _this_week(ctx, data, slot)
    if error or week is None:
        return error or "There are no picks yet. Reply pick to make some."
    offered = ctx.store.load_offers(slot, week)
    if not offered:
        return f"I haven't offered any alternatives for {slot}. Reply more {slot} first."
    if not 1 <= number <= len(offered):
        return f"Pick a number from 1 to {len(offered)}."
    return _put(ctx, data, week, slot, data.classes[offered[number - 1]], requested=False)


def cmd_undo(ctx: _Context) -> str:
    data = _Data(ctx)
    week = _active_week(data.picks, ctx.now)
    mine = [p for p in data.picks if p.week == week]
    moved = [p for p in mine if p.prev_start]
    if moved:
        notes = []
        for p in _by_slot(moved):
            if p.event_id:
                ctx.calendar.move(p.event_id, p.prev_start, data.classes[p.class_id].mins)
            ctx.store.save_picks([replace(p, start=p.prev_start, prev_start=None, prev_event_id="")])
            notes.append(f"Put {p.slot} back to {p.prev_start.hour}:{p.prev_start.minute:02d}.")
        return "\n".join(notes)
    scheduled = [p for p in mine if p.status == "scheduled"]
    if not scheduled:
        return "Nothing to undo."
    for p in scheduled:
        if p.event_id:
            ctx.calendar.delete(p.event_id)
        ctx.store.save_picks([replace(p, status="proposed", event_id="")])
    return "Removed this week's classes from your calendar."


def cmd_skip(ctx: _Context, slot: str) -> str:
    data = _Data(ctx)
    week, pick, error = _this_week(ctx, data, slot)
    if error:
        return error
    if not pick or not pick.class_id:
        return f"You have no {slot} class this week."
    if pick.event_id:
        ctx.calendar.delete(pick.event_id)
    ctx.store.save_picks([replace(pick, status="skipped", event_id="")])
    return f"Skipped {slot}."


def _latest_started(data: _Data, slot: str, now: datetime) -> Pick | None:
    started = [p for p in data.picks if p.slot == slot and p.class_id and p.start <= now]
    return max(started, key=lambda p: p.start, default=None)


def cmd_skipped(ctx: _Context, slot: str) -> str:
    data = _Data(ctx)
    if error := _slot_error(data.settings, slot):
        return error
    pick = _latest_started(data, slot, ctx.now)
    if not pick:
        return f"I don't have a {slot} class that has happened yet."
    ctx.store.save_picks([replace(pick, status="skipped")])
    return f"Marked {slot} as skipped."


def cmd_feedback(ctx: _Context, slot: str, kind: str) -> str:
    data = _Data(ctx)
    if error := _slot_error(data.settings, slot):
        return error
    if kind not in _FEEDBACK:
        return f"Feedback can be: {', '.join(_FEEDBACK)}."
    pick = _latest_started(data, slot, ctx.now)
    if not pick:
        return f"I don't have a {slot} class to give feedback on yet."
    ctx.store.save_picks([replace(pick, feedback=kind)])
    step = {"too_hard": -_STRENGTH_STEP, "too_easy": _STRENGTH_STEP}.get(kind)
    if step is not None:
        low, high = _STRENGTH_RANGE
        strength = min(high, max(low, data.settings.preferred_strength + step))
        ctx.store.save_settings(replace(data.settings, preferred_strength=strength))
    return {
        "like": "Noted, I'll pick more like that.",
        "dislike": "Noted, I won't pick that class again.",
        "too_hard": "Noted, I'll lean lighter on strength work.",
        "too_easy": "Noted, I'll lean heavier on strength work.",
    }[kind]


def _class_from_words(ctx: _Context, data: _Data, what: str) -> tuple[AloClass | None, str | None]:
    """"Tue" means the last class that happened in that slot. Anything else is a title or an id."""
    day = _day(_day_arg(what))
    if day in data.settings.slots:
        pick = _latest_started(data, day, ctx.now)
        if not pick:
            return None, f"I don't have a {day} class that has happened yet."
        c = data.classes.get(pick.class_id)
        if c is None:
            return None, f"Your last {day} class is no longer on Alo."
        return c, None
    return _find_class(data, what)


def cmd_fav(ctx: _Context, what: str, note: str) -> str:
    data = _Data(ctx)
    c, problem = _class_from_words(ctx, data, what)
    if problem:
        return problem
    if c.id in data.favourites:
        if not note.strip():
            return f"{c.title} is already in your favourites."
        added = next(f.added for f in ctx.store.load_favourites() if f.class_id == c.id)
        ctx.store.save_favourite(Favourite(class_id=c.id, added=added, note=note.strip()))
        return f"Updated the note on {c.title}."
    ctx.store.save_favourite(Favourite(class_id=c.id, added=ctx.now.date(), note=note.strip()))
    return f"Added {c.title} to your favourites. I'll lean towards it when I pick."


def cmd_unfav(ctx: _Context, what: str) -> str:
    data = _Data(ctx)
    if what.strip() in data.favourites and what.strip() not in data.classes:  # a class that has left Alo
        ctx.store.remove_favourite(what.strip())
        return f"Removed class {what.strip()} from your favourites (it's no longer on Alo)."
    favs = [data.classes[i] for i in data.favourites if i in data.classes]
    day = _day(_day_arg(what))
    if day in data.settings.slots:
        c, problem = _class_from_words(ctx, data, what)
    else:  # a title or id, looked up among favourites only so "core" does not match the whole catalogue
        wanted = what.strip().casefold()
        exact = [f for f in favs if f.title.casefold().strip() == wanted or f.id == what.strip()]
        found = exact or [f for f in favs if wanted in f.title.casefold()]
        c, problem = (found[0], None) if len(found) == 1 else (
            (None, f"None of your favourites matches {what}.") if not found else
            (None, "Which one? " + "; ".join(f.title.strip() for f in found[:5])))
    if problem:
        return problem
    if not ctx.store.remove_favourite(c.id):
        return f"{c.title} wasn't in your favourites."
    return f"Removed {c.title} from your favourites."


def cmd_favs(ctx: _Context) -> str:
    data = _Data(ctx)
    favs = sorted(ctx.store.load_favourites(), key=lambda f: f.added, reverse=True)
    if not favs:
        return "No favourites yet. Say fav <class or day> to add one."
    lines = []
    for f in favs[:20]:
        c = data.classes.get(f.class_id)
        name = f"{c.title.strip()} ({c.mins} min)" if c else f"class {f.class_id} (no longer on Alo, unfav {f.class_id})"
        lines.append(f"* {name}" + (f" - {f.note}" if f.note else ""))
    more = f"\n(and {len(favs) - 20} more)" if len(favs) > 20 else ""
    return f"Your favourites ({len(favs)}):\n" + "\n".join(lines) + more


def _parse_time(text: str) -> time | None:
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return None


def cmd_move(ctx: _Context, slot: str, at: str, day: str | None, permanent: bool) -> str:
    data = _Data(ctx)
    week, pick, error = _this_week(ctx, data, slot)
    if error:
        return error
    new_time = _parse_time(at)
    if new_time is None:
        return "I couldn't read that time. Use 24-hour HH:MM, like 14:00."
    if day is not None and day not in _DAYS:
        return f"I only know the days {', '.join(_DAYS)}."
    if permanent and day is not None:
        return (f"Changing the day for good isn't supported yet. I can move it this week: "
                f"move {slot} {at} --day {day}")
    clock = f"{new_time.hour}:{new_time.minute:02d}"
    if permanent:
        ctx.store.save_settings(replace(data.settings, slots={**data.settings.slots, slot: new_time}))
    note = ""
    if pick and pick.class_id and pick.start >= ctx.now:
        target_day = day or pick.start.strftime("%a")
        new_start = datetime.combine(week + timedelta(days=_DAYS.index(target_day)), new_time, tzinfo=TZ)
        if pick.status == "scheduled" and pick.event_id:
            ctx.calendar.move(pick.event_id, new_start, data.classes[pick.class_id].mins)
        undo = {} if permanent else {"prev_start": pick.start, "prev_event_id": pick.event_id}
        ctx.store.save_picks([replace(pick, start=new_start, **undo)])
        note = f" This week it's {new_start:%a} {clock}."
    if permanent:
        return f"From now on {day or slot} is at {clock}.{note}"
    return f"Moved {slot} to {clock}." if not note else f"Moved {slot}.{note}"


def _find_class(data: _Data, text: str) -> tuple[AloClass | None, str | None]:
    wanted = text.strip().casefold()
    exact = [c for c in data.classes_list if c.title.casefold() == wanted or c.id == text]
    matches = exact or [c for c in data.classes_list if wanted in c.title.casefold()]
    if not matches:
        return None, f"I couldn't find a class called {text}."
    if len(matches) > 1:
        return None, "Which one? " + "; ".join(c.title for c in matches[:5])
    return matches[0], None


def _first_free_slot(data: _Data, week: date) -> str | None:
    mine = {p.slot: p for p in data.picks if p.week == week}
    for slot in sorted(data.settings.slots, key=_DAYS.index):
        if slot not in mine or mine[slot].status in ("proposed", "no_match", "skipped"):
            return slot
    return None


def cmd_repeat(ctx: _Context, what: str, on: str | None) -> str:
    data = _Data(ctx)
    week = _active_week(data.picks, ctx.now)
    if week is None:
        return "There are no picks yet. Reply pick to make some."
    if what in data.settings.slots:
        previous = _latest_started(data, what, ctx.now)
        if not previous:
            return f"I don't have a {what} class that has happened yet."
        c, problem = data.classes[previous.class_id], None
    else:
        c, problem = _find_class(data, what)
    if problem:
        return problem
    slot = on or _first_free_slot(data, week)
    if slot is None:
        return "Every slot this week is already booked. Say which to replace, e.g. repeat Mon --on Tue."
    if error := _slot_error(data.settings, slot):
        return error
    return _put(ctx, data, week, slot, c, requested=True)


def cmd_request_style(ctx: _Context, style: str, on: str | None) -> str:
    data = _Data(ctx)
    if style not in data.settings.styles_on_request:
        return f"I don't know that style. Try: {', '.join(sorted(data.settings.styles_on_request))}."
    week = _active_week(data.picks, ctx.now)
    if week is None:
        return "There are no picks yet. Reply pick to make some."
    slot = on or _first_free_slot(data, week) or sorted(data.settings.slots, key=_DAYS.index)[0]
    if error := _slot_error(data.settings, slot):
        return error
    return _repick(ctx, week, [slot], overrides={slot: style}, exclude_old=True)


def cmd_low_energy_today(ctx: _Context) -> str:
    data = _Data(ctx)
    week = _active_week(data.picks, ctx.now)
    today = next((p for p in data.picks if p.week == week and p.start.date() == ctx.now.date() and p.class_id
                  and p.status in ("proposed", "scheduled")), None)
    if today is None:
        return "You have no class today."
    return _repick(ctx, week, [today.slot], overrides={today.slot: "low energy"}, exclude_old=True,
                   prefer_same_focus=True)


def cmd_period_started(ctx: _Context, when: str | None) -> str:
    try:
        started = date.fromisoformat(when) if when else ctx.now.date()
    except ValueError:
        return "I couldn't read that date. Use YYYY-MM-DD, like 2026-10-03."
    ctx.store.add_cycle_start(started)
    data = _Data(ctx)
    week = _active_week(data.picks, ctx.now)
    days = data.settings.low_energy_days
    affected = [p.slot for p in _by_slot([p for p in data.picks if p.week == week and p.class_id
                                           and p.status in ("proposed", "scheduled") and p.start >= ctx.now
                                           and 0 <= (p.start.date() - started).days < days])]
    if not affected:
        return f"Got it. I'll keep picks gentle for {days} days from {started}."
    return f"Got it. Gentler picks for the next {days} days.\n" + _repick(
        ctx, week, affected, exclude_old=True, prefer_same_focus=True)


# ---------------------------------------------------------------- argument parsing

_DAY_WORDS = {"mon": "Mon", "monday": "Mon", "tue": "Tue", "tues": "Tue", "tuesday": "Tue", "wed": "Wed",
              "weds": "Wed", "wednesday": "Wed", "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thursday": "Thu",
              "fri": "Fri", "friday": "Fri", "all": "all"}


def _day_arg(text: str) -> str:
    """Days can be typed any way: thu, THU, Thursday. Anything else is left for the usual error message."""
    return _DAY_WORDS.get(text.strip().lower(), text)


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # a bad message from Georgia must get an answer, not a usage dump on stderr
        raise _UsageError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="weekly_picker")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sunday", "pick", "approve", "autoadd", "check-ran", "undo", "low-energy-today", "clash-check", "show"):
        sub.add_parser(name)
    fav = sub.add_parser("fav")
    fav.add_argument("what", nargs="+")
    fav.add_argument("--note", nargs="+", default=[])
    sub.add_parser("unfav").add_argument("what", nargs="+")
    sub.add_parser("favs")
    sub.add_parser("import-physio").add_argument("file", nargs="?")
    label = sub.add_parser("label")
    label.add_argument("--limit", type=int, default=None)
    for name in ("more", "skip", "skipped"):
        sub.add_parser(name).add_argument("slot", type=_day_arg)
    choose = sub.add_parser("choose")
    choose.add_argument("slot", type=_day_arg)
    choose.add_argument("number", type=int)
    for name in ("goal", "set-goal"):
        p = sub.add_parser(name)
        p.add_argument("slot", type=_day_arg)
        p.add_argument("goal", nargs="+")
    sub.add_parser("next-week").add_argument("text", nargs="+")
    for name in ("add-day", "set-slot"):
        p = sub.add_parser(name)
        p.add_argument("day", type=_day_arg)
        p.add_argument("time")
        p.add_argument("goal", nargs="+")
    sub.add_parser("remove-slot").add_argument("day", type=_day_arg)
    for name in ("ignore-events", "unignore-events"):
        sub.add_parser(name).add_argument("words", nargs="+")
    sub.add_parser("period-started").add_argument("date", nargs="?")
    feedback = sub.add_parser("feedback")
    feedback.add_argument("slot", type=_day_arg)
    feedback.add_argument("kind")
    move = sub.add_parser("move")
    move.add_argument("slot", type=_day_arg)
    move.add_argument("time")
    move.add_argument("--day", type=_day_arg)
    move.add_argument("--permanent", action="store_true")
    repeat = sub.add_parser("repeat")
    repeat.add_argument("what", nargs="+")
    repeat.add_argument("--on", type=_day_arg)
    style = sub.add_parser("request-style")
    style.add_argument("style")
    style.add_argument("--on", type=_day_arg)
    return parser


def main(argv: list[str], *, store=None, calendar=None, client=None, label_client=None,
         now: datetime | None = None) -> str:
    try:
        args = _parser().parse_args(argv)
    except _UsageError as e:
        return f"I couldn't understand that command ({e}). Try again, or say it another way."
    ctx = _Context(store, calendar, client, label_client, now or datetime.now(TZ))
    c = args.command
    for attr in ("slot", "day"):  # day names from replies are lowercase or full ("thu", "thursday")
        if getattr(args, attr, None):
            setattr(args, attr, _day(getattr(args, attr)))
    with open(LOCK_PATH, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # wait for any other command to finish; released when the file closes
        return _dispatch(ctx, c, args)


def _dispatch(ctx: _Context, c: str, args) -> str:
    simple = {"sunday": lambda: cmd_sunday(ctx, False), "pick": lambda: cmd_sunday(ctx, True),
              "approve": lambda: cmd_approve(ctx), "autoadd": lambda: cmd_autoadd(ctx),
              "check-ran": lambda: cmd_check_ran(ctx), "undo": lambda: cmd_undo(ctx),
              "low-energy-today": lambda: cmd_low_energy_today(ctx), "clash-check": lambda: cmd_clash_check(ctx),
              "show": lambda: cmd_show(ctx), "favs": lambda: cmd_favs(ctx)}
    if c in simple:
        return simple[c]()
    return {
        "label": lambda: cmd_label(ctx, args.limit),
        "import-physio": lambda: cmd_import_physio(ctx, args.file),
        "fav": lambda: cmd_fav(ctx, " ".join(args.what), " ".join(args.note)),
        "unfav": lambda: cmd_unfav(ctx, " ".join(args.what)),
        "more": lambda: cmd_more(ctx, args.slot),
        "choose": lambda: cmd_choose(ctx, args.slot, args.number),
        "skip": lambda: cmd_skip(ctx, args.slot),
        "skipped": lambda: cmd_skipped(ctx, args.slot),
        "goal": lambda: cmd_goal(ctx, args.slot, " ".join(args.goal).lower()),
        "set-goal": lambda: cmd_set_goal(ctx, args.slot, " ".join(args.goal).lower()),
        "next-week": lambda: cmd_next_week(ctx, " ".join(args.text)),
        "add-day": lambda: cmd_add_day(ctx, args.day, args.time, " ".join(args.goal).lower()),
        "set-slot": lambda: cmd_set_slot(ctx, args.day, args.time, " ".join(args.goal).lower()),
        "remove-slot": lambda: cmd_remove_slot(ctx, args.day),
        "ignore-events": lambda: cmd_ignore_events(ctx, args.words),
        "unignore-events": lambda: cmd_unignore_events(ctx, args.words),
        "period-started": lambda: cmd_period_started(ctx, args.date),
        "feedback": lambda: cmd_feedback(ctx, args.slot, args.kind.lower()),
        "move": lambda: cmd_move(ctx, args.slot, args.time, args.day, args.permanent),
        "repeat": lambda: cmd_repeat(ctx, _day_arg(" ".join(args.what)), args.on),
        "request-style": lambda: cmd_request_style(ctx, args.style, args.on),
    }[c]()
