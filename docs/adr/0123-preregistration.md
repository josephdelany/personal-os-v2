# ADR-0123 — Pre-registration is arithmetic, not etiquette

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-100..114 (§C), REQ-INF-500..508 (§G.1)
**Implements:** the Python side of what migrations 0010 and 0012 enforce in the schema.
Nineteen requirements.

## The premise

**The difference between a discovery and a story is entirely a matter of when the claim was
written down.**

Every part of an analysis — the lag, the direction, the transformation, the adjustment set, the
test statistic — can be chosen *after* seeing the data, and **each choice is defensible on its
own.** Choosing all of them after the fact is how a null result becomes a finding without anybody
lying.

So the register fixes those choices with `preregistered_at`, `confirmation_data_from` is set to
`now()` at registration, and after that the arithmetic does the work: the confirmation job can
only read observations from after the moment the claim was fixed.

## Both clocks, or neither

REQ-INF-104/105 is the subtle one. A row about last Tuesday that arrived today is **not**
post-registration data — it is old data that showed up late, and **a backfill can deliver
thousands of them at once.** Filtering on `subject_day` alone would let a single import silently
supply the entire confirmation window.

A leaked row **aborts** the confirmation. It is not downgraded to a weaker claim, because the
weaker claim would still rest on data the hypothesis may have been mined from.

## The E-value question, asked honestly

REQ-INF-112 caps a finding at PROMOTED when the E-value at the interval limit nearest the null is
below 1.5. That statistic asks the honest question: **how strong would an unmeasured confounder
have to be to explain this away?** Below 1.5 the answer is *"not very"*, and no amount of process
turns that into a confirmed observational finding.

The same cap applies when no minimal sufficient adjustment set exists — because then **what was
adjusted for is not what the DAG says must be.**

## A refutation is surfaced, not deleted

REQ-INF-111. **A register that quietly drops its failures reports a success rate of 100% and means
nothing.** The refutations are the only evidence that the confirmation gate does anything at all.

## Nothing is imputed

REQ-INF-110. **An imputed value is indistinguishable from a measured one once it is in the
matrix**, and the imputation model's assumptions become the finding's assumptions without
appearing anywhere in its provenance.

## §G.1 — the registry drives everything

**No hardcoded variable pairs** (REQ-INF-500). A hardcoded list stops matching the data the first
time a metric is added, and **the mismatch is silent** — the search simply never looks at the new
metric.

**An observation whose metric has no registry row is refused** (REQ-INF-502), not stored and
flagged. A metric with no registry row has no unit, no state class, no plausible range and no
staleness rule — nothing downstream can decide what to do with its values, **and the row would sit
there looking like data.**

**Exactly three interfaces** (REQ-INF-504). A component that reads a table directly can see a
column the panel deliberately does not expose — a raw row, an un-superseded value, a coordinate.

**A fired negative control suppresses the whole run** (REQ-INF-507), not just the offending
finding. **The pipeline is finding effects where there cannot be any, and there is no reason to
believe the other findings from that run are different in kind.**

**REQ-INF-508 is an artifact detector.** Shift the exposure into the *future* and see whether the
effect survives. If tomorrow's caffeine predicts today's sleep, the association is not caffeine
acting on sleep — **it is something slower moving both, or a shared trend nobody removed.**

## One rename

`testable_hypotheses` became `hypotheses_from_registry`. **pytest collects any imported callable
whose name begins with `test`**, so the original produced a baffling *"fixture 'registry' not
found"* error in an unrelated file. A name that breaks the test runner wherever it is imported is
worth changing once.

## Verification

18 tests. Requirements proven 490 → 509 (74%); REQ-INF unproven 41 → 22.
