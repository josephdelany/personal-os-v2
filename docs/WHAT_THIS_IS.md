# WHAT THIS IS

*The articulation. Written 2026-09-02 from everything Joe has said across the
project, so the structure can be built around a clear statement instead of a
tab list. Joe corrects this; nothing gets built until he recognises himself in it.*

---

## The one sentence

**A case file on you, kept by an agency that works only for you, that cannot
lie, and that knows you better than you know yourself.**

Not a health tracker. Not eight apps. Not a dashboard. A *file* — the kind
Palantir would assemble if the subject were the client: everything you emit,
collected passively where possible and asked for where not; cross-referenced
across every source; assessed honestly at every step; and read back to you as
findings, projections, and instructions, each carrying exactly the confidence
it has earned.

The reason it isn't "eight apps" is the reason an intelligence agency isn't
eight apps. Agencies don't have a sleep app and a money app. They have **one
subject, many sources, one assessment.** Sleep, money, movement, attention,
food, drink, mood, places, people — those are *collection disciplines*, not
products. The product is the file.

---

## What it does — the five things, restated as the file's functions

**1. It collects everything you're exposed to.**
Passively: heart, sleep stages, HRV, temperature, gait, steps, workouts from
the watch; every place you go and how long you stay; every purchase; every
site, every video, every email, every commit, every calendar block; weather
and daylight wherever you are. Actively, for the things no sensor sees: what
you ate, what you drank, what you lifted, how you feel, what happened. Three
minutes in the morning, a photo per meal, a voice note when you want, ten
minutes at night. Nothing else. The file grows whether or not you open it.

**2. It shows you yourself honestly.**
Every number traces to a source. Every self-report shows its interval. Absence
is "not logged," never zero. Stale is labelled stale. Every claim wears the
tier it has actually earned, from a plain description up to a confirmed,
pre-registered finding — and the system publishes its own false-positive
rate next to every scan, so you can see how much of what it "found" would
appear in shuffled noise. It never softens, never cheers, never moralises. It
will tell you things you don't want to hear, in the same voice it tells you
everything else.

**3. It finds true things about you that you didn't know.**
Everything is in conversation with everything. Not a fixed list of hypotheses
— a general inference engine over every metric it holds, at every lag, across
every domain, corrected for multiplicity and autocorrelation, with a shuffled
null run beside it. The Friday bar tab that shows in Saturday's HRV. The late
screen that shows in deep sleep two nights later. The purchase pattern that
precedes the low week. It surfaces these as exploratory — text, labelled,
never a chart — and lets you watch one until it proves or fails.

**4. It answers anything you ask about your life.**
"What was I doing on the 14th?" "How much have I spent at bars since June?"
"Is my resting heart rate different on days after I lift?" "When did I last
sleep past eight?" Answers come only from your own data, only from computed
results, never from a model's guess — and where the data can't answer, it
says so and says what would let it.

**5. It tells you what to do today.**
This is the one that was missing. Given the assessment, the findings, and the
forecast, it may recommend — with its tier and uncertainty stated, never as a
fact — and every recommendation makes a prediction that gets scored. When it's
wrong, it's demoted automatically. Over time you learn which of its advice to
take, because it keeps the receipts.

---

## The feel

Quiet, dense, exact. A reading room, not a scoreboard. No rings, no streaks,
no confetti. Tabular numerals. Every screen opens with one honest sentence and
the evidence sits beneath it. Dark by default. It should feel like reading a
file someone competent has been keeping on you for years — because that is
what it is.

The first honest version will be mostly empty. Workouts: nothing. Food:
nothing. Most body metrics: weeks stale. The file says so plainly, and each
empty section names the one action that fills it. That emptiness is not a
flaw; it's the file being accurate about the collection gap.

---

## The subject's objective

The file exists to serve one thing above the rest: **strength and body
composition.** Every other domain matters partly on its own and mostly for
what it does to that. Sleep, food, alcohol, stress, money, places — the file
tracks them all, but the question it's always asking underneath is: *what is
moving the lifts, and what is moving the scale?*

---

## The structure that falls out of this

If it's a file, it has the sections a file has. This is the proposed shape —
not tabs for products, but sections of a dossier.

| Section | What it is | Replaces |
|---|---|---|
| **ASSESSMENT** | Today. Current state vs your bands. What's up, what's down, what's stale, what's uncaptured. The one thing worth doing. Forecast with its track record. | Today / daily brief |
| **THE RECORD** | The timeline. Any day since 2019, minute by minute, every source, searchable. The ledger of everything captured. | Timeline / Log |
| **MOVEMENTS** | Where you were, when, how long. Places, dwell, commute, radius, novelty. Gym attendance as ground truth. Bar dwell without a self-report. | Location tracer |
| **SOURCES** | The collection disciplines — Sleep, Recovery, Vitals, Movement, Workouts, Food, Drink, Mood, Attention, Money, Content, Places, Email, Calendar, Weather. Each a full deep-dive with the same nine-module skeleton. Each labelled with density and staleness. | Domains / "the 8 apps" |
| **FINDINGS** | What the analysis has established, at what tier. Exploratory patterns with their null. Watched hypotheses with their clock. Confirmed findings with their pre-registration. Refuted ones kept visible. | Intelligence / Patterns |
| **RELIABILITY** | How much to trust each part of the file. Claimed vs achieved forecast coverage. The scan's false-positive rate. Missed predictions. Blindspots — what the file cannot currently see. Heartbeats. | Trust |
| **THE DESK** | Ask anything. Capture. Correct a record. Register a hypothesis. Settings. | Me / Ask / Log |

Seven sections. Every domain lives inside SOURCES, built once from the
nine-module skeleton and instantiated by configuration — which is how "every
app" gets built without building every app.

---

## What Joe needs to confirm or correct

1. Is the one sentence right? If you wouldn't describe it that way to someone
   else, say how you would.
2. Is the objective right — strength and body composition above everything?
3. Are the seven sections the right cut? Add, merge, rename.
4. Is MOVEMENTS its own section, or a source inside SOURCES? (I made it its
   own because you asked for it by name and because it cross-references
   everything.)
5. Dark by default, dense, quiet — is that the feel, or do you want it to
   feel different from that?
