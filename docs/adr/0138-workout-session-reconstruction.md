# ADR-0138 — A session record is not a set, and discarding it was not "pending observation"

**Status:** accepted
**Date:** 2026-09-11
**Requirements:** REQ-WKT-001/002/003, REQ-REC-004/005/008/009; INTENT_COVERAGE R2
**Migrations:** 0070 (three registry keys, the third registered method)

## The finding this came from

The 2026-09-10 checkpoint recorded INTENT_COVERAGE case R2 — *training history without sets* — as:

> **Pending observation, not missing implementation.**

That was wrong, and it had been wrong since the September import. The evidence:

| what was checked | what was found |
|---|---|
| `_legacy_snapshot/data_capability_inventory_2026-09-09.json` | **32 workout sessions in the export**: 25 `TraditionalStrengthTraining`, 4 Running, 2 Walking, 1 Cycling |
| `tools/importers/apple_health.py:201` | a `<Workout>` element hit `c.bump("workout_deferred_to_B18")` and **was never yielded** |
| production, read-only | **zero** workout-session atoms; `core.metric_registry` had the three `strength_*` keys and **no session key** |
| the two alternative sources | `csv__workouts` EMPTY ("empty file / parse error"), `supabase:public.workouts` 0 rows |

So the recorded training history existed, in the file, on this machine, and the parser counted
every session and threw it away. "Deferred to B18" was load-bearing prose for three weeks.

**The general lesson, which is the reason this ADR exists at all:** a counter that records a
discard is not a deferral. `workout_deferred_to_B18` reported a number nobody read, and a status
line inherited its intent ("we will do this later") while the code's actual behaviour was
permanent data loss at import time. A deferral that leaves no row is indistinguishable from a
capability nobody built.

## The distinction the whole design protects

R2's own words are *"do not invent load, reps or volume"*. Two facts sit either side of that line
and merging them is the only way this feature can go wrong:

```
a strength session was RECORDED, and ran for N active minutes    <- observed, 32 of them
what was on the bar, for how many reps, at what RPE              <- never once recorded
```

`strength_load_lb`, `strength_reps` and `strength_rpe` have been registered since B18 and have
**never received a row**, because the Log Workout shortcut is not installed. Nothing in this
change moves that. `workout_session_min` is therefore registered in its own `workout` family
rather than in `strength`: putting a session duration in the strength family would let a
per-domain surface answer "how is strength going?" with a count of sessions, which is exactly the
substitution REQ-WKT-003 forbids — a workout timestamp is not a lifting set.

**Missing sets prohibit inventing load and reps. They do not prevent reconstructing that a
session occurred.** That sentence is the whole of R2, and the old status conceded the second
clause along with the first.

## Three decisions worth recording

### 1. The duration is the value; the span is the interval. They are never the same fact.

Apple writes `duration` (active minutes, pauses excluded) alongside `startDate`/`endDate` (wall
clock). They routinely disagree, and not marginally. The real 2023-02-26 session:

```
startDate 14:56:13   endDate 21:11:56    -> a 375-minute span
duration  185.23 min                     -> because of a pause at 16:36 and a resume at 19:38
```

Reading the span as the session would report a six-hour training block that did not happen. The
atom's `value_point` is the recorded active duration and its `valid_interval` is the wall-clock
span, stored as two facts because that is what they are.

### 2. The degenerate session is stored exactly as recorded.

The export holds a `TraditionalStrengthTraining` record starting 2025-07-29 08:53:18, paused
eleven seconds later, never resumed, closed at 19:26 — **duration 0.175 min, active energy
0.537 Cal**. It is obviously not a training session and it is obviously a real record of what the
Watch did.

It is stored. Filtering it in the parser would be the importer inventing a minimum-duration
definition of "a workout", and **a measurement definition is Joe's, not a parser's** (CLAUDE.md:
models do not choose temporal specifications). INV-2 makes captures append-only besides. Its own
numbers say what it was, and the question of whether a frequency count should exclude it is
raised as **OQ-81** rather than answered here.

### 3. Every session reconstructed from this export alone lands at DESCRIPTIVE, and that is correct.

The obvious corroboration for a training session is the same day's `exercise_minutes`. It comes
out of **the same HealthKit export**, so it shares the session's `origin_group` and
`independent_origins` counts it once. This is REQ-REC-008 doing its job rather than being
asserted — and it is the identical defect that previously promoted 34 non-wear episodes to
EXPLORATORY on one observation read twice.

The promotion path is real and currently unexercised: a gym `place_visit` is a genuinely
different capture path and does reach EXPLORATORY (tested). **This system has never captured a
`place_visit`.** Said plainly so nobody reads a uniformly DESCRIPTIVE output as a bug.

## What the method may conclude

`training_session` v1, family `training_session`, `required_evidence = {workout_session_record}`,
`permissible_outputs = {occurred}`, `temporal_specification = subject_day`.

- **No `did_not_occur`, by construction.** The Watch stopped in five stages ending 2026-08-21, so
  a day with no session record is overwhelmingly a day it was not worn. Absence of a record is
  absence of capture (REQ-REC-009), and the method is given no output that could say otherwise.
- **Corroboration is not required.** Demanding it would refuse 25 real sessions for want of a gym
  visit this system has never captured.
- It is the **first method that reconstructs an event in Joe's life**. `watch_non_wear`
  (device_state) and `sleep_gap_explained` (data_coverage) are both facts about *the record*,
  so REQ-REC-016's multi-family requirement could be counted but not really demonstrated.

## One repair made along the way

`tools/reconstruct_run.rows_for` ran the device-capture gatherer for **every** method key. With
0067 applied, `--all-methods` would hand `sleep_gap_explained` evidence it does not accept
(`sleep_record_absent`, `watch_non_wear_inferred` — collected by
`tools/reconstruction_acceptance.py`, not by the runner), get `required_evidence_missing` for
every day, and report them all as "examined without a conclusion". **A no-op that reads as a
measurement.** Dispatch is now explicit and a method with no gatherer raises `NoGatherer`, which
`main` reports as one line — `NOT RUN — this tool collects no evidence for it` — and continues,
so the scheduled job does not go red over a method nobody claimed it ran.

## Consequences

- Importing the export now reaches back to **2023-02-22**, well outside the 2026-07-01 recovery
  window, because that is where the training history is. `--since` still bounds it.
- 0070 extends the unapplied stack to **0055–0070**. Nothing here is deployed.
- `tools/engines/strength.py` remains correctly idle. e1RM, volume and ACWR need per-set records
  and this change produces none. Connecting it is **not** part of R2 and was not done.
