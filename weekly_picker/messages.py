"""All chat copy. Plain text, one class per line."""
from weekly_picker.models import AloClass, Labels, Pick

_SHORT = {"yoga strap": "strap", "resistance bands": "bands", "pilates ball": "ball"}


def equipment_text(c: AloClass, label: Labels | None) -> str:
    if label and "weights" in c.equipment and label.weight_needed in ("light", "medium"):
        return f"{label.weight_needed} weights"
    items = sorted(c.equipment)
    return _SHORT.get(items[0], items[0]) if items else "no equipment"


def _clock(p: Pick) -> str:
    return f"{p.start.hour}:{p.start.minute:02d}"


def _line(p: Pick, classes: dict[str, AloClass], labels: dict[str, Labels]) -> str:
    if p.status == "no_match" or not p.class_id:
        return f"* {p.slot}: nothing placed this week (no match, or no free time between 9:00 and 12:00), reply more {p.slot}"
    c = classes[p.class_id]
    day = p.start.strftime("%a")
    text = f"* {day} {_clock(p)}: {c.title} ({c.mins} min, {equipment_text(c, labels.get(c.id))})"
    if p.less_sure:
        text += " (less sure)"
    if day != p.slot:
        text += f" (moved from {p.slot})"
    return text


def _mark(p: Pick) -> str:
    return {"skipped": "✗", "no_match": "-", "proposed": "-"}.get(p.status, "✓")


def sunday(last_week: list[Pick], picks: list[Pick], classes: dict[str, AloClass], labels: dict[str, Labels],
           jev_used: bool) -> str:
    slots = [p.slot for p in picks]
    parts = []
    if last_week:
        marks = " ".join(f"{p.slot} {_mark(p)}" for p in last_week)
        example = slots[1] if len(slots) > 1 else slots[0]
        parts.append(f"Did you do all of last week's classes? {marks}\n"
                     f'If you missed one, reply "skipped {example}". No reply means you did them all.')
    parts.append("\n".join(_line(p, classes, labels) for p in picks))
    parts.append(f"Reply ok, or more {' / '.join(slots)} for alternatives")
    if not jev_used:
        parts.append("Picked without Jev this week.")
    return "\n\n".join(parts)


def added(picks: list[Pick], classes: dict[str, AloClass], labels: dict[str, Labels]) -> str:
    return "Added to your calendar:\n" + "\n".join(_line(p, classes, labels) for p in picks)


def updated(picks: list[Pick], classes: dict[str, AloClass], labels: dict[str, Labels]) -> str:
    return "Updated:\n" + "\n".join(_line(p, classes, labels) for p in picks)


def _clock12(p_start) -> str:
    hour = p_start.hour % 12 or 12
    suffix = "am" if p_start.hour < 12 else "pm"
    return f"{hour}{suffix}" if p_start.minute == 0 else f"{hour}:{p_start.minute:02d}{suffix}"


def moved(slot: str, new_start, clash_title: str) -> str:
    day = new_start.strftime("%a")
    where = _clock12(new_start) + (f" on {day}" if day != slot else "")
    return f"{slot} moved to {where} (clashes with {clash_title}). Reply undo to put it back."


def no_room(slot: str, title: str) -> str:
    return (f"I couldn't fit {title} on {slot}: there is no free time between 9:00 and 12:00. "
            f"I've left {slot} as it was. Reply move {slot} HH:MM to choose a time yourself.")


def could_not_move(slot: str, clash_title: str) -> str:
    return (f"{slot} clashes with {clash_title} and I couldn't find another time this week. "
            f"Reply move {slot} HH:MM to choose one.")


def autoadded() -> str:
    return "Added this week's classes, reply undo to remove."


def not_previewed() -> str:
    return ("I haven't added this week's classes because I can't confirm the preview reached you. "
            "Reply show to see them, then ok to add them.")


def not_run() -> str:
    return "This week's classes weren't picked yet. Reply pick to run it now."


def save_failed(c: AloClass) -> str:
    return f"Couldn't save {c.title} to your calendar: {c.url}"
