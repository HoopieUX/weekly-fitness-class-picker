# Decisions

The calls I made while building, each with what it costs if wrong. Written in the order the work went.

## Design

- **Code owns the weekly run; the chat agent owns the conversation.** The part that must not fail is plain,
  testable code. Free-text understanding sits in the agent. Cost if wrong: the agent needs a rule table to map
  replies to commands.
- **Silence is neutral.** No feedback never counts as a dislike. Cost if wrong: a disliked class may come back once.
- **Scheduled classes count as done unless the user says "skipped".** There is no way to see whether a class was
  watched, and I did not want extra check-in messages. Cost if wrong: history may count a few skipped classes as done.
- **Jev's labels live in their own tab,** not extra columns on the catalogue. Labelling in batches does not rewrite
  the whole catalogue. Cost if wrong: labels are read in a second tab.
- **One file touches storage.** Cost if wrong: none; it is what makes the tests fast and a later move easy.

## Safeguards

- **Plain rules sit under Jev.** Cardio cut-off, heavy weights, partner workouts, disliked classes and the
  four-week repeat window are code, not a model's opinion. Cost if wrong: a rule is too blunt (the partner rule
  was tuned against the real catalogue for this reason).
- **Jev down means a plain-rules week, said out loud.** Cost if wrong: a less well-matched week.
- **The "more" alternatives are saved,** so "choose 2" picks the class that was offered even if Jev's order shifts
  between calls. Cost if wrong: one extra tab.
- **A failed write never wipes saved rows.** New rows land first, then only the leftover tail is cleared. Cost if
  wrong: none.
- **Bad input gets a one-line answer.** A typo should never look like the picker went quiet.
- **Undo is real.** Clash moves, "ok" and the Monday auto-add can all be reversed, and undoing one class does not
  undo the whole week. Cost if wrong: undo after "choose" or "repeat" removes the whole week.

## Behaviour

- **The week is chosen by the calendar, not the weekday.** "Pick" plans this week while any slot is still ahead,
  otherwise next week. Found by testing on a Monday morning. Cost if wrong: say "pick" to re-plan.
- **The Sunday job is safe to run twice.** It changes nothing if the week already has picks. Cost if wrong: say
  "pick" to force a fresh plan.
- **One-off requests are one-off.** "Low energy this week" or "make Tuesday strength" are cleared after the
  Sunday run and never saved to settings. Cost if wrong: a repeat request is needed.
- **Changing a slot's weekday from chat is refused,** with a clear message. An earlier version renamed slots and
  could collapse two of them. Cost if wrong: that change has to be made in settings.
- **Multi-area focus uses the first area** ("legs; booty" counts as legs). Cost if wrong: the variety rule treats
  a legs and booty class as legs.
- **Strength scores run 0 to 3,** because Jev scores are zero-indexed. Feedback nudges the preferred level by 0.25
  and clamps. Cost if wrong: strength nudges clamp one step off.
- **The clash checker looks to the end of the week,** because a class can move that far. Found by a test. Cost if
  wrong: a move could land on an unchecked busy day.
- **Favourites ignore the length limit but not equipment,** and if a long favourite will not fit, the next class
  is used. Cost if wrong: a favourite may be passed over on a busy day.
- **Physio is a nudge, never a driver.** The whole physio effect is capped at a tenth of the score, and "no physio"
  turns it off for a week. Cost if wrong: a slightly less physio-friendly week.

## Known gaps

- Moving a class that has already started says "moved" but moves nothing.
- "Request style" with every slot booked replaces Monday without asking.
- Equipment text shows only the first item when a class needs several.
- The reason Jev failed is not logged, so "picked without Jev" is hard to diagnose.
