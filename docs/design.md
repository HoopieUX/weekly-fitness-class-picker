# Design

This is how the picker works now. It was planned first, then built, then corrected as the tests found gaps.

## Purpose

Every Sunday, pick an on-demand fitness class for each slot in the coming week (Monday to Thursday in my settings) and put them in Google Calendar, so there
is no scrolling through thousands of classes and no daily decision.

In priority order:

1. **Less decision fatigue.** A normal week needs one word ("ok") or no reply at all.
2. **Consistency.** Classes happen at fixed times every week.
3. **Learning.** Hands-on practice building with Jev and with an AI coding agent.

The picks serve four fitness goals: get stronger, sculpt and tone, increase flexibility, and keep going
consistently. No pure cardio unless asked for.

## Who does what

| Job | Done by | Why |
| --- | --- | --- |
| Planning, and every parameter (slots, goals, equipment, length range) | Georgia, with Claude Code | These are personal choices, so a person sets them |
| Writing the code and tests | Claude Code | Fast, and the tests check it |
| Reading each class and judging it (goal, strength, weight needed, low-energy fit, physio areas) | Jev, once per class | A judgement call, so a model is the right tool |
| Ranking the shortlist against a slot goal | Plain code, from Jev's saved labels | The judgement was already made when each class was labelled |
| Filtering, balancing the week, booking, clash checks | Plain code | It must not fail, and it must be testable |
| Understanding free-text replies | The chat agent (Instinct on WhatsApp) | It turns "move Tuesday to 2pm" into a command |

Code owns the weekly run. The agent owns the conversation. Jev never talks to the user; code reads its answers.

Only one file (`store.py`) touches storage, so moving from Google Sheets to a database means rewriting that one file. The files and what each does are in the README's code map.

## Jev's labels

Asked once per class, all questions in one request.

| Label | Answers | Used for |
| --- | --- | --- |
| Main goal | strength, sculpt and tone, flexibility, mobility, cardio, calm, other | Matching classes to slot goals; excluding cardio |
| Strength level | none, light, solid, heavy | Ranking strength-day options |
| Weight needed | none, light, medium, heavy | Excluding classes that need heavy weights |
| Good on a low-energy day | probability | Gentler swaps |
| Focus (only where the catalogue is blank) | full body, core, legs, arms, booty | The focus mix rule |
| Physio areas | one yes/no per area, plus how much it feels like a physio session | A small nudge, capped at a tenth of the score |

Everything else is plain rules, not Jev.

## Weekly rules

1. **Filter.** Length 10 to 30 minutes; all equipment owned (after normalising names); style allowed; not cardio;
   no heavy weights; no partner workouts; not disliked; not done in the last four weeks unless asked for.
2. **Match the slot goal** using Jev's label.
3. **Balance the week.** Different focus areas across the week's classes (full body allowed once), and no
   instructor twice when instructors are known. If nothing fits, the rules relax in steps rather than failing.
4. **Rank** the shortlist against the slot goal, using the probabilities Jev saved when it labelled each class. Liked and favourite classes get a nudge; "too hard" and
   "too easy" feedback moves the preferred strength level.
5. **Check the calendar.** Classes only go between 09:00 and 12:00, starting at 10:00 if free, otherwise at the nearest free 15-minute slot that day, else the next free weekday. If nothing fits, the class is left out and the message says so.
6. **Write the picks** as proposed. They become real calendar events on "ok", or automatically at 23:00 on Sunday if there is no reply.

## The weekly rhythm

- Sunday 20:00: picks are made and a message goes out.
- Sunday 21:00: a check tells me if the picks never ran.
- Reply "ok" to add them, change them in plain words, or say nothing.
- Sunday 23:00: with no reply, the picks are added anyway, and the message says how to undo. Anything I changed before then is what gets added. This only happens if the preview was delivered (the agent confirms with `delivered`); if not, nothing is added and I am told why.
- Through the day: the clash checker keeps booked classes clear of new events.
- After a class: "like", "too hard" and so on feed the next week.

## When things go wrong

| Situation | Behaviour |
| --- | --- |
| Jev is unavailable | Nothing changes for the weekly run, because the labels are already saved. Only newly added classes wait to be labelled |
| A calendar write fails | The message says which class did not save, with its link |
| The weekly job did not run | A check message tells the user nothing was drafted |
| Two commands at once | They queue behind a lock, so they never interleave |
| A typo or unknown word | A one-line answer that says what went wrong, never silence |

## Left out on purpose

- Instant clash detection through calendar push notifications (a 30-minute check is enough for morning classes).
- Checking the provider's watch history to confirm a class was done. Scheduled classes count as done unless the
  user says "skipped".
- Connecting a cycle-tracking app.
