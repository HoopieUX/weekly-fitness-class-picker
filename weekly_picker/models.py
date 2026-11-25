from dataclasses import dataclass, field
from datetime import date, datetime, time


@dataclass(frozen=True)
class AloClass:
    id: str
    title: str
    mins: int
    difficulty: str
    intensity: int | None
    style: str
    categories: tuple[str, ...]
    equipment: frozenset[str]
    focus: str | None
    description: str
    url: str
    instructor: str | None = None


@dataclass(frozen=True)
class Labels:
    class_id: str
    main_goal: str
    goal_probs: dict[str, float]
    strength: float
    weight_needed: str
    low_energy: float
    focus: str | None = None
    physio: dict[str, float] = field(default_factory=dict)  # physio area -> probability the class works it
    physio_feel: float = 0.0  # 0..1, how much the class feels like a physio session


@dataclass(frozen=True)
class Favourite:
    """A class Georgia likes and wants more of. Logged by chat, nothing to do with a week's picks."""
    class_id: str
    added: date
    note: str = ""


@dataclass(frozen=True)
class Pick:
    week: date  # the Monday of the week
    slot: str  # "Mon" / "Tue" / "Wed"
    start: datetime  # timezone-aware
    class_id: str
    status: str = "proposed"  # proposed / scheduled / done / skipped / no_match
    feedback: str = ""  # "" / like / dislike / too_hard / too_easy
    event_id: str = ""
    less_sure: bool = False
    jev_used: bool = True
    requested: bool = False
    prev_start: datetime | None = None
    prev_event_id: str = ""


OWNED_EQUIPMENT = frozenset({
    "blocks", "weights", "ankle weights", "yoga strap", "chair", "pilates ball",
    "bolster", "resistance bands", "wall", "blanket", "towel", "pillow", "mat", "socks",
})


@dataclass(frozen=True)
class Settings:
    slots: dict[str, time]
    slot_goals: dict[str, str]
    min_mins: int
    max_mins: int
    equipment_owned: frozenset[str]
    styles_in: frozenset[str]  # skill styles allowed by default; every non-skill style is allowed implicitly
    styles_on_request: frozenset[str]
    styles_out: frozenset[str]
    low_energy_days: int
    preferred_strength: float
    next_week: dict[str, str] = field(default_factory=dict)
    extra_days: dict[str, str] = field(default_factory=dict)  # temporary slots: day -> last date they exist
    # calendar events whose title starts with one of these words are reminders, so they never block a class
    ignore_titles: list[str] = field(default_factory=lambda: ["message", "remind"])

    @staticmethod
    def default() -> "Settings":
        return Settings(
            slots={"Mon": time(10, 0), "Tue": time(10, 0), "Wed": time(10, 0)},
            slot_goals={"Mon": "strength", "Tue": "flexibility", "Wed": "sculpt and tone"},
            min_mins=10,
            max_mins=30,
            equipment_owned=OWNED_EQUIPMENT,
            styles_in=frozenset({"skills_flexibility", "skills_mobility"}),
            styles_on_request=frozenset({
                "skills_inversions", "skills_arm balances", "skills_backbends",
                "skills_yoga poses", "skills",
            }),
            styles_out=frozenset({"skills_how to teach"}),
            low_energy_days=3,
            preferred_strength=2.0,
        )
