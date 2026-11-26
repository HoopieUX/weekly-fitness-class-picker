from dataclasses import replace
from datetime import date, time

from weekly_picker.picker import alternatives, label_ranker, physio_bonus, plan_week
from tests.helpers import dt, lab, pick
from tests.world import WEEK


def constant_ranker(fit: float):
    return lambda goal, modifiers, candidates: {c.id: fit for c in candidates}


def test_one_pick_per_slot_with_slot_goals(world):
    picks = plan_week(**world.args())
    assert [p.slot for p in picks] == ["Mon", "Tue", "Wed"]
    assert [world.labels[p.class_id].main_goal for p in picks] == ["strength", "flexibility", "sculpt and tone"]
    assert all(p.status == "proposed" and p.week == WEEK for p in picks)
    assert [p.start for p in picks] == [dt(2026, 10, 12), dt(2026, 10, 13), dt(2026, 10, 14)]


def test_focus_and_instructor_differ_across_the_week(world):
    picks = plan_week(**world.args())
    assert len({world.focus_of(p) for p in picks}) == 3
    assert len({world.classes_by_id[p.class_id].instructor for p in picks}) == 3


def test_full_body_is_allowed_once_but_relaxed_when_nothing_else_fits(world):
    for goal in ("strength", "flexibility", "sculpt and tone"):
        world.keep_goal_focuses(goal, ("full body", "core"))
    prefers_full_body = lambda goal, mods, cands: {  # noqa: E731
        c.id: (0.95 if c.focus == "full body" else 0.5) for c in cands}
    picks = plan_week(**world.args(ranker=prefers_full_body))
    assert [world.focus_of(p) for p in picks[:2]] == ["full body", "core"]
    assert [p.status for p in picks] == ["proposed"] * 3  # Wednesday relaxes the focus rule rather than failing


def test_same_focus_everywhere_still_gives_three_picks(world):
    world.set_all_focus("legs")
    assert [p.status for p in plan_week(**world.args())] == ["proposed"] * 3


def test_empty_pool_relaxes_repeats_then_no_match(world):
    world.mark_goal_done_recently("strength")
    assert plan_week(**world.args())[0].status == "proposed"
    world.remove_goal("strength")
    mon = plan_week(**world.args())[0]
    assert mon.status == "no_match" and mon.class_id == "" and mon.start == dt(2026, 10, 12)


def test_clash_moves_same_day_to_the_nearest_free_time(world):
    world.busy.append((dt(2026, 10, 12, 9, 0), dt(2026, 10, 12, 10, 0)))
    assert plan_week(**world.args())[0].start == dt(2026, 10, 12, 10, 0)


def test_a_full_day_never_moves_the_class_to_another_day(world):
    world.busy_whole_day(2026, 10, 14)  # Wednesday
    wed = plan_week(**world.args())[2]
    assert wed.slot == "Wed" and wed.class_id == "" and wed.status == "no_time"


def test_two_picks_never_double_book_the_same_time(world):
    picks = plan_week(**world.args())
    assert len({p.start for p in picks}) == 3
    assert all(p.status == "proposed" for p in picks)


def test_low_energy_next_week_applies_to_every_slot(world):
    world.settings = replace(world.settings, next_week={"all": "low energy"})
    assert all(world.labels[p.class_id].low_energy >= 0.5 for p in plan_week(**world.args()))


def test_next_week_goal_replaces_one_slot_goal(world):
    world.settings = replace(world.settings, next_week={"Mon": "flexibility"})
    picks = plan_week(**world.args())
    assert world.labels[picks[0].class_id].main_goal == "flexibility"
    assert world.labels[picks[1].class_id].main_goal == "flexibility"  # Tue is flexibility anyway


def test_period_makes_slots_inside_the_window_low_energy(world):
    world.cycle = [date(2026, 10, 11)]
    picks = plan_week(**world.args())
    assert world.labels[picks[0].class_id].low_energy >= 0.5  # Mon, 1 day in
    assert world.labels[picks[1].class_id].low_energy >= 0.5  # Tue, 2 days in


def test_recent_repeat_rule_applies_and_replanning_the_same_week_does_not_block_itself(world):
    first = plan_week(**world.args())
    world.history = list(first)
    again = plan_week(**world.args())
    assert [p.class_id for p in again] == [p.class_id for p in first]


def test_liked_instructor_ranks_higher(world):
    liked = pick(class_id="str-core-Bea", feedback="like", status="done", start=dt(2026, 8, 3), week=date(2026, 8, 3))
    world.history = [liked]
    picks = plan_week(**world.args())
    assert world.classes_by_id[picks[0].class_id].instructor == "Bea"


def test_disliked_class_is_never_picked(world):
    first = plan_week(**world.args())[0].class_id
    world.history = [pick(class_id=first, feedback="dislike", status="skipped", start=dt(2026, 1, 5),
                          week=date(2026, 1, 5))]
    assert plan_week(**world.args())[0].class_id != first


def test_alternatives_are_distinct_and_skip_current_picks(world):
    current = plan_week(**world.args())
    alts = alternatives("Tue", n=5, **{k: v for k, v in world.args().items() if k not in ("busy",)}, current=current)
    assert len(alts) == 5 and len({a.id for a in alts}) == 5
    assert not {a.id for a in alts} & {p.class_id for p in current}
    assert all(world.labels[a.id].main_goal == "flexibility" for a in alts)


def test_label_ranker_scores_by_goal_probability(world):
    ranked = label_ranker(world.labels)("strength", [], world.classes[:2])
    assert ranked[world.classes[0].id] == 0.9


def test_only_and_keep_replan_just_the_missing_slot(world):
    full = plan_week(**world.args())
    mon, wed = full[0], full[2]
    [tue] = plan_week(**world.args(keep=[mon, wed], only=["Tue"]))
    assert tue.slot == "Tue" and tue.status == "proposed"
    assert world.focus_of(tue) not in {world.focus_of(mon), world.focus_of(wed)}
    taken = {world.classes_by_id[p.class_id].instructor for p in (mon, wed)}
    assert world.classes_by_id[tue.class_id].instructor not in taken


def test_kept_picks_still_block_their_time(world):
    wed_all_day = plan_week(**world.args())[2]
    world.busy_whole_day(2026, 10, 13)  # Tuesday full, so Tue wants Wed 10:00, where the kept Wed pick already sits
    [tue] = plan_week(**world.args(keep=[wed_all_day], only=["Tue"]))
    assert tue.start != wed_all_day.start


def test_exclude_ids_are_never_picked(world):
    first = plan_week(**world.args())[0].class_id
    assert plan_week(**world.args(exclude_ids=frozenset({first})))[0].class_id != first


def test_prefer_focus_wins_when_available(world):
    out = plan_week(**world.args(prefer_focus={"Mon": "legs"}))
    assert world.focus_of(out[0]) == "legs"


def test_a_calm_week_still_varies_instructors_even_though_every_focus_is_full_body(world):
    world.add_calm()
    world.settings = replace(world.settings, next_week={"all": "calm"})
    picks = plan_week(**world.args())
    assert [p.status for p in picks] == ["proposed"] * 3
    assert len({world.classes_by_id[p.class_id].instructor for p in picks}) == 3


def test_body_area_variety_still_applies_to_body_goals(world):
    world.add_calm()  # must not change anything for a normal week
    assert len({world.focus_of(p) for p in plan_week(**world.args())}) == 3


def test_physio_bonus_rewards_the_best_area_the_week_has_not_covered():
    l = lab(physio={"side_bend": 0.9, "balance": 0.4, "hinge": 0.1})
    assert physio_bonus(l) == 0.05 * 0.9
    assert physio_bonus(l, frozenset({"side_bend"})) == 0.05 * 0.4
    assert physio_bonus(lab()) == 0.0  # labelled before the physio questions: no nudge, no crash


def test_physio_work_tips_an_even_choice_and_the_week_spreads_across_areas(world):
    picks = plan_week(**world.args(ranker=constant_ranker(0.5)))
    others = [c.id for c in world.classes if c.id not in (picks[0].class_id, picks[1].class_id)]
    # give every class the same side-bend score, and one Tuesday-eligible other class balance too
    for cid in world.labels:
        world.labels[cid] = replace(world.labels[cid], physio={"side_bend": 0.9})
    tue_pool = [cid for cid in others if world.labels[cid].main_goal == "flexibility"]
    target = tue_pool[-1]
    world.labels[target] = replace(world.labels[target], physio={"side_bend": 0.9, "balance": 0.95})
    picks = plan_week(**world.args(ranker=constant_ranker(0.5)))
    assert picks[1].class_id == target


def test_classes_working_several_physio_areas_get_a_capped_variety_boost():
    one = lab(physio={"side_bend": 0.9})
    three = lab(physio={"side_bend": 0.9, "balance": 0.8, "spine_twist": 0.7})
    five = lab(physio={a: 0.9 for a in ("shoulder_stability", "hinge", "balance", "side_bend", "spine_twist")})
    assert round(physio_bonus(three) - physio_bonus(one), 6) == 0.03
    assert round(physio_bonus(five) - physio_bonus(one), 6) == 0.03  # variety is capped


def test_the_whole_physio_nudge_is_at_most_a_tenth():
    best_possible = lab(physio_feel=1.0, physio={a: 1.0 for a in ("shoulder_stability", "hinge", "balance",
                                                                  "side_bend", "spine_twist")})
    assert physio_bonus(best_possible) == 0.1


def test_feeling_like_physio_adds_a_nudge():
    assert round(physio_bonus(lab(physio_feel=1.0)) - physio_bonus(lab()), 6) == 0.02


def test_no_physio_next_week_turns_the_nudge_off(world):
    picks = plan_week(**world.args(ranker=constant_ranker(0.5)))
    tue = picks[1].class_id
    tue_pool = [cid for cid in world.labels if world.labels[cid].main_goal == "flexibility" and cid != tue]
    target = tue_pool[-1]
    world.labels[target] = replace(world.labels[target], physio={"balance": 0.95}, physio_feel=1.0)
    assert plan_week(**world.args(ranker=constant_ranker(0.5)))[1].class_id == target
    world.settings = replace(world.settings, next_week={"all": "no physio"})
    assert plan_week(**world.args(ranker=constant_ranker(0.5)))[1].class_id == tue


def test_a_strong_physio_class_makes_the_40_class_shortlist(world):
    from weekly_picker.picker import _Mods, _ranked
    from tests.helpers import cls
    classes = [cls(id=f"f{i:02d}", focus="core") for i in range(41)]
    labels = {c.id: lab(class_id=c.id, main_goal="flexibility", goal_probs={"flexibility": 0.95}) for c in classes}
    labels["f40"] = replace(labels["f40"], physio={"side_bend": 0.95}, physio_feel=0.6)  # 41st by id
    seen = []
    ranker = lambda goal, mods, cands: seen.extend(c.id for c in cands) or {c.id: 0.5 for c in cands}  # noqa: E731
    _ranked(classes, _Mods("flexibility"), classes, labels, world.settings, [], ranker, WEEK)
    assert "f40" in seen and len(seen) == 40


def test_a_favourite_wins_an_even_choice_and_makes_the_shortlist(world):
    from weekly_picker.picker import _Mods, _ranked
    from tests.helpers import cls
    classes = [cls(id=f"f{i:02d}", focus="core") for i in range(41)]
    labels = {c.id: lab(class_id=c.id, main_goal="flexibility", goal_probs={"flexibility": 0.95}) for c in classes}
    seen = []
    ranker = lambda goal, mods, cands: seen.extend(c.id for c in cands) or {c.id: 0.5 for c in cands}  # noqa: E731
    ranked = _ranked(classes, _Mods("flexibility"), classes, labels, world.settings, [], ranker, WEEK,
                     favourites=frozenset({"f40"}))  # 41st by id, so it would miss the 40 without the favourite
    assert "f40" in seen and ranked[0][1].id == "f40"


def test_a_favourite_can_be_longer_than_the_length_limit(world):
    from weekly_picker.picker import _pool
    from weekly_picker.picker import _Mods
    from tests.helpers import cls
    long_one, short_one = cls(id="long", mins=55, focus="core"), cls(id="short", mins=20, focus="core")
    labels = {c.id: lab(class_id=c.id, main_goal="flexibility", goal_probs={"flexibility": 0.95})
              for c in (long_one, short_one)}
    args = ([long_one, short_one], labels, world.settings, [], WEEK)
    kw = dict(ignore_repeats=False, exclude=set())
    assert [c.id for c in _pool(_Mods("flexibility"), *args, **kw)] == ["short"]
    assert {c.id for c in _pool(_Mods("flexibility"), *args, **kw, favourites=frozenset({"long"}))} == {"long", "short"}


def test_a_long_favourite_is_still_ruled_out_by_equipment(world):
    from weekly_picker.picker import _pool, _Mods
    from tests.helpers import cls
    c = cls(id="long", mins=55, focus="core", equipment=frozenset({"reformer"}))
    labels = {"long": lab(class_id="long", main_goal="flexibility", goal_probs={"flexibility": 0.95})}
    got = _pool(_Mods("flexibility"), [c], labels, world.settings, [], WEEK, ignore_repeats=False, exclude=set(),
                favourites=frozenset({"long"}))
    assert got == []


def test_a_long_favourite_that_will_not_fit_gives_way_to_the_next_class(world):
    for day in (13, 14, 15, 16):
        world.busy_whole_day(2026, 10, day)
    world.busy.append((dt(2026, 10, 12, 0, 0), dt(2026, 10, 12, 10, 0)))  # Monday: only 10:00 to 10:30 is free
    world.busy.append((dt(2026, 10, 12, 10, 30), dt(2026, 10, 12, 23, 59)))
    strength = [c for c in world.classes if world.labels[c.id].main_goal == "strength"]
    long_fav = replace(strength[0], mins=90)
    world.classes = [long_fav if c.id == long_fav.id else c for c in world.classes]
    picks = plan_week(**world.args(), favourites=frozenset({long_fav.id}))
    mon = picks[0]
    assert mon.status == "proposed" and mon.class_id != long_fav.id


def test_every_class_starts_after_9_and_ends_by_12(world):
    from datetime import timedelta
    for p in plan_week(**world.args()):
        c = world.classes_by_id[p.class_id]
        assert p.start.hour >= 9 and (p.start + timedelta(minutes=c.mins)).time() <= time(12, 0)


def test_a_week_with_no_free_morning_places_nothing_and_says_no_match(world):
    busy = [(dt(2026, 10, 12 + d, 9, 0), dt(2026, 10, 12 + d, 12, 0)) for d in range(5)]
    picks = plan_week(**world.args(busy=busy))
    assert [p.status for p in picks] == ["no_time"] * 3 and all(p.class_id == "" for p in picks)
