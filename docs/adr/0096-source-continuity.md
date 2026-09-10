# ADR-0096 — Detect an instrument change masquerading as a change in Joe's life

Status: accepted (`tools/check_source_continuity.py`; no migration, no production write)
Date: 2026-09-09
Requirements: RULE-05, RULE-06, RULE-12, REQ-NFR-005..014 in spirit.

## The same mistake, twice, in two domains

**Steps.** Both devices recorded whole days until the Watch went silent on 2026-08-21.
September averages ~2,200 steps against July's ~3,800. Nothing about Joe's walking changed;
one of two instruments stopped (ADR-0085, OQ-54).

**Money.** `bank_csv` carried 35–46 charges a month, $2,400–3,400, through 2026-05-13, then
stopped. `chase_email` began on 2026-06-20 carrying 9–16 charges a month, $322–462 — about a
third of the transactions and a **seventh of the value**. Between them sit **38 days with no
transaction from any source**.

Both look like a person who abruptly did much less. Both are a capture path changing under a
metric whose name did not.

## Why freshness cannot see it

`check_freshness` asks *did anything arrive*. After the transaction backfill,
`transaction_amount_usd` is **fresh** — its newest row is 2026-09-05 — and that is true and
useless. The question here is *did the same thing keep arriving*, and no staleness limit can
express it. A metric can be perfectly fresh and carrying a seventh of the reality.

## What it does, and refuses to do

It reports per-source spans and monthly rates, and flags two things: a **gap** longer than
seven days between one source ending and the next beginning, and a **rate change** above 50%
across a source change.

It corrects nothing and calls neither figure wrong. Which instrument to trust is a measurement
decision (RULE-12), and the honest answer is often **neither — the truth for that window was
never captured**. Publishing the later number understates; publishing the earlier one asserts
data that does not exist; averaging them invents a third thing. The tool exists so a trend
spanning the boundary can be refused or qualified rather than published.

A test asserts it stays silent on a continuous source and on a clean same-day handover with a
steady rate. A detector that fires on healthy data is noise, and noise is ignored precisely
when it matters.

## What this implies for existing answers

Any spend total or trend crossing **2026-05-13** is affected, including the merchant totals
verified in ADR-0093 — Hannaford's 1262.14 over 500 days is drawn almost entirely from the
`bank_csv` era, and the same question asked over the last 90 days sees the sparse
`chase_email` lane. The figures are correct about the atoms; the atoms are not a complete
record of that window, and only this check makes that visible.

## Carried into the answer (0059)

`spend`'s result now includes `sources` — each contributing capture source with its charge
count and its own first and last day — and `source_discontinuity`, true when more than one
source fed a single window. Computed from the matched atoms, so it cannot go stale when a new
source appears, and silent when only one source is involved.

**Two different failures, and only one is a "discontinuity".** Real data made the distinction:
every one of Hannaford's 30 charges came from `bank_csv` alone and stopped on **2026-05-03**,
so a "last 500 days" total was drawn from a source that had been dead for 129 of them.
`source_discontinuity` is correctly *false* there — one source is one source. What exposes it
is each source carrying its own span, which is why the spans are present even when nothing is
flagged. A test asserts that.

## Not done here

The caveat sentence still describes only the merchant-versus-descriptor limitation; the source
facts live in the structured result rather than in the prose. Putting a coverage clause in the
sentence needs a template change and belongs with the next `ask` migration.
