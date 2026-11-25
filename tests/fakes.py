from types import SimpleNamespace

from typesafe_sdk import Choice, Noul, Score


def _choice(probs: dict[str, float]):
    return SimpleNamespace(choice=max(probs, key=probs.get), probabilities=probs, confidence=0.9)


def fake_response(**answers):
    """Build a response with exactly these answers: dict -> choice probabilities, float -> score or noul."""
    choices, scores, nouls = {}, {}, {}
    for name, value in answers.items():
        if isinstance(value, dict):
            choices[name] = _choice(value)
        elif name in ("strength", "physio_feel"):
            scores[name] = SimpleNamespace(score=value, confidence=0.9)
        else:
            nouls[name] = SimpleNamespace(noul=value)
    return SimpleNamespace(choices=choices, scores=scores, nouls=nouls)


def response_for(questions):
    """A plausible answer for every question that was asked."""
    answers = {}
    for name, q in questions.items():
        if isinstance(q, Choice):
            options = list(q.criteria)
            answers[name] = {options[0]: 0.7, **{o: 0.3 / max(len(options) - 1, 1) for o in options[1:]}}
        elif isinstance(q, Score):
            answers[name] = 1.5
        elif isinstance(q, Noul):
            answers[name] = 0.4
    return fake_response(**answers)


class FakeClient:
    def __init__(self, fail_on_call: int | None = None):
        self.calls, self.fail_on_call, self.states, self.questions = 0, fail_on_call, [], []

    async def system_one(self, state, questions):
        self.calls += 1
        self.states.append(state)
        self.questions.append(questions)
        if self.fail_on_call == self.calls:
            raise RuntimeError("boom")
        return response_for(questions)


class FakeSyncClient:
    """Sync stand-in for TypeSafeClient: every Score question gets `scores[id]` (default 1.5)."""

    def __init__(self, scores=None, confidence=0.9, fail=False):
        self.calls, self.scores, self.confidence, self.fail = 0, scores or {}, confidence, fail
        self.state = self.questions = None

    def system_one(self, state, questions):
        self.calls += 1
        if self.fail:
            raise RuntimeError("TypeSafe is down")
        self.state, self.questions = state, questions
        out = {name: SimpleNamespace(score=self.scores.get(name, 1.5), confidence=self.confidence)
               for name in questions}
        return SimpleNamespace(choices={}, scores=out, nouls={})
