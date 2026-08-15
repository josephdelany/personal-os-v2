# ADR-0005: Nutrition resolution — the `weighed` interval width (STUB)

## Status

Stub — partial. This ADR records **one** decision in full (the `weighed`
interval width) and reserves the rest of its scope for later authorship. The
remaining scope — cache-first USDA lookup order, the personal portion table,
and the interval widths for the other methods — is not decided here and must be
recorded before the Big Mac slice (Phase 3) is built. The part recorded below
is final and immutable in the normal ADR sense; the later additions append,
they do not rewrite it.

## Date

2026-08-15

## Context

Nutrition intervals are stored as `estimate_method` plus a `_low`/`_point`/
`_high` triple (RULE-08, ADR-0002, REQ-NUT-030..035). Interval width is a
function of the resolution method. The research supplied defensible widths for
three methods and none for the fourth:

| Method | Width | Source |
|---|---|---|
| `labelled` | ±10% | label legal tolerance |
| `portion_table` | ±20% | portion-estimation literature |
| `photo_estimate` | 0.75× / 1.60× (asymmetric) | vision MAPE + systematic downward bias |
| `weighed` | **not given** | — |

REQ-NUT-035 shipped with a placeholder ±5% for `weighed`, invented, flagged as
OQ-05 / spec E-Q1. The placeholder encodes an assumption that is wrong: it
treats a weighed food as the *most precise* method in the system, tighter than
a label.

## Decision

**The `weighed` interval width is ±10%, equal to `labelled`, and marked
provisional in REQ-NUT-035 pending calibration.**

The reasoning, which is the point of this ADR and the reason the two methods
are not collapsed:

- A **labelled** packaged food has a *known portion* (the label states the
  serving) and *composition-only* uncertainty (what is actually inside a
  serving versus what the label claims, bounded by legal labelling tolerance).
- A **weighed** generic food has a *known portion* (the scale reading) but
  *composition uncertainty that is plausibly WIDER* than a label's legal
  tolerance — a generic "chicken breast, weighed to the gram" still varies in
  fat and moisture content across birds, cuts and cooking loss, and nothing
  bounds that variation the way labelling law bounds a packaged product.
- Therefore **weighed may end up wider than labelled, not tighter.** Weighing
  removes *portion* error. It does not remove *composition* error, and for a
  generic food the composition error is the larger of the two unknowns.

Setting `weighed = labelled = ±10%` is the honest interim position: equal
until measured, not assumed-tighter.

**The binding structural requirement:** `weighed` and `labelled` remain
**distinct `estimate_method` values** in the schema even while their widths are
numerically equal. The equal width is a current calibration coincidence, not an
identity. Keeping them distinct means a future calibration exercise — weigh a
known-label food, compare the stored value against the label — can separate the
two widths without a schema migration over historical rows. **Never collapse
two methods into one because their current numbers match.**

## Consequences

**Good.** The `weighed` width is now honestly bounded rather than invented, and
set equal to `labelled` rather than tighter than it — so it no longer overstates
its own precision by implying a weighed generic food beats a legally-toleranced
label. (`weighed` and `labelled` are now the tightest widths in the system, tied
at ±10%; `portion_table` is ±20% and `photo_estimate` is wider still.) The
distinct `estimate_method` values preserve the option to re-separate the widths
from real data later at zero migration cost. OQ-05 / E-Q1 resolved.

**Bad / provisional.** ±10% for `weighed` is still a judgement, not a measured
number. It is marked provisional in REQ-NUT-035 and stays that way until a
calibration exercise replaces it with an observed width. The calibration itself
is not yet scheduled.

## What this ADR does NOT yet decide

Recorded so the gap is visible, not silently closed:

- The cache-first USDA resolution order (REQ-NUT-001..008) — the mechanism is
  in the requirements but not yet justified in an ADR.
- The personal portion table design (REQ-NUT-018..023).
- Confirmation of the `portion_table` (±20%) and `photo_estimate` (0.75×/1.60×)
  widths against Joe rather than against the research alone.
- The count→grams resolution for branded menu items (REQ-NUT-050/051), added
  this session; its choice of `estimate_method = 'labelled'` is stated in the
  requirement but not yet argued here.

These must be authored before Phase 3 builds the slice.
