# ADR-0097 — e1RM is an interval, and a set outside the formula's range produces nothing

Status: accepted (`tools/engines/strength.py`; no migration, no production write)
Date: 2026-09-09
Requirements: REQ-WKT-008..013, REQ-WKT-018/019, RULE-06, RULE-08, RULE-09, RULE-13, RULE-15.

## e1RM is an interval because nobody lifted it

An e1RM from a submaximal set is **resolved, not measured**. Published formulas disagree — at
225 lb × 5, Epley gives 262.50 and Brzycki 253.12 — so reporting either alone states a
precision the method does not have.

The interval is the **spread across the registered formulas**, not an invented percentage band.
That makes it an honest statement of how much the choice of method matters, and it is the only
band this system can justify from evidence it actually has. `estimate_method` names the
formulas and the version, so a stored figure says how it was produced (REQ-WKT-009, RULE-08).

A midpoint exists for ordering and is deliberately not a stored field. The interval is the
estimate.

## A set outside the validated range produces an Omission, not a number

Both formulas are fitted on roughly 1–10 repetitions. A 20-rep set extrapolates far outside
that, and **the number would look exactly like a good one** — same units, same magnitude, same
place in a trend. So `e1rm` returns an `Omission` carrying the reason, and a missing e1RM
becomes a recorded fact rather than a silence (REQ-WKT-010, RULE-06).

A bodyweight set is refused for a different reason and it matters: its e1RM is **undefined**,
not zero. Zero would sort as the weakest set ever performed and drag every trend down.

## ACWR divides rates, not totals

The windows are different lengths. Dividing a 7-day total by a 28-day total reports a quarter
of the truth and makes every athlete look detrained. Both sides are per-logged-day rates, so
**absent days divide out of both** rather than being counted as zeros — a skipped session is not
zero volume and an unlogged day is not a rest day (REQ-WKT-018/019).

Coverage is returned alongside the ratio so a caller can refuse a thin one instead of dividing
two guesses, and every figure carries `windows_calibrated: false`: the 7/28 windows are
provisional placeholders (OQ-36), so the ratio orders sessions against each other and **carries
no threshold**. It must never be rendered beside one until calibrated.

## Pure by construction

No database, no clock, no model. A test asserts the module reaches none of them — RULE-09 (the
model never computes), RULE-15 (these figures survive the language layer being unavailable) and
reproducibility, since a `now()` would make a replay irreproducible.

## What this does not do

Nothing writes these measures yet. Registry rows for `strength_e1rm_lb`, `strength_volume_lb`
and `strength_acwr` are a migration, and the storage question is REQ-WKT-013's point-in-time
contract against `derived_measures`, which does not exist (OQ-22). More to the point: **no set
has ever been logged**, so the engine is correct and idle, exactly like the extractor in
ADR-0087. Both wait on the same thing.
