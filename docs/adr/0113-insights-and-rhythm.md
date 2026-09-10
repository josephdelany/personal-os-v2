# ADR-0113 — What the system may say, when it may say it, and the gate that was open

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-150..158 (§C.4), REQ-FIN-190..200 (§D.3)
**Implements:** B17 §C.4 and §D.3. Nineteen requirements, none previously proven.

## The timing decision that is the whole intervention

REQ-FIN-151: an unused-subscription insight is delivered on the **next charge date**, never on
the day the evidence became available.

Payment depreciation erodes the salience of a sunk cost. A subscription bought in March feels
free by June — which is precisely why unused ones survive. Telling Joe in June that he has not
opened it since March lands on a cost he no longer feels; telling him **on the day it charges
again** restores that salience, and that is the moment a cancellation actually happens.

**The delay is the intervention.** `schedule_unused_insight` returns the renewal date and a
renewal already past returns nothing, because a charge that has been and gone is not a moment of
restored salience either.

## REQ-FIN-197 versus REQ-FIN-198, resolved rather than fudged

These look contradictory. 197 forbids ever estimating alcohol volume, units or standard drinks
from a transaction amount. 198 permits a bar tab as a *prior* on drink count at confidence ≤ 0.30.

The difference is the whole of it:

- **An estimate** is presented as a drink count. It answers *"how much did I drink"* with a
  number derived from a price. **$60 at a bar is a round for other people as often as it is four
  drinks for Joe.**
- **A prior** is a disclosed, weak, clearly-labelled input to something else, discarded the
  moment a real `consume` atom exists for that episode.

So `drink_prior` returns `None` unless a prior is requested explicitly, caps confidence at 0.30,
stamps `provenance='inferred'`, sets `drink_count` to `None` in the payload itself, and returns
`None` again once a real observation exists. **There is no function in this module that returns a
drink count.**

## The gate that was open

REQ-FIN-199 fences the Lomb-Scargle periodogram: it may run only where the series holds enough
cycles for a false-alarm probability to be meaningful, and a peak that does not clear the FAP is
**not reported** — not reported at a lower tier, not reported.

The first implementation of that gate did not work, and the test caught it:

- **The FAP formula was wrong.** I used `exp(−p·(N−3)/2)`, which belongs to a differently
  normalised periodogram. With N=400 that exponent is enormous for any *p*, so it returned a
  false-alarm probability of exactly **0.000 for pure Gaussian noise** — and reported a 19.5-day
  "period" in random numbers. The correct expression for normalised power is
  `1 − (1 − (1−p)^((N−3)/2))^M`. Measured after the fix: noise gives FAP 0.054 and is refused;
  a real 14-day sine gives ~0 and is reported.
- **The scipy call was reaching for `_sp.signal` where `_sp` is `scipy.stats`**, which has no
  `.signal`. A `hasattr` guard meant that fell through to a hand-rolled fallback on *every* call,
  silently. It gave plausible numbers, which is exactly why it survived: **a wrong branch that
  returns nonsense announces itself; one that returns something reasonable does not.**

The fallback is now removed rather than left in place. Dead code that once ran silently is worse
than dead code.

## The rest, briefly

**Duplicate services carry the combined amount** (REQ-FIN-154). Three music subscriptions at $11
read as three small charges *or* as one $33 monthly decision, and only the second framing is
actionable.

**A zombie stream names the absent signal** (REQ-FIN-155). *"We think you do not use this"* is
unfalsifiable and irritating; *"no login for 200 days"* is a claim Joe can confirm or correct
immediately.

**The cancellation total is the only score this system keeps**, and it scores the system's own
usefulness rather than Joe's behaviour (REQ-FIN-156).

**A suppressed insight class cannot return under a new name** (REQ-FIN-158). Re-raising the same
idea with different wording is the behaviour that teaches a person to stop reading, and a class
rename is the easy way to do it by accident, so declared aliases are checked too.

**The annotation prompt arrives the following morning** (REQ-FIN-194). Asking at 23:30 interrupts
the evening it is asking about, and the answer would be worse for it.

**Trait and mood vocabulary is delegated to `finance_never`, not duplicated.** Two copies would
drift, invisibly, until one surface shipped a word the other blocked.

**Habit output is framed against Joe's stated goals, never against restraint** (REQ-FIN-200).
Framing around restraint would make the system an authority on how he should live — a role
nothing in a transaction log qualifies it for.

## Verification

37 tests across the two modules. Requirements proven 315 → 335 (49%); REQ-FIN unproven 71 → 51.
Nothing is wired to real data.
