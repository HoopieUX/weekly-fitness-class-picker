from dataclasses import replace
from datetime import date, datetime, time

from weekly_picker.config import TZ
from weekly_picker.models import AloClass, Labels, Pick, Settings


def cls(**kw) -> AloClass:
    base = dict(
        id="c1", title="Class", mins=20, difficulty="beginner", intensity=2, style="yoga_vinyasa",
        categories=(), equipment=frozenset(), focus="full body", description="", url="https://x/c1",
        instructor=None,
    )
    base.update(kw)
    base["equipment"] = frozenset(base["equipment"])
    return AloClass(**base)


def lab(**kw) -> Labels:
    base = dict(
        class_id="c1", main_goal="strength", goal_probs={"strength": 0.8, "cardio": 0.05},
        strength=2.0, weight_needed="none", low_energy=0.3, focus=None,
    )
    base.update(kw)
    return Labels(**base)


def dt(y: int, m: int, d: int, h: int = 10, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=TZ)


def pick(**kw) -> Pick:
    base = dict(week=date(2026, 9, 21), slot="Mon", start=dt(2026, 9, 21), class_id="c1", status="done")
    base.update(kw)
    return Pick(**base)


def settings(**kw) -> Settings:
    return replace(Settings.default(), **kw)
