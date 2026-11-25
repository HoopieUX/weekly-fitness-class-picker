# Decisions

The main calls I made while building, each with what it costs if wrong.

## The shape of it

- **Jev labels each class once; the weekly run never calls it.** An early version asked Jev to score the shortlist
  every Sunday. That repeated a judgement already made, and tied the weekly run to a key and a network call. Now the
  weekly pick ranks from Jev's saved labels, and Jev only looks again if a question changes or new classes are added.
  It also means a small model can run the week. Cost if wrong: the ranking cannot react to anything the labels do
  not capture; the fix is a new label.
- **Code owns the weekly run; the chat agent owns the conversation.** The part that must not fail is plain,
  testable code. Free-text understanding sits in the agent. Cost if wrong: the agent needs a table mapping replies
  to commands (`docs/for-agents.md`).
- **One file touches storage (`store.py`).** It keeps the tests fast and makes a later move off Google Sheets a
  one-file job. Jev's labels live in their own tab so labelling never rewrites the whole catalogue.

## Safeguards

- **Plain rules sit under the labels.** Cardio cut-off, heavy weights, partner workouts, disliked classes and the
  four-week repeat window are code, not a model's opinion. Cost if wrong: a rule is too blunt.
- **No reply means yes, but only if I saw the preview.** The picker cannot see WhatsApp, so the agent runs
  `delivered` after sending it, and the 23:00 auto-add checks for that. If it is missing, nothing is added and the
  message says why. A new plan clears the mark. Cost if wrong: if the agent forgets `delivered`, I say "ok" myself.
- **Auto-add uses the same week as "ok".** The first version looked at "this week", which at 23:00 on Sunday is the
  week that is ending, so it would have added nothing and said nothing. Found while moving the job from Monday
  morning to Sunday night.
- **Classes are only placed between 09:00 and 12:00, preferably at 10:00.** Otherwise the nearest free 15 minutes. If
  nothing fits, the class is left out and the message says so; a swap that cannot fit leaves the slot as it was.
  A time I choose myself ("move Tue to 14:00") is respected. Cost if wrong: a busy morning leaves a gap instead of
  moving a class to the afternoon.
- **A failed write never wipes saved rows.** New rows land first, then only the leftover tail is cleared.
- **Bad input gets a one-line answer,** so a typo never looks like the picker went quiet.
- **Undo is real.** Clash moves, "ok" and the auto-add can all be reversed. Cost if wrong: undo after "choose" or
  "repeat" removes the whole week.

## Behaviour

- **The week is chosen by the calendar, not the weekday.** "Pick" plans this week while any slot is still ahead,
  otherwise next week. The Sunday job is safe to run twice; "pick" forces a fresh plan.
- **One-off requests stay one-off.** "Low energy this week" or "make Tuesday strength" clear after the Sunday run and
  are never saved to settings.
- **Scheduled classes count as done unless I say "skipped".** There is no way to see whether a class was watched.
  Silence is neutral: no feedback never counts as a dislike.
- **Changing a slot's weekday from chat is refused.** An earlier version renamed slots and could collapse two.
- **Favourites ignore the length limit but not equipment.** If a long favourite will not fit, the next class is used.
- **Physio is a nudge, never a driver.** The whole effect is capped at a tenth of the score, and "no physio" turns it
  off for a week.
- **Smaller calls:** multi-area focus uses the first area; strength scores run 0 to 3 because Jev's are
  zero-indexed; the clash checker looks to the end of the week because a class can move that far.

## Known gaps

- Moving a class that has already started says "moved" but moves nothing.
- "Request style" with every slot booked replaces Monday without asking.
- Equipment text shows only the first item when a class needs several.
