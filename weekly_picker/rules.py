import re
from datetime import date

from weekly_picker.config import CARDIO_THRESHOLD, REPEAT_DAYS
from weekly_picker.models import AloClass, Labels, Pick, Settings

_COUNTS_AS_DONE = {"done", "scheduled"}
# Partner classes say so in the title ("Partner Plank", "...for Two", "Duo", "Buddy Up") or the description
# ("partner workout", "grab a partner"). "A partner if you'd like" and talks about relationships do not count.
_PARTNER_TITLE = re.compile(r"\b(partner|partners|for two|duo|buddy|buddies)\b", re.I)
_PARTNER_TEXT = re.compile(
    r"\b(partner (workout|class|session|practice|stretch|flow|sweat)|grab (a|and) (partner|friend|buddy)"
    r"|bring a (friend|partner)|with a buddy|(workout|class|session|practice|flow|sweat|travel) for two)\b", re.I)


def _style_allowed(style: str, settings: Settings, requested_styles: frozenset[str]) -> bool:
    if style in settings.styles_out:
        return False
    if not style.startswith("skills"):
        return True
    if style in settings.styles_in:
        return True
    return style in settings.styles_on_request and style in requested_styles


def reasons_excluded(
    c: AloClass,
    labels: Labels | None,
    settings: Settings,
    history: list[Pick],
    today: date,
    *,
    requested_ids: frozenset[str] = frozenset(),
    requested_styles: frozenset[str] = frozenset(),
    allow_cardio: bool = False,
    ignore_repeats: bool = False,
    skip_length: bool = False,
) -> list[str]:
    reasons: list[str] = []
    if not skip_length and not settings.min_mins <= c.mins <= settings.max_mins:
        reasons.append("length")
    if not c.equipment <= settings.equipment_owned:
        reasons.append("equipment")
    if not _style_allowed(c.style, settings, requested_styles):
        reasons.append("style")
    if _PARTNER_TITLE.search(c.title) or _PARTNER_TEXT.search(c.description):
        reasons.append("partner")
    if labels is None:
        reasons.append("unlabelled")
    else:
        if not allow_cardio and labels.goal_probs.get("cardio", 0.0) >= CARDIO_THRESHOLD:
            reasons.append("cardio")
        if labels.weight_needed == "heavy":
            reasons.append("heavy_weights")
    mine = [p for p in history if p.class_id == c.id]
    if any(p.feedback == "dislike" for p in mine):
        reasons.append("disliked")
    if not ignore_repeats and c.id not in requested_ids:
        if any(p.status in _COUNTS_AS_DONE and (today - p.start.date()).days < REPEAT_DAYS for p in mine):
            reasons.append("recent_repeat")
    return reasons
