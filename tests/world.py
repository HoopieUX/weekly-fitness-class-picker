"""A small synthetic catalogue: 3 goals x 4 focuses x 3 instructors = 36 classes, with known labels."""
from dataclasses import dataclass, field, replace
from datetime import date

from weekly_picker.models import AloClass, Labels, Pick, Settings
from weekly_picker.picker import label_ranker
from tests.helpers import cls, dt, lab

GOALS = ["strength", "flexibility", "sculpt and tone"]
FOCUSES = ["core", "legs", "arms", "full body"]
INSTRUCTORS = ["Ann", "Bea", "Cat"]
WEEK = date(2026, 10, 12)  # a Monday


def class_id(goal: str, focus: str, who: str) -> str:
    return f"{goal[:3]}-{focus.replace(' ', '')}-{who}"


@dataclass
class World:
    classes: list[AloClass] = field(default_factory=list)
    labels: dict[str, Labels] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings.default)
    history: list[Pick] = field(default_factory=list)
    busy: list = field(default_factory=list)
    cycle: list[date] = field(default_factory=list)
    ranker: object = None

    def __post_init__(self):
        for goal in GOALS:
            for focus in FOCUSES:
                for who in INSTRUCTORS:
                    cid = class_id(goal, focus, who)
                    self.classes.append(cls(id=cid, title=cid, focus=focus, instructor=who))
                    self.labels[cid] = lab(
                        class_id=cid, main_goal=goal, goal_probs={goal: 0.9, "other": 0.1},
                        strength=2.0 if goal == "strength" else 0.5,
                        low_energy=0.8 if who == "Cat" else 0.3,
                    )

    @property
    def classes_by_id(self):
        return {c.id: c for c in self.classes}

    def args(self, **over):
        base = dict(
            week=WEEK, classes=self.classes, labels=self.labels, settings=self.settings, history=self.history,
            busy=self.busy, ranker=self.ranker or label_ranker(self.labels), today=date(2026, 10, 11),
            cycle=self.cycle,
        )
        base.update(over)
        return base

    def focus_of(self, p: Pick) -> str:
        return self.classes_by_id[p.class_id].focus

    def set_all_focus(self, focus: str):
        self.classes = [replace(c, focus=focus) for c in self.classes]

    def keep_goal_focuses(self, goal: str, focuses: tuple[str, ...]):
        self.classes = [c for c in self.classes if not c.id.startswith(goal[:3]) or c.focus in focuses]

    def remove_goal(self, goal: str):
        self.classes = [c for c in self.classes if not c.id.startswith(goal[:3])]

    def mark_goal_done_recently(self, goal: str):
        for i, c in enumerate(c for c in self.classes if c.id.startswith(goal[:3])):
            self.history.append(Pick(week=date(2026, 10, 5), slot="Mon", start=dt(2026, 10, 5), class_id=c.id,
                                     status="done"))

    def add_calm(self):
        """Six calm classes, all 'full body' like most of Jev's guesses for meditation: two instructors repeat."""
        for i, who in enumerate(["Ann", "Ann", "Bea", "Bea", "Cat", "Cat"]):
            cid = f"cal-{i}-{who}"
            self.classes.append(cls(id=cid, title=cid, focus="full body", instructor=who, style="mindfulness_meditation"))
            self.labels[cid] = lab(class_id=cid, main_goal="calm", goal_probs={"calm": 0.95, "other": 0.05},
                                   strength=0.0, low_energy=0.95)

    def busy_whole_day(self, y: int, m: int, d: int):
        self.busy.append((dt(y, m, d, 7, 0), dt(y, m, d, 21, 0)))
