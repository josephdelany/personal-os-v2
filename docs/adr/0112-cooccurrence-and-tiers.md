# ADR-0112 — Cross-lens links: registered first, or not computed at all

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-160..166 (§D.1), REQ-FIN-170..180 (§D.2)
**Implements:** B17 §D.1 and §D.2. Eighteen requirements, none previously proven.

## What this prevents

Spend can be correlated against sleep, mood, workouts, location, substances and productivity.
That is hundreds of implicit tests, and REQ-FIN-176 states the consequence in its own words:
**something will always look significant.**

A system that computes a correlation whenever two series happen to be available will therefore
produce a steady supply of striking, false findings, each arriving with a real number attached
and none of them marked. So a co-occurrence may only be computed for a hypothesis registered
**first**, the foreign key is NOT NULL by construction, and an unregistered pairing **aborts and
is logged** rather than being quietly skipped.

The logging is the part that matters. A pairing silently not computed leaves no trace, so **a job
fishing across every lens looks identical to a job doing nothing.** The log is what makes the
fishing visible.

## The ladder, and why its top rung is welded shut

| tier | what it takes |
|---|---|
| T0 OBSERVED | one dated fact, n=1, no pattern claimed, **no interpretation attached** |
| T1 DESCRIPTIVE | a count over a stated window, n ≥ 10, day-of-week reported |
| T2 CO-OCCURRENT | a rate difference across a pre-registered condition, n ≥ 20 in the **smaller** arm, day-of-week controlled |
| T3 CAUSAL | reserved, permanently unreachable |

T3 exists in the vocabulary so the ladder is honest about having a rung above T2. It is
unreachable because **observational spend data cannot support a causal claim no matter how large
n becomes**. `assign_tier` has no code path returning it, the dataclass raises on it, and a test
tries n up to 10,000 to confirm.

**A failing T2 is not silently demoted to T1.** They answer different questions, and presenting
an underpowered rate difference as a count would answer a question nobody asked.

**T0 carries no interpretation, explicitly.** One evening is an anecdote, and an interpretation
laid on top of n=1 is the whole of the harm this ladder exists to prevent.

## Day-of-week is controlled, not merely reported

REQ-FIN-177, and the reason is specific to Joe: **Friday is both the high-work day and the social
day.** Almost every apparent finding in this domain is day-of-week wearing a costume, and
controlling for it is what separates *"he drinks when he is stressed"* from *"both happen on
Fridays"*.

## `occurred_at`, never `posted_at`

REQ-FIN-162. Settlement is commonly the following day, so joining on it would attribute a
Thursday night to Friday — **silently moving every late-week evening into the weekend and
manufacturing the weekend pattern the analysis was looking for.**

## Cash is excluded from every denominator, and said so

REQ-FIN-179. Cash is not random missingness; it is concentrated on exactly the behaviour being
examined — a bar round, a split tab — so leaving it in the denominator deflates every rate
involving the thing most likely to be paid in cash. The exclusion is **stated in the rendered
sentence**: an excluded denominator nobody is told about is a rate that cannot be checked.

## Occasions, not dollars

REQ-FIN-166. **A $120 tab three people split is one occasion and $40 of Joe's money.** Visit count
is robust to price variance and to splitting; an amount is not, and reporting the $120 as the
alcohol metric would make a normal evening look like a heavy one. The amount is secondary and is
netted of inbound P2P transfers first (REQ-FIN-180).

## Missingness is counted independently of the prompt

REQ-FIN-165. The implied-but-unlogged count is derived from transactions, whether or not Joe ever
answers. **If it only existed when he replied, the days he ignored the prompt — the busiest ones,
the ones most likely to involve a bar — would look like days with no drinking.**

A date-only import is marked and barred from within-day analysis (REQ-FIN-163) and is **not**
counted as implied-unlogged: a missing window is not evidence of absence. The link is kept rather
than dropped, because the charge did happen.

## Verification

22 tests, no database and no clock. Not claimed: nothing is wired to real atoms — `core.atoms`
holds zero transaction atoms until the pending backfill is authorised, and the `cooccurrences`
table itself is not yet a migration.
