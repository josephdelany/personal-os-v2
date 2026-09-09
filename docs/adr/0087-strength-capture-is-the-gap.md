# ADR-0087 — The Watch has recorded 25 strength sessions in four years; the set logger is the capture

Status: accepted
Date: 2026-09-09
Requirements: REQ-WKT-001..007, INTENT_COVERAGE R2.

## The finding

`export.zip` contains 32 `<Workout>` elements covering 2023-02-22 to 2026-08-21. Of those, 25
are `TraditionalStrengthTraining`, and their distribution is:

| year | strength sessions |
|---|---|
| 2023 | 17 |
| 2024 | 4 |
| 2025 | 3 |
| 2026 | 1 |

**Two of the 32 workouts fall inside the 2026-07-01 recovery window, and both are runs.** The
most recent strength session is 2026-06-30 — one day before the window opens.

INTENT_COVERAGE names strength and body composition as the primary objective. The system's
record of that objective is 25 rows over four years, none of them containing a set.

## What this changes

Importing Apple's workout records is worth little and was worth planning around a lot. The
useful work is not a `<Workout>` parser; it is the per-set capture path, because **data can
only be collected once** and every week without it is a permanent hole in the only domain Joe
named as primary.

That path was almost complete and nobody had noticed:

- `tools/make_shortcut_workout.py` already generates a "Log Workout" shortcut posting one set
  per run — `{kind:'workout', exercise, weight_lb, reps, rpe}`.
- `core.metric_registry` already carries `strength_load_lb`, `strength_reps`, `strength_rpe`,
  so REQ-WKT-005's "the registry rows are owed" is discharged.
- **Nothing joined them.** A tapped set landed in `raw_captures` and stopped there.

`tools/extract_workouts.py` closes that. It is the whole of the missing link.

## Two data-quality facts about Apple's own numbers

`duration` is ACTIVE time and is not the elapsed interval, and for strength sessions the two
diverge badly because the workout is left running:

- 2023-02-26: 185 active minutes inside a 376-minute window.
- 2025-07-29: **0.2 active minutes inside a 633-minute window** — started and forgotten.

So elapsed time is not a usable session duration for strength, and computing one from
`[startDate, endDate)` would produce a ten-hour training session. Both facts are stored when a
workout is imported — the active duration as the value, the interval as `valid_interval` — and
neither is derived from the other.

## OQ-33 is answered by construction

The shape question — per-attribute atoms sharing a set key (a), or a composite set atom (b) —
is settled by what the built model can express. An `atoms` row carries a single `value_point`,
so (b) needs a schema change; the registry already holds three per-attribute keys; the
shortcut already posts three per-attribute fields. Joe's ruling is a confirmation, not a
deliberation, and the extractor implements (a).

## What is deliberately not done

- **REQ-WKT-001 is NOT satisfied and is not claimed to be.** It requires per-set capture and
  forbids recording only a session aggregate. Apple's export has no sets, so importing those
  sessions cannot satisfy it. The requirement stays open until Joe logs sets.
- **REQ-WKT-006 is NOT satisfied.** Canonical exercise resolution is B14's; the verbatim text
  rides as evidence and "Bench Press" and "bench press" remain two strings.
- **REQ-WKT-004 is NOT satisfied.** A bodyweight or assisted movement must be marked, and the
  shortcut has no field to mark one. A 0 lb entry is counted as
  `zero_load_unmarkable_see_REQ_WKT_004` and no load atom is written, because a load of zero
  is a claim about the bar and a pull-up is not that claim. Adding the field is a shortcut
  change, owned by B16.
- **No e1RM and no volume** (RULE-09). Those are derived measures with their own owner and
  `code_version`; a capture path that computes them makes the number untraceable.

## The action this implies

Joe installs the Log Workout shortcut and logs sets. Until then `extract_workouts.py` runs
clean and writes nothing, which is the correct behaviour and also the problem.
