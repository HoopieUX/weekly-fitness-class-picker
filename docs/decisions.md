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
- **Jev being down cannot break the week,** because the weekly run does not call Jev (see the last section).
- **The "more" alternatives are saved,** so "choose 2" picks the class that was offered even if Jev's order shifts
  between calls. Cost if wrong: one extra tab.
- **A failed write never wipes saved rows.** New rows land first, then only the leftover tail is cleared. Cost if
  wrong: none.
- **Bad input gets a one-line answer.** A typo should never look like the picker went quiet.
- **Undo is real.** Clash moves, "ok" and the Sunday night auto-add can all be reversed, and undoing one class does not
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

## A failure found while changing the schedule

- **Auto-add used to run on Monday morning, so it looked at "this week".** When I moved it to 23:00 on Sunday, "this
  week" is the week that is ending, so the job would have found nothing and said nothing: the classes would never
  have reached the calendar. The fix is that auto-add now uses the same week as "ok": the earliest week with
  proposed picks and a weekday still to come. Five tests cover it: Sunday 23:00 adds the coming week, an earlier "ok"
  keeps it quiet, a change at 22:55 is still added, nothing picked stays silent (the 19:00 check is the alarm), and a
  fourth day is included. Cost if wrong: a stray proposed pick from an earlier week would not be added.
- **Why silence is safe here.** If the 18:00 job fails, there is nothing to add, so auto-add says nothing on
  purpose; the 19:00 check is what tells me. Two separate jobs, so one failing does not hide the other.

## Placement window and the delivery rule

- **Classes are placed between 09:00 and 12:00 only, preferably starting at 10:00.** Before this the search ran from
  07:00 to 21:00, so a busy morning could push a class to the evening. The default slot time is now 10:00. A
  preferred time outside the window falls back to 10:00. Cost if wrong: a very busy morning leaves a class out
  instead of moving it to the afternoon.
- **Nothing fits means nothing is placed, and I am told.** The weekly message says "nothing placed this week", and a
  swap that cannot fit says so and leaves the slot as it was. This fixed a second bug: a swap used to fall back to
  the old time even when it overlapped something. Cost if wrong: a slot stays empty until I choose a time.
- **A time I choose myself is respected.** "Move Tue to 14:00" is allowed outside the window, because it is my
  explicit choice. Only automatic placement is limited. Cost if wrong: I can put a class outside the window by hand.
- **No reply only counts as approval if I actually saw the preview.** The picker cannot see WhatsApp, so the agent
  runs `delivered` after sending the preview, and auto-add checks for it. If it is missing, nothing is added and the
  message says so, so the failure is never silent. A new plan clears the mark, so a changed week has to be shown again.
  Cost if wrong: if the agent forgets `delivered`, I have to say "ok" myself.
- **The mark is kept in the existing offers tab,** under the name "preview", rather than adding a column to picks.
  Cost if wrong: one slightly odd row in a tab.

## Jev labels once; the weekly run never calls it

- **The weekly pick ranks from Jev's saved labels, with no Jev call.** An earlier version asked Jev to score the
  shortlist every Sunday and fell back to the saved labels only when Jev was down. That was a second, repeated
  judgement on work already done, and it made the weekly run depend on a key and a network call for no real gain.
  Jev now labels each class once, and labels again only when a question changes or new classes are added.
  Cost if wrong: the ranking cannot react to something the labels do not capture. The fix would be a new label.
- **It also means a small model can run the week.** All the hard thinking is saved, so the agent only passes commands
  and replies along.
- **The "picked without Jev" message and the "less sure" flag no longer fire.** The stored columns are kept so old
  rows still read. Cost if wrong: two unused columns.
