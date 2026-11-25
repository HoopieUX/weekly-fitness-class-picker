# For agents

If you are an agent (Instinct, Muse, Claude Code) reading this repo to run the picker, start here.

## Ground rules

- Run commands as `python -m weekly_picker <command>`. Each command prints the text to send to the user.
- **An empty output means say nothing.** Silence is correct (for example, auto-add with nothing to add).
- Send the output as it is. Do not reword it, and do not invent commands. If the user's message does not fit a
  command, ask them to say it another way.
- Commands queue behind a lock, so it is safe to run two at once.
- Credentials and the live Sheet ID are kept outside the repo. Never write them into a file or a message.
- The code in this repo is the code that runs. The sample in `sample/` is only for trying it with no accounts.

## The weekly schedule

| When | Run | What it does |
| --- | --- | --- |
| Sunday 18:00 | `sunday` | Picks a class for each slot (Monday to Thursday, same time each day) and prints the message |
| Sunday 19:00 | `check-ran` | Says so if the 18:00 job never produced picks; silent otherwise |
| Sunday 23:00 | `autoadd` | Adds anything still only proposed to the calendar, so no reply still works; silent if nothing is waiting |
| Every 30 minutes, 07:00 to 21:30 | `clash-check` | Moves a booked class if a new event lands on it; silent when nothing clashes |

## Replies to commands

| The user says | Run |
| --- | --- |
| "ok" | `approve` |
| "undo" | `undo` |
| "show", "what's this week" | `show` |
| "more Tue" | `more Tue`, then `choose Tue <number>` when they pick one |
| "skip Tue" | `skip Tue` |
| "skipped Tue" (last week's class) | `skipped Tue` |
| "make Tue strength" (this week) | `goal Tue strength` |
| "Tuesdays are strength from now on" | `set-goal Tue strength` |
| "low energy today" | `low-energy-today` |
| "low energy week", "longer this week", "no physio" | `next-week low energy` / `next-week longer` / `next-week no physio` |
| "period started" (optional feature) | `period-started` (add a date if they give one) |
| "move Tue to 14:00" | `move Tue 14:00` (add `--permanent` for every week) |
| "repeat Monday's class" | `repeat Mon` |
| "inversion Monday" | `request-style skills_inversions --on Mon` (the style names are in settings; a wrong one gets a list back) |
| "loved it", "too hard", "too easy", "didn't like it" | `feedback Tue like` (or `too_hard`, `too_easy`, `dislike`) |
| "fav Tue", "unfav Tue", "favs" | `fav Tue`, `unfav Tue`, `favs` |
| "add a class on Fri at 09:30" | `add-day Fri 09:30 <goal>` (this week only) or `set-slot Fri 09:30 <goal>` (every week) |
| "no more Fridays" | `remove-slot Fri` |
| "pick again" | `pick` |

How a feeling becomes a setting ("low energy today" means `low-energy-today`) is the agent's job. The picker does
the picking.

## Which model

The weekly run only passes commands and replies along, because Jev has already made the judgements. A small model
(Haiku, with Claude Code) is enough.
