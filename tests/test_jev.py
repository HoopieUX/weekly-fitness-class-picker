from weekly_picker.jev import GOALS, PHYSIO_AREAS, class_state, label_questions, make_ranker, rank, to_labels
from tests.fakes import FakeSyncClient, fake_response
from tests.helpers import cls


def test_questions_skip_weight_and_focus_when_not_needed():
    q = label_questions(cls(equipment=frozenset(), focus="core"))
    assert set(q) == {"main_goal", "strength", "low_energy", "physio_feel", *PHYSIO_AREAS}


def test_questions_include_weight_and_focus_when_needed():
    q = label_questions(cls(equipment=frozenset({"weights"}), focus=None))
    assert set(q) == {"main_goal", "strength", "low_energy", "weight_needed", "focus", "physio_feel", *PHYSIO_AREAS}


def test_every_class_gets_a_yes_no_question_per_physio_area():
    q = label_questions(cls())
    assert list(PHYSIO_AREAS) == ["shoulder_stability", "hinge", "balance", "side_bend",
                                  "spine_twist"]
    assert all(set(q[a].criteria) == {"true", "false"} for a in PHYSIO_AREAS)


def test_to_labels_reads_physio_answers():
    l = to_labels(cls(id="7"), fake_response(main_goal={"mobility": 1.0}, strength=0.5, low_energy=0.8,
                                             side_bend=0.9, spine_twist=0.3))
    assert l.physio == {"side_bend": 0.9, "spine_twist": 0.3} and l.physio_feel == 0.0


def test_physio_feel_is_a_four_level_score_stored_as_0_to_1():
    assert len(label_questions(cls())["physio_feel"].criteria) == 4
    resp = fake_response(main_goal={"mobility": 1.0}, strength=0.5, low_energy=0.8, side_bend=0.9)
    resp.scores["physio_feel"] = type(resp.scores["strength"])(score=1.5, confidence=0.9)
    assert to_labels(cls(), resp).physio_feel == 0.5


def test_question_options():
    q = label_questions(cls(equipment=frozenset({"weights"}), focus=None))
    assert list(q["main_goal"].criteria) == GOALS
    assert len(q["strength"].criteria) == 4
    assert list(q["weight_needed"].criteria) == ["none", "light", "medium", "heavy"]
    assert list(q["focus"].criteria) == ["full body", "core", "legs", "arms", "booty"]


def test_cardio_and_sculpt_are_described_concretely():
    goals = label_questions(cls())["main_goal"].criteria
    assert "HIIT" in goals["cardio"] and "Pilates" in goals["sculpt and tone"]


def test_class_state_nests_under_class_key():
    s = class_state(cls(title="Quick Core", mins=9, equipment={"blocks"}, description="Burn.", focus="core"))
    assert s["class"]["title"] == "Quick Core" and s["class"]["mins"] == 9
    assert s["class"]["equipment"] == ["blocks"] and s["class"]["description"] == "Burn."


def test_to_labels_maps_fields():
    l = to_labels(cls(id="7"), fake_response(main_goal={"strength": 0.7, "cardio": 0.1}, strength=2.6, low_energy=0.2))
    assert (l.class_id, l.main_goal, l.weight_needed, l.goal_probs["cardio"]) == ("7", "strength", "none", 0.1)
    assert l.strength == 2.6 and l.low_energy == 0.2 and l.focus is None


def test_to_labels_reads_optional_answers_when_present():
    l = to_labels(cls(id="7"), fake_response(
        main_goal={"calm": 1.0}, strength=0.0, low_energy=0.9,
        weight_needed={"light": 0.8, "none": 0.2}, focus={"core": 0.6, "legs": 0.4},
    ))
    assert l.weight_needed == "light" and l.focus == "core"


def test_rank_asks_one_score_per_candidate_in_one_request():
    client = FakeSyncClient(scores={"a": 3.0, "b": 0.0})
    out = rank(client, "strength", ["low energy"], [cls(id="a"), cls(id="b")])
    assert client.calls == 1 and set(client.questions) == {"a", "b"}
    assert out == {"a": (1.0, 0.9), "b": (0.0, 0.9)}
    assert client.state["request"] == {"goal": "strength", "modifiers": ["low energy"]}
    assert set(client.state["classes"]) == {"ca", "cb"}  # keys are valid paths: `classes.ca`
    assert "`classes.ca`" in client.questions["a"].instructions


def test_rank_caps_candidates_at_forty():
    client = FakeSyncClient()
    out = rank(client, "strength", [], [cls(id=str(i)) for i in range(60)])
    assert len(out) == 40 and len(client.questions) == 40


def test_rank_with_no_candidates_makes_no_call():
    client = FakeSyncClient()
    assert rank(client, "strength", [], []) == {} and client.calls == 0


def test_make_ranker_binds_the_client():
    client = FakeSyncClient(scores={"a": 1.5})
    assert make_ranker(client)("calm", [], [cls(id="a")]) == {"a": (0.5, 0.9)}
