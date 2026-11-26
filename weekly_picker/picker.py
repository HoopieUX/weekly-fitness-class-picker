"""Weekly picking: filter with plain rules, rank with Jev, balance the week, place each class in the calendar."""
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Callable, Sequence

from weekly_picker.config import PLACE_PREFERRED
from weekly_picker.jev import GOALS, MAX_CANDIDATES
from weekly_picker.models import AloClass, Labels, Pick, Settings
from weekly_picker.rules import reasons_excluded
from weekly_picker.timeslots import place_on_day, slot_start

Ranker = Callable[[str, list[str], list[AloClass]], dict[str, float]]
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
_LOW_ENERGY = 0.5
_BODY_GOALS = {"strength", "sculpt and tone", "flexibility", "mobility", "cardio"}  # "body area" means little for calm
_GOAL_MATCH = 0.3
# The physio nudge. Together these add at most 0.1, a tiebreaker next to Jev's 0..1 fit score.
_PHYSIO_BONUS = 0.05  # times how sure Jev is the class works the best physio area the week has not covered yet
_PHYSIO_HIT = 0.5  # a class "covers" a physio area when Jev is at least this sure it works it
_VARIETY_STEP = 0.02  # per extra physio area a class works, beyond the first
_VARIETY_CAP = 0.03
_FEEL_BONUS = 0.02  # for a class that feels fully like a physio session
_PHYSIO_CAP = 0.1
_FAVOURITE_BONUS = 0.15  # same weight as a liked class or instructor


def physio_bonus(label: Labels, covered: frozenset[str] = frozenset()) -> float:
    """Reward the physio area this class works best (only areas the week has not covered yet), classes that
    work several areas at once, and classes that feel like a physio session."""
    open_areas = [p for a, p in label.physio.items() if a not in covered]
    best = _PHYSIO_BONUS * max(open_areas, default=0.0)
    variety = min(_VARIETY_STEP * max(len(physio_hits(label)) - 1, 0), _VARIETY_CAP)
    return min(best + variety + _FEEL_BONUS * label.physio_feel, _PHYSIO_CAP)


def physio_hits(label: Labels) -> set[str]:
    return {a for a, p in label.physio.items() if p >= _PHYSIO_HIT}


def label_ranker(labels: dict[str, Labels]) -> Ranker:
    """Rank from the labels Jev saved: how likely each class is to serve the goal."""
    return lambda goal, modifiers, candidates: {c.id: labels[c.id].goal_probs.get(goal, 0.0) for c in candidates}


@dataclass(frozen=True)
class _Mods:
    goal: str
    low_energy: bool = False
    longer: bool = False
    allow_cardio: bool = False
    styles: frozenset[str] = frozenset()
    physio: bool = True  # "no physio" turns the physio nudge off

    @property
    def texts(self) -> list[str]:
        return (["low energy"] if self.low_energy else []) + (["longer"] if self.longer else [])


def _mods(settings: Settings, slot: str, slot_date: date, cycle: Sequence[date]) -> _Mods:
    goal, low, longer, cardio, styles, physio = settings.slot_goals[slot], False, False, False, set(), True
    for key in ("all", slot):
        for text in (t.strip().lower() for t in settings.next_week.get(key, "").split(",")):
            if text == "low energy":
                low = True
            elif text == "longer":
                longer = True
            elif text == "no physio":
                physio = False
            elif text in GOALS:
                goal, cardio = text, cardio or text == "cardio"
            elif text in settings.styles_on_request:
                styles.add(text)
    if any(0 <= (slot_date - start).days < settings.low_energy_days for start in cycle):
        low = True
    return _Mods(goal, low, longer, cardio, frozenset(styles), physio)


def _focus(c: AloClass, labels: dict[str, Labels]) -> str | None:
    return c.focus or labels[c.id].focus


focus_of = _focus


def _pool(mods, classes, labels, settings, history, today, *, ignore_repeats, exclude,
          favourites=frozenset()) -> list[AloClass]:
    """Classes that pass the plain rules. A favourite ignores the length limit: favourites can be long."""
    effective = replace(settings, max_mins=45) if mods.longer else settings
    pool = []
    for c in classes:
        label = labels.get(c.id)
        if c.id in exclude:
            continue
        if reasons_excluded(c, label, effective, history, today, requested_styles=mods.styles,
                            allow_cardio=mods.allow_cardio, ignore_repeats=ignore_repeats,
                            skip_length=c.id in favourites):
            continue
        if mods.low_energy and label.low_energy < _LOW_ENERGY:
            continue
        if mods.styles and c.style not in mods.styles:  # a requested style means "pick one of those"
            continue
        wanted = c.style in mods.styles or label.main_goal == mods.goal or label.goal_probs.get(mods.goal, 0.0) >= _GOAL_MATCH
        if wanted:
            pool.append(c)
    return pool


def _ranked(pool, mods, classes, labels, settings, history, ranker, today, covered=frozenset(),
            favourites=frozenset()):
    def physio(c):
        return physio_bonus(labels[c.id], covered) if mods.physio else 0.0

    def favourite(c):
        return _FAVOURITE_BONUS if c.id in favourites else 0.0

    # the shortlist: best goal match first, with the physio nudge so strong physio classes make the cut
    pool = sorted(pool, key=lambda c: (-(labels[c.id].goal_probs.get(mods.goal, 0.0) + physio(c) + favourite(c)), c.id))
    pool = pool[:MAX_CANDIDATES]
    if not pool:
        return []
    fits = ranker(mods.goal, mods.texts, pool)
    by_id = {c.id: c for c in classes}
    liked = [p for p in history if p.feedback == "like" and p.class_id in by_id]
    liked_ids = {p.class_id for p in liked}
    liked_instructors = {by_id[p.class_id].instructor for p in liked} - {None}
    last_done: dict[str, date] = {}
    for p in history:
        if p.status in ("done", "scheduled") and p.class_id in by_id and p.class_id in labels:
            f = _focus(by_id[p.class_id], labels)
            last_done[f] = max(last_done.get(f, date.min), p.start.date())
    scored = []
    for c in pool:
        score = fits.get(c.id, 0.0)
        liked = 0.15 if c.id in liked_ids or c.instructor in liked_instructors else 0.0
        score += max(liked, favourite(c))  # liked and favourite do not stack, so the day's goal stays in charge
        seen = last_done.get(_focus(c, labels))
        score += 0.05 * (1.0 if seen is None else min((today - seen).days, 28) / 28)
        score += physio(c)
        if mods.goal == "strength":
            score -= 0.1 * abs(labels[c.id].strength - settings.preferred_strength)
        scored.append((score, c))
    scored.sort(key=lambda t: (-t[0], t[1].id))
    return scored


def plan_week(
    week: date, classes: list[AloClass], labels: dict[str, Labels], settings: Settings, history: list[Pick],
    busy, ranker: Ranker, *, today: date, cycle: Sequence[date] = (),
    keep: Sequence[Pick] = (), only: Sequence[str] | None = None, exclude_ids: frozenset[str] = frozenset(),
    prefer_focus: dict[str, str] | None = None, favourites: frozenset[str] = frozenset(),
) -> list[Pick]:
    """One new Pick per slot, in weekday order. `week` is the Monday. Slots with nothing usable become `no_match`;
    slots where classes fit the rules but none fits the 09:00 to 12:00 window on that day become `no_time`.

    To re-pick part of a week: `keep` the picks that stay (their focus, instructor, class and time still count),
    and list the slots to plan in `only`. `exclude_ids` are never picked; `prefer_focus` maps slot -> focus to try first.
    """
    history = [p for p in history if p.week != week]
    by_id = {c.id: c for c in classes}
    prefer_focus = prefer_focus or {}
    picks: list[Pick] = []
    placed: list[tuple] = []
    used_focus: set[str | None] = set()
    used_instructors: set[str] = set()
    used_ids: set[str] = set(exclude_ids)
    covered: set[str] = set()  # physio areas this week's picks already work
    kept_slots = {k.slot for k in keep if k.class_id}
    for k in keep:
        if k.class_id:
            kc = by_id[k.class_id]
            placed.append((k.start, k.start + timedelta(minutes=kc.mins)))
            used_focus.add(_focus(kc, labels))
            used_ids.add(k.class_id)
            if k.class_id in labels:
                covered |= physio_hits(labels[k.class_id])
            if kc.instructor:
                used_instructors.add(kc.instructor)
    for slot in sorted(settings.slots, key=_DAYS.index):
        if slot in kept_slots or (only is not None and slot not in only):
            continue
        preferred = slot_start(week, slot, PLACE_PREFERRED)
        mods = _mods(settings, slot, preferred.date(), cycle)
        chosen, had_candidate = None, False
        for level in (0, 1, 2):  # 0 = all rules, 1 = allow repeats, 2 = also relax focus and instructor variety
            pool = _pool(mods, classes, labels, settings, history, today, ignore_repeats=level >= 1, exclude=used_ids,
                          favourites=favourites)
            ranked = _ranked(pool, mods, classes, labels, settings, history, ranker, today, frozenset(covered),
                             favourites)
            if slot in prefer_focus:
                ranked.sort(key=lambda t: _focus(t[1], labels) != prefer_focus[slot])  # stable: keeps the score order
            for _, c in ranked:
                same_area = mods.goal in _BODY_GOALS and _focus(c, labels) in used_focus
                if level < 2 and (same_area or (c.instructor and c.instructor in used_instructors)):
                    continue
                had_candidate = True
                start = place_on_day(preferred.date(), c.mins, list(busy) + placed)
                if start is None:  # no free time for this one in the window (a long favourite, say): try the next
                    continue
                chosen = (c, start)
                break
            if chosen:
                break
        if not chosen:
            picks.append(Pick(week=week, slot=slot, start=preferred, class_id="",
                              status="no_time" if had_candidate else "no_match"))
            continue
        c, start = chosen
        placed.append((start, start + timedelta(minutes=c.mins)))
        used_focus.add(_focus(c, labels))
        used_ids.add(c.id)
        covered |= physio_hits(labels[c.id])
        if c.instructor:
            used_instructors.add(c.instructor)
        picks.append(Pick(week=week, slot=slot, start=start, class_id=c.id))
    return picks


def alternatives(
    slot: str, week: date, classes: list[AloClass], labels: dict[str, Labels], settings: Settings,
    history: list[Pick], ranker: Ranker, *, today: date, current: Sequence[Pick] = (), cycle: Sequence[date] = (),
    n: int = 5, favourites: frozenset[str] = frozenset(),
) -> list[AloClass]:
    """The best `n` other classes for one slot, same pool and ranking as plan_week, skipping this week's picks."""
    history = [p for p in history if p.week != week]
    mods = _mods(settings, slot, week + timedelta(days=_DAYS.index(slot)), cycle)
    exclude = {p.class_id for p in current if p.class_id}
    covered = frozenset().union(*(physio_hits(labels[p.class_id]) for p in current
                                  if p.class_id and p.slot != slot and p.class_id in labels))
    for ignore_repeats in (False, True):
        pool = _pool(mods, classes, labels, settings, history, today, ignore_repeats=ignore_repeats, exclude=exclude,
                      favourites=favourites)
        ranked = _ranked(pool, mods, classes, labels, settings, history, ranker, today, covered, favourites)
        if len(ranked) >= n:
            break
    return [c for _, c in ranked[:n]]
