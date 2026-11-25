import pytest

from weekly_picker.labeller import label_all
from weekly_picker.store import InMemoryStore
from tests.fakes import FakeClient
from tests.helpers import cls, lab


def make_store(classes):
    return InMemoryStore(classes)


def test_label_all_resumes():
    classes = [cls(id="1"), cls(id="2"), cls(id="3")]
    store = make_store(classes)
    store.save_labels([lab(class_id="1", physio={"balance": 0.2})])
    client = FakeClient()
    n = label_all(classes, store, client)
    assert n == 2 and client.calls == 2 and set(store.load_labels()) == {"1", "2", "3"}


def test_label_all_keeps_saved_batches_when_interrupted():
    classes = [cls(id=str(i)) for i in range(5)]
    store = make_store(classes)
    client = FakeClient(fail_on_call=3)
    with pytest.raises(RuntimeError):
        label_all(classes, store, client, batch_size=2, concurrency=1)
    assert set(store.load_labels()) == {"0", "1"}


def test_label_all_limit_and_rerun_finishes_the_rest():
    classes = [cls(id=str(i)) for i in range(5)]
    store = make_store(classes)
    assert label_all(classes, store, FakeClient(), limit=2) == 2
    assert set(store.load_labels()) == {"0", "1"}
    assert label_all(classes, store, FakeClient()) == 3
    assert len(store.load_labels()) == 5


def test_label_all_sends_class_state_with_all_questions_in_one_call():
    classes = [cls(id="1", title="Only")]
    client = FakeClient()
    label_all(classes, make_store(classes), client)
    assert client.calls == 1 and client.states[0]["class"]["title"] == "Only"


def test_label_all_with_nothing_to_do_makes_no_calls():
    classes = [cls(id="1")]
    store = make_store(classes)
    store.save_labels([lab(class_id="1", physio={"balance": 0.2})])
    client = FakeClient()
    assert label_all(classes, store, client) == 0 and client.calls == 0


def test_label_all_relabels_classes_labelled_before_the_physio_questions():
    classes = [cls(id="1"), cls(id="2")]
    store = make_store(classes)
    store.save_labels([lab(class_id="1"), lab(class_id="2", physio={"hinge": 0.9})])
    client = FakeClient()
    assert label_all(classes, store, client) == 1 and client.calls == 1
    assert set(store.load_labels()["1"].physio) == {"shoulder_stability", "hinge", "balance",
                                                    "side_bend", "spine_twist"}


def test_classes_labelled_before_physio_keep_their_answers_and_get_only_physio_questions():
    classes = [cls(id="1")]
    store = make_store(classes)
    old = lab(class_id="1", main_goal="calm", goal_probs={"calm": 0.9}, strength=0.2, focus="core")
    store.save_labels([old])
    client = FakeClient()
    label_all(classes, store, client)
    new = store.load_labels()["1"]
    assert (new.main_goal, new.goal_probs, new.strength, new.focus) == ("calm", {"calm": 0.9}, 0.2, "core")
    assert new.physio and new.physio_feel == 0.5
    assert set(client.questions[0]) == {"physio_feel", "shoulder_stability", "hinge", "balance", "side_bend",
                                        "spine_twist"}
