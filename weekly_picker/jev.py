"""Jev (TypeSafe) labels each class once. Jev never talks to Georgia; code reads its saved answers."""
from dataclasses import replace

from typesafe_sdk import Choice, Noul, Score

from weekly_picker.models import AloClass, Labels

GOALS = ["strength", "sculpt and tone", "flexibility", "mobility", "cardio", "calm", "other"]
FOCUSES = ["full body", "core", "legs", "arms", "booty"]
WEIGHTS = ["none", "light", "medium", "heavy"]

_GOAL_DESCRIPTIONS = {
    "strength": "Builds muscular strength: resistance work with weights, bands or bodyweight, aimed at getting stronger",
    "sculpt and tone": "Muscular endurance and shaping: Pilates, barre or sculpt style work with light weights or "
                       "bodyweight and many controlled repetitions",
    "flexibility": "Stretching and lengthening to increase range of motion: deep stretches, long holds, splits",
    "mobility": "Joint mobility and movement quality: gentle controlled ranges for hips, spine and shoulders, "
                "warm-up or rehab style",
    "cardio": "Mostly continuous heart-rate work: HIIT, jumping, running-style intervals or fast cardio dance",
    "calm": "Calming the mind and body: meditation, breathing, restorative or sleep-focused practice",
    "other": "None of the above, for example teaching skills, talks, nutrition or inversion technique",
}
_STRENGTH_LEVELS = [
    "No strength work: stretching, meditation or breathing only",
    "Light strength work: gentle bodyweight or small movements, mostly serving another aim",
    "Solid strength work: a real muscle-building component with resistance or sustained effort",
    "Heavy strength work: demanding resistance training with heavy weights or advanced bodyweight strength",
]
_WEIGHT_DESCRIPTIONS = {
    "none": "No weights recommended, or bodyweight only",
    "light": "Light weights, roughly 1 to 5 lb (up to 2 kg)",
    "medium": "Medium weights, roughly 5 to 10 lb (2 to 4.5 kg)",
    "heavy": "Heavy weights over 10 lb (4.5 kg), or advice to use the heaviest weights you have",
}
# Physio areas Georgia wants more of. Every class gets a true/false probability for each, since one class can hit several.
PHYSIO_AREAS = {
    "shoulder_stability": "Works shoulder control, like a physio's resisted shoulder external rotation or forward "
                          "flexion: the rotator cuff, rotating the arm outwards, raising the arms forward and "
                          "overhead with control",
    "hinge": "Works the back of the legs and the glutes with hip hinges, like a skater deadlift: deadlifts, "
             "good mornings, hamstring and bum work",
    "balance": "Includes balance work, like the single-leg balance in a skater deadlift: standing on one leg, "
               "single-leg hinges or squats, balance poses",
    "side_bend": "Includes side bending, like a physio's lumbar side flexion: side stretches, lateral lines, "
                 "obliques and the sides of the lower back",
    "spine_twist": "Includes spinal rotation, like a physio's thoracic rotations: twists that turn the mid and "
                   "upper back",
}
_PHYSIO_YES_NO = {"true": "Yes, a clear part of this class", "false": "No, or only in passing"}

_PHYSIO_FEEL_LEVELS = [
    "Nothing like physio: fast, flowing or performance focused",
    "A little like physio: some slow, controlled moments",
    "Quite like physio: mostly slow, controlled, joint-focused work",
    "Very like physio: careful, controlled, rehab-style exercises for specific joints and muscles",
]

_FOCUS_DESCRIPTIONS = {
    "full body": "Works the whole body with no single main area",
    "core": "Mainly abdominals, obliques and deep core",
    "legs": "Mainly quads, hamstrings, calves and inner or outer thighs",
    "arms": "Mainly arms, shoulders, chest or upper back",
    "booty": "Mainly glutes and hips",
}


def class_state(c: AloClass) -> dict:
    return {"class": {
        "title": c.title, "mins": c.mins, "difficulty": c.difficulty, "intensity": c.intensity, "style": c.style,
        "categories": list(c.categories), "equipment": sorted(c.equipment), "focus": c.focus,
        "description": c.description,
    }}


def physio_questions() -> dict:
    """The physio questions alone, so classes labelled before they existed can get just these."""
    questions = {"physio_feel": Score(
        instructions="How much does this class feel like a physiotherapy session? Judge from `class.title`, "
                     "`class.description` and `class.style`.",
        criteria=list(_PHYSIO_FEEL_LEVELS),
    )}
    for area, description in PHYSIO_AREAS.items():
        questions[area] = Noul(
            instructions=f"Does this class include this kind of work? {description}. Judge from `class.title` and "
                         "`class.description`.",
            criteria=dict(_PHYSIO_YES_NO),
        )
    return questions


def add_physio(label: Labels, response) -> Labels:
    """Keep every earlier answer and add the physio ones."""
    feel = response.scores.get("physio_feel")
    return replace(
        label,
        physio={a: response.nouls[a].noul for a in PHYSIO_AREAS if a in response.nouls},
        physio_feel=feel.score / (len(_PHYSIO_FEEL_LEVELS) - 1) if feel else 0.0,
    )


def label_questions(c: AloClass) -> dict:
    questions = {
        "main_goal": Choice(
            instructions="What is the main thing a person gets from doing this class? Judge from `class.title`, "
                         "`class.description`, `class.style` and `class.categories`.",
            criteria=dict(_GOAL_DESCRIPTIONS),
        ),
        "strength": Score(
            instructions="How much muscle-strengthening work is in this class?",
            criteria=list(_STRENGTH_LEVELS),
        ),
        "low_energy": Noul(
            instructions="Would this class suit someone who feels tired or low on energy and wants something gentle?",
            criteria={
                "true": "Gentle, slow, low impact, easy to stay with when tired",
                "false": "Demanding, fast, high impact or needing a lot of effort",
            },
        ),
    }
    questions.update(physio_questions())
    if "weights" in c.equipment:
        questions["weight_needed"] = Choice(
            instructions="What weight does the instructor recommend or imply for this class?",
            criteria=dict(_WEIGHT_DESCRIPTIONS),
        )
    if c.focus is None:
        questions["focus"] = Choice(
            instructions="Which body area does this class mainly work?",
            criteria=dict(_FOCUS_DESCRIPTIONS),
        )
    return questions


def to_labels(c: AloClass, response) -> Labels:
    goal = response.choices["main_goal"]
    weight = response.choices.get("weight_needed")
    focus = response.choices.get("focus")
    return add_physio(Labels(
        class_id=c.id,
        main_goal=goal.choice,
        goal_probs=dict(goal.probabilities),
        strength=response.scores["strength"].score,
        weight_needed=weight.choice if weight else "none",
        low_energy=response.nouls["low_energy"].noul,
        focus=focus.choice if focus else None,
    ), response)


MAX_CANDIDATES = 40  # the weekly shortlist size (the picker ranks it from Jev's saved labels)
