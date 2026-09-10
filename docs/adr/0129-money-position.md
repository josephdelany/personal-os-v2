# ADR-0129 — Inbound money is not income

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-001..004, 120..123, 214, 222, 223, 259..266
**Implements:** B17's Missing-C block — income, balance, budget and forecast. Nineteen
requirements. REQ-FIN unproven 36 → 18.

## The correction that started this

**I described the remaining work as "increasingly the ones that need you: credentials, hardware,
and the two library rulings."** That was too generous, for the second time in this session.
REQ-FIN-259..266 — income, balance, reconciliation, budget, forecast — are pure logic and need
nothing from Joe. Checking the list rather than characterising it is the lesson, and it is now
twice.

## The finding this block exists around

Measured on Joe's own data: **94% of inbound money is internal transfer.**

A system that treats "inbound" as "income" therefore **overstates earnings roughly
seventeen-fold**, and every savings-rate, net-spend and cash-position figure built on it inherits
that error silently.

So `classify_inbound` returns one of four directions, and two of them look like income and are
not:

- **an internal transfer** between Joe's own accounts is not money arriving;
- **a reimbursement already netted** against a shared cost (REQ-FIN-049) is not income either —
  counting it once as a reduction in spend and again as an arrival of money is **double-counting
  in the flattering direction.**

REQ-FIN-261 detects income streams with the **same** recurrence engine, inheriting its maturity
threshold. A separate threshold would be a second definition of "recurring" in one system, and
**a paycheck detected by one rule and not the other is a difference nobody would look for.**

## The balance is as-of, never live

§E's measured harm applies here in full: **a running position updated continuously is the "you
have $312 left" counter with a different label.** So the position is derived as-of a stated date,
updates at most daily, and carries its coverage limitation — because **a balance derived from
imports that stopped on 2026-05-13 is an approximate position, and an unlabelled approximate
position is read as an exact one.**

REQ-FIN-266 flags every non-reconciling period rather than absorbing the difference: **a period
that does not reconcile means transactions are missing, and that period's totals are wrong by
exactly the amount nobody can see.**

## The forecast

REQ-FIN-265: a range at least 20% of its midpoint. **A projected end-of-month total is the single
most tempting number in a finance app — and detected recurrence gives a good basis for one, which
makes it more dangerous, not less.**

## Usage inference is capped by purchase type, not by reasoning

REQ-FIN-120. **A gym membership has a strong usage signal — a place visit. A book has none.**
Letting the engine assign its own confidence would let a plausible chain of reasoning about a
book reach the same number as a door swipe.

REQ-FIN-121 goes further for the not-inferable class: **no inference is attempted at all.** Not
"we tried and could not tell" — an attempted inference on something with no signal produces a
number derived from nothing, and **a 0.0-confidence number still renders.**

REQ-FIN-122's gap is the difference of two estimates, each with its own error, so **the gap's
uncertainty is larger than either.** A point estimate of it would be the most precise-looking and
least supported number in the subsystem.

REQ-FIN-123 is the cheap win in the other direction: **a card present at a gym is stronger
evidence of being at the gym than most things this system could infer, and it costs no capture at
all.**

## Verification

19 tests. Requirements proven 593 → 611 (89%).
