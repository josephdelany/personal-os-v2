# ADR-0125 — The set is the unit, and there is no streak

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-WKT-001..022
**Implements:** B18 §A/§B. **REQ-WKT is now 22 of 22 proven** — the second prefix after REQ-NFR
to reach zero unproven.

## The four decisions

**The set is the unit** (REQ-WKT-001). A session total loses the thing strength training is about:
**5×5 at 225 and 1×25 at 135 are the same volume and completely different training.** Once the
sets are collapsed the distinction cannot be recovered, and every derived measure downstream
inherits the loss.

**One canonical entity per movement** (REQ-WKT-006). *"Bench"*, *"bench press"*, *"barbell bench"*,
*"BB bench"* are one movement. Left as free text they are four series with a quarter of the data
each — and **nothing detects that, because four sparse trends look exactly like four exercises Joe
does rarely.** An unmapped movement goes to review rather than getting its own series, for the
same reason.

**A rest day is `observed_absent`, not a gap** (REQ-WKT-019). *"I chose not to train"* and *"no
data"* are different facts, and only the first is evidence about training. Collapsing them makes a
deliberate deload indistinguishable from a week the phone was off — **and an ACWR that reads them
as identical will call one of them detraining.**

**There is no streak** (REQ-WKT-014/016). Strength is a trend toward a stated objective, not an
attendance record. **Joe's capture has stopped twice this year through no act of his; a streak
would have scored both as lapses.**

## Point-in-time correctness needs both clocks

REQ-WKT-013. A set *about* a day inside the window that was *recorded* after it closed is
knowledge the measure did not have. Letting it in makes a historical figure change when somebody
backfills — **and then the number Joe saw last week is not the number he sees now.**

## The render layer formats and nothing else

REQ-WKT-015. It does not divide, average, convert or total — each of those is a computation, and
**a computation performed at render time has no stored result to trace to.** The test that pins
this uses the *midpoint* of a stored interval: a number that looks entirely reasonable and exists
nowhere in the database.

REQ-WKT-017: the figures render whether or not the language layer is up. **A surface that goes
blank when the model is unavailable has made the model load-bearing for facts that were computed
without it.**

## A word deliberately left permitted

`broken` is attendance language and is banned. **`broke` is not** — *"you broke a personal record"*
is exactly what this surface exists to say, and banning the stem would refuse the sentence the
objective function is about. My first test asserted the opposite and was wrong; the code was
right.

## The objective function, named so it cannot drift

REQ-WKT-022: strength progression **and** body composition, together. Either alone is gameable in
a direction Joe does not want — **e1RM rises with bodyweight, and body composition improves by
eating less and lifting less.** Naming the pair keeps the objective from drifting into whatever is
easiest to measure.

## Verification

19 tests. Requirements proven 532 → 544 (79%); REQ-WKT 12 unproven → **0**.

Not claimed: no set has ever been logged. The Log Workout shortcut is still uninstalled, so every
one of these measures is correct and idle.
