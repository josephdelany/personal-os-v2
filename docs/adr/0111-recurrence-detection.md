# ADR-0111 — Recurrence detection: robust statistics, because one missed month is normal

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-130..140 (§C.3)
**Implements:** B17 §C.3, which the spec calls "the substrate for the whole section" — everything
in §C.4 (interventions) and §D (habits) is built on whether a stream was detected at all.

## The two decisions that decide whether this works

### Median and MAD, never mean and standard deviation (REQ-FIN-133)

A subscription billed on the 1st for eleven months and skipped once produces intervals
`[31, 59, 30]`. Measured and checked in a test rather than asserted:

| statistic | value | consequence |
|---|---|---|
| mean | 40.0 | dragged 30% away from the truth |
| standard deviation | 12.4 | the fit fails |
| **median** | **31** | correct |
| **MAD** | **1** | one outlier gets no vote |

**A mean/SD rule loses a real subscription because Joe's card declined once.** That is the entire
argument for the robust statistic, and the test asserts the mean/SD numbers directly so the claim
cannot quietly stop being true.

### Monthly is day-of-month, not thirty days (REQ-FIN-132)

A charge on the 31st recurs on the 28th in February and slides to Monday when the 1st is a Sunday.
Measured as a fixed 30-day interval those are misses. Measured as *same day of month ± 3*, they
are the same subscription.

A 30-day rule is also wrong by construction: it drifts a full day every month, so after a year it
is comparing against a date the merchant has never used. The implementation is month-end aware —
an anchor on the 31st compares against the 28th in February and the 30th in April, which are
exact matches rather than 3-day and 1-day misses.

## The judgements

**Amount stability is not required (REQ-FIN-136).** A phone bill and a utility bill are recurring
in every sense that matters and their amounts move every month. Requiring a stable amount would
detect Netflix and miss the electricity — **and the electricity is the one worth knowing about,
because it is where a step change hides.**

**A rounding change is not a price rise.** The changepoint detector requires the step to clear 5%
of the earlier level. $9.99 → $10.00 has not changed price, it has been rounded, and reporting
that as a price rise trains Joe to ignore the ones that matter.

**A wandering series is `variable`, not `fixed_with_step`.** Any series has a best split; the
classifier checks that each side is actually stable before claiming a step, because
`fixed_with_step` promises a price that holds until the next change.

**The insight names the month, not the index.** *"Utility changed from 12.99 to 15.99 in April
2026"* is a fact Joe can check against his memory. *"A changepoint at position 3"* is not.

**A cancelled stream is returned, never dropped (REQ-FIN-138).** A resurrected subscription is
itself behavioural data: the thing cancelled in March and restarted in September is a more
interesting fact than either event alone, and deleting the row would make the restart look like a
first-ever charge.

**Groceries, fuel, coffee and bars route to habits (REQ-FIN-139)** — same mathematics, different
table, different surface. A weekly coffee *is* periodic, and calling it a subscription would put
"cancel this?" beside something nobody subscribed to.

**Streams are keyed by merchant AND account.** The same subscription on two cards is two streams,
and one may lapse while the other runs.

**Joe's label is applied before any detection work (REQ-FIN-140)**, and `is_a_subscription`
keeps a stream that no period fits. A label he has to reapply is a label he stops giving.

## Changepoint search

Exhaustive single-split rather than iterative, because a stream has tens of points, not thousands.
Exhaustive is deterministic and has no tuning parameters to get wrong, which matters more here
than the asymptotics.

## Verification

21 tests against series whose right answer is known by construction: the 31st sliding through
February, a missed month, a price rise, a rounding change, a wandering utility bill, and a stream
left to lapse and then cancel. `detect` is asserted deterministic under input reordering.

Not claimed: nothing is wired to real transaction data yet. `core.atoms` holds zero transaction
atoms until the backfill in the pending stack is authorised.
