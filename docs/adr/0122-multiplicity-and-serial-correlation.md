# ADR-0122 — The discipline around a specification curve

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-001..009 (§B.1), 020..026 (§B.2), 030..038 (§B.3)
**Implements:** B9's statistical discipline. Twenty-five requirements. `speccurve.py` computes a
curve; this is what may be tested, how many tests that makes, and what a sample size means when
the observations are days in a row.

## Why a tree and not one flat family

A flat correction over every metric pair is a family of tens of thousands, and at that size **the
correction is so severe that nothing survives — so nothing is discovered, and the search may as
well not have run.** Yekutieli's hierarchical FDR tests a family only if its parent was rejected,
which keeps each family small enough for BH to have power while still controlling error over the
tree.

REQ-INF-004 rules out plain Benjamini–Yekutieli for the same reason from the other direction: its
harmonic penalty is about **10.9 at m=30,000**. That is not conservatism, it is **a gate nothing
passes, and a gate nothing passes teaches you nothing about the world.**

## Pruning before correction is the whole point of the ordering

REQ-INF-005 prunes ineligible pairs **before** any correction. A pair removed before correction
does not count toward `m`, so **pruning buys power for the tests that remain.** Pruning afterwards
would shrink the reported family while leaving the penalty already paid.

## The family size is frozen at test time

`benjamini_hochberg` takes `m` and never derives it from the list length. **Deriving it from
however many tests happened to run would let a crashed test silently make every surviving q-value
smaller.**

REQ-INF-009 closes the same door from the other side: the family catalog may not be authored or
modified after results are seen, because **that changes q-values without changing data, in
whichever direction the person doing it wants.** And a new metric moves family sizes at the *next*
run, never mid-run — a size that changes during a run makes the tests already performed
incomparable with the ones still to come.

## n is never shown alone

These observations are days in a row and they are autocorrelated. **A metric with ρ=0.6 over 400
days carries the information of about 100 independent ones.** So `n_eff = n(1−ρ)/(1+ρ)` is stored
on every estimate and rendered beside `n` always: *"n=400"* is true and misleading; *"n=400,
n_eff=100"* is neither.

An estimate without robust standard errors, or without a stored ρ and maxlags, **does not become a
findings row.** A naive standard error over autocorrelated days produces an interval that is
simply too narrow, and nothing downstream can tell.

**REQ-INF-026 is the sharpest of these.** A washout period without autocorrelation-robust
inference is forbidden, because discarding the days around a transition makes the remaining points
look cleaner and more independent than they are — and in the cited work that *raised* the
false-positive rate. **A procedure that looks like extra rigour while being the opposite is the
most dangerous kind.**

## The null is not a footnote

REQ-INF-034: the observed significant fraction may never render without the circular-shift null's
beside it. *"41% of specifications were significant"* sounds decisive until the shuffled data
produces 38%. **The null fraction is not a caveat attached to that number — it is the thing that
gives it a meaning**, so the renderer refuses to produce one without the other.

REQ-INF-038 applies the same logic to a whole run: **twelve discoveries against a null median of
three and a 95th percentile of seven is a result; against a null median of eleven it is a
Tuesday.**

## The lag profile

REQ-INF-035: five lags, always. **A single lag coefficient reported as "the effect" is a choice
among five, and the one chosen is the one that looked best.**

REQ-INF-036 catches the specific failure: significant at exactly one lag *and* sign-flipped at
another is **the signature of noise**, and returns INSUFFICIENT with `sign_unstable`.

REQ-INF-037 makes the curve the **default** output for a promoted finding, not an expandable
detail — **a single number with a curve hidden behind a click is a single number.**

## A test that could not fail

One test asserted `exceeds_null_p95 is False or ... is True`, which cannot fail and proved
nothing. Replaced with the real values on both sides of the threshold. Noted because it is the
same shape as the defects earlier reviews found: **a check that cannot fail is decoration**, and
it passes every suite it is in.

## Verification

23 tests. Requirements proven 468 → 490 (72%); REQ-INF unproven 63 → 41.
