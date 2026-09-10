# ADR-0104 — Randomized micro-trials: the highest tier, and the highest bar

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-200..217
**Implements:** B19 §D. Depends on no new library (ADR-0103 established that `statsmodels`,
`scipy` and `numpy` were already present; only B19.1 needs anything new).

## Context

Everything else in this system is observational: it watches what Joe already does and strips out
confounding afterwards. A randomized block trial is the one design where the assignment is not
caused by anything about Joe's day — which is why `EXPERIMENTAL` sits above
`CONFIRMED_OBSERVATIONAL` on RULE-16's ladder.

It is also **the only part of the system that asks Joe to change his behaviour for six weeks**.
That asymmetry sets the whole design: the tier is the highest, so the bar for starting is the
highest too.

## The arithmetic, stated rather than hidden

Power was computed before writing any gate, and the result is sobering:

| blocks | detectable effect at 80% power |
|---|---|
| 12 | **1.62 SD** |
| 126 | 0.50 SD |

A twelve-block trial — twelve weeks at weekly blocks — can only detect an effect of about 1.6
standard deviations. A 0.5 SD effect, which most real behavioural effects are at or below, needs
over a hundred blocks.

**The correct consequence is that most proposals are refused**, and that is now what happens. A
system that quietly accepted them would spend six weeks of Joe's compliance on trials that could
not have seen anything, then return a null that means *"we could not have seen it"* while reading
as *"it does not work"*. That is the specific harm REQ-INF-208 exists to prevent, and it is worse
than not running the trial.

So the refusal carries **both** counter-offers: the block count that would reach 80% power, and
the effect the requested duration could actually detect. "No" without either is not a decision
Joe can act on.

## Decisions

### `n` is not `n_eff`, at the planning stage as well as the analysis stage

Blocks are contiguous, so adjacent block means share a boundary and any slow-moving trend.
Treating 12 blocks as 12 independent observations inflates power when planning *and* confidence
when analysing — the same error twice, both times in the direction that flatters the trial.
`effective_n` applies the standard `(1−ρ)/(1+ρ)` correction and `power()` takes ρ.

### Block order is a seeded permutation, never an alternation

`ABABAB` is perfectly confounded with any weekly or fortnightly rhythm, and Joe's life has
several — pay dates, weekends, a training split (REQ-INF-203). Arms are balanced first so they
cannot drift apart by chance at small block counts, then shuffled.

The seed is **BLAKE2b of the trial id, not `hash()`**. Python salts `hash()` per process, so a
`hash()`-seeded sequence differs on a rerun — and an assignment that changes when you look at it
again is not a randomisation, it is a rewrite of history.

### A block must outlast the washout

Otherwise each block begins before the previous exposure wore off, the arms bleed together, and
the contrast is diluted toward zero. That is **a bias toward the null**, so it presents as a
clean negative result rather than as a broken design — the worst way for a design fault to
surface.

### Deviating days are kept, and ITT is primary

A day Joe did the opposite of his assignment is data, not dirt (REQ-INF-209). Dropping it
silently converts an intention-to-treat estimate into a per-protocol one — **the substitution
that makes adherence look like efficacy**, because the days Joe complied are the days he felt
able to, and those differ from the rest in ways the exposure did not cause. So deviating days
stay in and are flagged, ITT over *assigned* arms is primary, and per-protocol is returned only
with a label saying it is not an unbiased estimate.

### A failed randomisation is INSUFFICIENT, not a lower tier

Above 20% deviation, or with blocks incomplete, or without the pre-specified analysis, the result
is `INSUFFICIENT` — **not** demoted to `CONFIRMED_OBSERVATIONAL`. A half-finished randomisation
is not an observational study; it is a randomisation that failed, and the observational tier
would credit it with a design it did not achieve.

### The pre-registration freezes at the first assignment, not at insert

`analysis.trials` is the most attractive row in the system to fudge: move the outcome after
seeing the data and a null becomes an `EXPERIMENTAL` claim. REQ-INF-213 forbids it and a trigger
enforces it.

The line is drawn at the **first assignment**, not at insert, deliberately. A proposed trial Joe
has not accepted may still be adjusted; freezing on insert would push every rethink into a
delete-and-recreate cycle that loses the proposal history. After the first block is drawn,
randomisation has begun and any change is retrospective.

The freeze is **targeted**: `completed_at` and `declined_at` still move. A constraint that blocks
the normal path gets disabled rather than respected.

### Blinding is recorded honestly

Most of Joe's exposures are behavioural and admit no indistinguishable placebo, so `blinded` is
usually false. REQ-INF-205 requires the impossibility to be stated *in the rendered result*, and
the table refuses an unblinded trial with no note. It is not decoration: an unblinded behavioural
trial can move its own outcome through expectation alone, and the reader must be told at the
point of reading.

## A spec discrepancy, recorded rather than silently resolved

REQ-INF-216 says the reasoning layer "SHALL NOT randomize an exposure not marked `tier='lever'`",
while REQ-INF-565 describes the same distinction as a metric "marked `context` in
`metric_registry`". There is no `tier` column on `metric_registry`, and `tier` is already RULE-16's
six-level evidence ladder — overloading it would make "tier" mean two different things one line
apart.

Implemented as `metric_registry.role` (ADR-0102). **This is a wording defect in REQ-INF-216, not a
design choice I am free to make**, and it is recorded here so the requirement can be corrected
rather than quietly reinterpreted.

## Consequences

All three tables are empty and stay empty until a trial is proposed and accepted. The engine and
its constraints are tested; **nothing is observed**. Those are different statuses.

No trial can be proposed today for a second reason worth stating plainly: `metric_registry.role`
defaults to `context`, and **no metric has been marked `lever` yet**. That is Joe's classification
to make, and defaulting it for him is exactly what REQ-INF-565 forbids.
