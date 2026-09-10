# ADR-0107 — Measuring adherence without the mechanisms that destroy it

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-CAP-093, 094, 095, 096, 097, 098, 099
**Implements:** B16 §F.3.

## Context

Every obvious way to measure adherence makes this system worse:

- **A streak** turns one missed day into a reason to abandon everything. The spec's own non-goals
  say so: *"the downside — abandoning the whole system after one missed day — is severe."*
- **A 100% bar** guarantees daily failure.
- **Imputing a missing meal** makes the record look complete while making it false.
- **More prompts when compliance falls** is the one intervention the cited studies found
  participants uniformly aversive.

So this module is mostly prohibitions, and the things it does measure are deliberately dull.

## Decisions

### Coverage has no memory of which days were adjacent

A rolling 7-day percentage and a streak count are computable from the same data and say opposite
things after one missed day: the percentage goes 100% → 86%; the streak goes 40 → 0. **The second
is a cliff, and the cliff is what makes a person stop.**

So `run_lengths` is *deliberately absent* from this module — unlike `regimes.py`, where
REQ-INF-545 requires exactly that function. A test asserts the attribute does not exist. The
capability is not merely unused; it is unavailable.

### The denominator is the window, not the days that have a record

Dividing by "days we heard from" would report 100% for a week containing one entry — the
arithmetic version of imputing the rest (REQ-CAP-099). A day with no record is marked
`no_record`, not zero: *missing* and *logged nothing* are different facts, and only one of them
is about Joe.

### The alert is addressed to the design log, not to Joe

REQ-CAP-097 fires only on three consecutive weeks each losing more than two percentage points.
That is deliberately hard to trip: an alert that fires on ordinary variation trains its reader to
ignore it, and this is the only signal that *the asking* has stopped working.

And it goes to `design_alerts`. **A declining check-in rate is evidence that the asking is wrong,
not that Joe is failing.** Sending it to him would be the nag REQ-CAP-098 forbids, arriving under
another name.

`prompt_plan` has no code path that returns more prompts than it was given. `coverage_pct` is
accepted as a parameter and used only in the explanation — the instinct to add reminders is
exactly backwards, so the function is built so that it cannot.

### F-Q1 is left open rather than settled by accident

The spec's F-Q1 asks what counts toward rolling 7-day coverage. `day_is_covered` takes
`components` as a parameter with the conservative default instead of baking it in where a later
ruling could not reach it. What is *not* open is REQ-CAP-096's bar: two eating occasions, never
all of them.

## The linter, and the two things building it found

REQ-CAP-095 needs a linter, and scoping it correctly was the whole problem.

**Run over source code it produced ~200 hits, essentially all false.** `chain` (a migration chain,
a supersession chain), `rank` (a window function, a tier ordering), `points` ("the number points
at"), `broke` (a commit message). REQ-CAP-095 says SHALL NOT **display**, and a comment is not a
display. **A linter with 200 false positives is a linter somebody deletes**, so it now runs over
API *envelopes* — the boundary every surface in this system renders. Both keys and string values
are checked, because a key named `streaks` becomes a heading and a heading is a display.

Two findings from building it:

1. **My own explanatory note tripped my own linter.** The sentence explaining that there is no
   streak counter used the word "streak". Rewritten to avoid the entire forbidden vocabulary
   rather than exempted — which proves the point: the policy is explicable without the words, and
   a note that trips its own linter would have been the first argument for an exemption.
2. **`points` is both a game currency and a unit of measurement.** "You have 400 points" must be
   caught; "declined by 2 percentage points" must not — and REQ-CAP-097 is written in exactly
   those words. A linter that fires on the requirement it enforces gets switched off within a
   week. Resolved by excluding on *preceding context* (`percentage`, `pp`, `basis`), so the
   gamified use is still caught. That is precision, not an exemption (RULE-00).

## The contradiction the linter found in the frontend brief

`docs/LOVABLE_FRONTEND.md` line 16: *"No streaks, no badges, no rings, no confetti, no
gamification of any kind, ever."*

Line 31 of the same document: `"streaks":[{"metric":"rhr","run_days":3,...,"historical_max_run":8}]`

Migration 0030's `get_state` is **live in production** and returns that field. The substance is
defensible — a run of days a metric sits outside its band is a real observation, and nobody earns
it — but the field is called `streaks`, carries `historical_max_run`, and a frontend reading that
contract will render *"3 day streak — best ever 8"*. At that point the distinction survives only
in a migration comment.

Recorded as **OQ-76** with a recommendation to rename rather than remove. Not decided here:
renaming a field in a live API is a contract change, and whether metric-deviation runs count as
"streaks" is a product judgement about what Joe will read.
