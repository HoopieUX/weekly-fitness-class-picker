# Weekly fitness class picker

![tests](https://github.com/HoopieUX/weekly-fitness-class-picker/actions/workflows/tests.yml/badge.svg)

Every Sunday it picks an on-demand fitness class for each of my days (Monday to Thursday, preferably starting at 10:00), explains why, and puts them in Google Calendar. Jev (an AI) judges each class once and saves the result; after that, plain code does the weekly work.

> This is a snapshot of a private working repo, shared so you can read the real code and tests. It is not kept in sync. One difference: this copy has the old weekly Jev ranking call removed, because Jev only needs to label each class once. The live repo may still carry that older code.

## What it looks like

Three screenshots from a real week, in the order it happens.

![The Sunday preview on WhatsApp](docs/images/1-sunday-preview.png)

**1. The Sunday preview.** Every Sunday, Instinct sends my week's picks on WhatsApp: the class, how long it is and what kit I need, all at 10:00. I reply "ok" and they go into my calendar. If I say nothing, they are added automatically at 23:00, as long as the preview was delivered.

![The week in Google Calendar](docs/images/2-calendar-week.png)

**2. The week in Google Calendar.** The classes are the green blocks. They always sit between 9:00 and 12:00, and they never overlap the grey "Busy" blocks (my other events). That is the clash rule at work: the picker fits classes around what is already in my diary. This is the week as first added, before the move below.

![Moving a class in plain words](docs/images/3-move-a-class.png)

**3. Changing it by just asking.** I ask to move Tuesday's class to Friday. The agent turns that into a picker command, the picker finds the 10:00 slot and updates the calendar event, and Instinct confirms.

The wording and the link previews on WhatsApp come from the agent and WhatsApp. The picks, the times and the calendar changes come from the picker. The diagrams below show how the pieces fit.

## Why I built it

- The catalogue I use has 4,746 classes. Scrolling it every day is decision fatigue, and with no routine I did not do much.
- I wanted classes at the same times each week, matched to goals I set: stronger, more flexible, sculpt and tone.
- I wanted to see what Jev could do when it is given a real, narrow job.

## How the jobs are split

- **Me:** I planned it with Claude Code and set every parameter (days, times, goals, equipment, class length).
- **Claude Code:** wrote the code and the tests.
- **Jev:** reads each class once and judges it (goal, strength, weight needed, how gentle it is, physio areas), then saves those labels. It only looks again if my parameters change or I add new classes.
- **Plain code:** filters classes, balances the week, books the calendar, checks for clashes. This part must not fail, so no AI sits in it.

```mermaid
flowchart LR
    A["Agent<br/>(Instinct, Muse or Claude Code)"] -->|runs commands| P["weekly_picker<br/>(command-line tool)"]
    P -->|reads| L["Jev's saved labels<br/>(one judgement per class)"]
    J["Jev<br/>(labels each class once)"] -->|saves| L
    P -->|books and checks clashes| C["Google Calendar"]
    P <-->|stores| S["Google Sheet<br/>(classes, labels, picks, settings)"]
    A <-->|WhatsApp| Me["Me"]
```

## How a week works

```mermaid
flowchart TD
    A["Sunday evening: picker filters classes with my rules and ranks them from Jev's saved labels"] --> B["WhatsApp message: the week's picks, a reason for each"]
    B --> R{"My reply"}
    R -->|ok| CAL["Classes go into Google Calendar"]
    R -->|swap| SW["Five alternatives, I choose one"] --> B
    R -->|skip| SK["Class removed from the week"] --> CAL
    R -->|fav| FV["Class saved as a favourite, picks lean towards it"] --> CAL
    R -->|"how I feel: 'low energy today', 'something longer', 'no physio'"| F["Agent turns it into a setting and re-picks the class to suit"] --> B
    R -->|no| NO["Nothing is added; ok later still works"]
    R -->|"no reply by 23:00, and the preview was delivered"| M["Sunday 23:00: classes added automatically, with an undo option"]
    M --> CAL
    CAL --> K["Through the day: clash checker moves a class if a new event lands on it"]
    K --> FB["After a class: like, too hard, too easy"]
    FB --> N["Feeds next week's picks"]
    N --> A
```

| When | What happens |
| --- | --- |
| Sunday 20:00 | Picks are made and sent as a preview |
| Sunday 21:00 | A check tells me if the picks never ran |
| Sunday 23:00 | No reply counts as approval: the classes go into the calendar, but only if the preview was delivered and I have not said no or changed the week |
| Every 30 minutes, 07:00 to 21:30 | Clash check: a booked class moves if a new event lands on it |

Classes are only placed between 09:00 and 12:00, starting at 10:00 if free, otherwise at the nearest free 15 minutes, and never on another day. If nothing fits, the class is left out and the message says so. The days and goals are my settings, and the run times live in the scheduler, not in this code.

## Code map

| File | Its one job |
| --- | --- |
| `weekly_picker/__main__.py` | Lets you run it as `python -m weekly_picker` |
| `weekly_picker/catalogue.py` | Reads the class catalogue and tidies messy equipment and focus names |
| `weekly_picker/commands.py` | The command-line interface; every command returns the text to send back |
| `weekly_picker/config.py` | A few constants: time zone, cardio cut-off, repeat window |
| `weekly_picker/gcal.py` | Reads busy times and creates, moves and deletes calendar events |
| `weekly_picker/jev.py` | The questions Jev answers when it labels a class |
| `weekly_picker/labeller.py` | Runs Jev over every class once, resuming if interrupted |
| `weekly_picker/messages.py` | All the chat wording, one class per line |
| `weekly_picker/models.py` | The data shapes: class, labels, pick, settings |
| `weekly_picker/picker.py` | Plans the week: filter, rank, balance, place in free time |
| `weekly_picker/rules.py` | Filters out classes that break the settings |
| `weekly_picker/sample.py` | Loads the sample folder into an in-memory store (used by the demo) |
| `weekly_picker/store.py` | The only file that touches storage |
| `weekly_picker/timeslots.py` | Free-time maths: nearest free slot, next free weekday |
| `scripts/demo.py` | Plans one week from the sample and prints the picks |
| `scripts/pick_classes.py` | Chooses the sample classes and exports a numbered extract with no IDs, links or instructors |
| `scripts/make_sample.py` | Builds the sample: swaps real IDs for demo IDs, drops links and instructors |

## Running it with an agent

It is a plain command-line tool, so any agent that can run commands can drive it. Built with Claude Code; I now talk to it through Instinct on WhatsApp. Muse and Claude Code also work.

Instinct reads this repo for the code. Agents should start with [docs/for-agents.md](docs/for-agents.md): the weekly schedule and which command each reply maps to.

With Claude Code, the weekly booking only needs Haiku. Jev has already done the hard thinking by labelling every class once, so the agent only runs commands and passes on my replies. A lower-level model is the right one for that.

## Try the sample

The sample is 24 classes (six for each of the four slots) with made-up names and rewritten descriptions. Lengths, difficulty, equipment and focus are unchanged. There are no links or instructor names, and the IDs are demo IDs (`C-001` onwards). The labels came from Jev reading the real classes and were carried over to the renamed ones.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python scripts/demo.py
```

No Google account and no Jev key needed. The live version ranks the same way, from Jev's saved labels: Jev only labels again if my parameters change or I add new classes.

## How it was tested

The tests run on every push (see the badge); a few need my private catalogue and skip on a fresh clone. The situations they cover are in [docs/how-i-tested.md](docs/how-i-tested.md). The design and the decisions behind it are in [docs/design.md](docs/design.md) and [docs/decisions.md](docs/decisions.md).

## What's next

- A short video walkthrough of a real week.
- A command to relabel only the classes affected when I change a parameter.
- Moving storage from Google Sheets to a database, which only means rewriting `store.py`.
