# ADR-0050: The specification curve and the promotion gate (REQ-TIER-012)

## Status
Accepted. Built by B9.1 (`docs/build/B9_confirmation_gate.md`), migration 0046, session 20.

## Date
2026-09-02

## Context
REQ-TIER-012 promotes a hypothesis only when it "passes hierarchical-FDR rejection at every level of its
branch, has a specification curve computed over at least 50 defensible specifications, and has a
circular-shift null showing its significant-specification share exceeds the null median". Until B9 the
resolver promoted on **one** contrast (ADR-0049's v2 look-1 rule: same sign, p<0.05, n_eff>=20). That is
one of the three conditions, so `PROMOTED` was over-claimed against its own requirement.

## Decision
`tools/engines/speccurve.py` (`speccurve-v1`) computes a fixed grid of **108 specifications** —
3 transformations (raw, weekday-demedianed, detrended+weekday-demedianed) x 3 splits (quartile, tertile,
median) x 3 trims (none, 1%, 5%) x 2 windows (all post-registration days, last 60) x 2 tests
(Mann-Whitney, Welch's t) — every one on post-registration days only. 108 >= REQ-TIER-012's floor of 50.

- **The grid is fixed in the file, not chosen per hypothesis** (RULE-13: the model never selects the
  temporal or analytic specification). "Defensible" is used in the narrow sense the requirement needs:
  each axis is a choice a careful analyst could have made in advance, and none is made after seeing a result.
- `share_sig` = the share of the 108 with p < 0.05 **and** the registered sign.
- The **circular-shift null** repeats the identical 108 on a shifted outcome series using the scan's own
  `_shift` (deterministic per name, so a null run reproduces rather than varying), 20 repetitions, median
  share. Promotion requires `share_sig > null_median_share`.
- **Hierarchical FDR** at look 1: level 1 is BH across the watches looked at that night within the same
  `(driver family -> outcome family)` cell; level 2 is BH across the family Simes p-values. Both must
  reject. The Simes and BH primitives are the scan's (`scan._simes`, `scan._bh`) — one owner (RULE-11/12).
- **REQ-TIER-028 counter-frame** is computed at promotion and carried in every PROMOTED/CONFIRMED payload:
  the count of post-registration days where the outcome was in its bottom quartile *and* the exposure was
  in its bottom quartile — outcome-negative days that happened without the exposure.
- Failing the FDR gate ledgers `insufficient_fdr_not_rejected` (vocabulary `low_n_eff`, per B9); failing
  the specification curve or the null ledgers `insufficient_spec_curve_unstable` (vocabulary
  `sign_unstable`). Neither ends the watch: it waits for look 2.
- Every specification's statistics persist in `analysis.spec_curves` (INV-3: the rendered share traces to
  108 stored rows). The column is `window_spec`, not `window` — `window` is a reserved word in PostgreSQL
  and B9's DDL as written fails to parse (found by the test suite, fixed minimally).

## The honesty number
The whole gate (B9.2's conjunction, which promotion feeds) confirms **3.0%** of pure-noise pairs
(6/200 seeded AR(1) rho=0.5 runs, direction pre-registered) — under REQ-TIER-012/013's implied 5%.
Measured by `test_ADR_0050_confirmation_on_pure_noise_synthetic_is_below_5_percent`, which runs in CI.
The same measurement with the direction chosen **after** seeing the data gives 6.5% — the arithmetic
value of pre-registration, in this system, is that difference.

## Consequence that changes when a watch can be promoted
A circular shift of at least 30 days, in either direction, needs at least `2*30 + 1 = 61` paired days:
on a 45-day window every offset >= 30 is equivalent to a shift of <= 15 the other way, and on a 30-day
window there is no valid offset at all. **So a v2 watch cannot be PROMOTED until it has ~61 paired
post-registration days, not the 30 its look-1 rule names.** Before that the gate ledgers
`insufficient_window_too_short` and the watch waits. This is not a threshold anyone chose: it falls out
of REQ-TIER-012's own condition, and the alternative — shrinking the shift on short windows — would be
weakening the requirement to make it passable (RULE-00). Look 1 can still REFUTE at 30 days; only
promotion waits. Recorded here because it silently changes ADR-0049's v2 timetable.

`scan._shift`, which B9 names for the null, **cannot be used**: it computes its offset as
`60 + hash % 241` with no reference to the series length, so on any series shorter than the offset
`vals[-k:] + vals[:-k]` is the identity and the "null" is the observed data. Measured before the fix: a
synthetic pair with a real effect scored `share_sig = 1.000` and `null_median_share = 1.000`. The scan
itself is unaffected (it runs on seven-year series where the offset always shifts), so `speccurve` has
its own `circular_shift` and `scan` is untouched.

## Consequences
- `PROMOTED` now means what REQ-TIER-012 says it means. A hypothesis that survives one contrast but not
  108 specifications does not reach it.
- The nightly resolver is slower at look 1 (108 specifications + 20 null repetitions per maturing watch).
  Only watches crossing a look boundary pay it, which is at most a handful per night.
- `get_findings.watching[]` and `.promoted[]` carry `spec_curve:{n_specs, share_sig, null_median_share}`
  and `fdr:{q_l1, q_l2}`, so the surface can state the share rather than assert the promotion.

## Not built
The specification grid is not itself pre-registered per hypothesis (it is a global constant); no
bootstrap interval on `share_sig`; the null uses 20 repetitions, not a full permutation distribution.
