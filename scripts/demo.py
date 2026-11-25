"""Plan one week from the sample data. No Google account and no Jev key needed.

Usage: python scripts/demo.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weekly_picker.sample import load_sample  # noqa: E402
from weekly_picker.picker import label_ranker, plan_week  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "sample"


def run_demo(sample_dir: Path, week: date, today: date) -> str:
    store = load_sample(sample_dir)
    classes, labels, settings = store.load_classes(), store.load_labels(), store.load_settings()
    by_id = {c.id: c for c in classes}
    picks = plan_week(
        week, classes, labels, settings, store.load_picks(), [], label_ranker(labels), today=today, jev_used=False,
        cycle=store.load_cycle(), favourites=frozenset(f.class_id for f in store.load_favourites()),
    )
    lines = [f"Week of {week:%d/%m/%Y}", ""]
    for p in picks:
        if not p.class_id:
            lines.append(f"{p.slot}  no_match")
            continue
        c, label = by_id[p.class_id], labels[p.class_id]
        lines.append(f"{p.slot}  {p.start:%H:%M}  {c.title} ({c.mins} min)  "
                     f"{label.main_goal}, {label.goal_probs.get(label.main_goal, 0):.0%} sure")
    lines += ["", "Ranked from Jev's saved labels. The live version asks Jev each week."]
    return "\n".join(lines)


def main() -> None:
    today = date.today()
    week = today + timedelta(days=(7 - today.weekday()) % 7 or 7)  # the next Monday
    print(run_demo(SAMPLE, week, today))


if __name__ == "__main__":
    main()
