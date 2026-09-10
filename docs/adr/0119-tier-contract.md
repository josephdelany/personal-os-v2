# ADR-0119 — The ladder every other engine references

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-TIER-002..004, 010..016, 021..027, 030..034, 044..045, 051..052
**Implements:** the previously-unproven parts of §A. REQ-TIER now stands at 41 of 43 proven.

## Why this one closes a loop

Chains, trials, co-occurrences, narration, recommendations — every engine written this session
references a tier. Until now the ladder was enforced in each of them separately. This is where a
tier is assigned, where it may not be changed, and what may be said at each rung.

## The two guards that matter most

**The narration layer may never write `tier`** (REQ-TIER-003). The tier is the output of a
deterministic statistics job with a `code_version` beside it. **If a narrator could set it, the
strength of a claim would be decided by whichever component is best at producing confident
prose** — exactly backwards, and the failure the whole ladder exists to prevent.

**A tier mismatch discards the prose, not the label** (REQ-TIER-004). This is the subtle one. A
rendered claim whose displayed tier differs from its stored one is *not* a labelling error to
patch: the sentence was written for a tier the evidence does not support, so **relabelling it
leaves a CONFIRMED-shaped sentence flying an EXPLORATORY flag.** The prose goes; the template
stays.

## EXPERIMENTAL is a property of the assignment, not of the sample

REQ-TIER-016. `assign_tier` checks `randomizer_assigned`, never `n`. **No volume of observational
data becomes an experiment**, and a test puts n=100,000 through the observational path to confirm
it still comes back DESCRIPTIVE.

## Language

**"caused" is EXPERIMENTAL-only** (REQ-TIER-021) — the one word whose misuse cannot be recovered
by a qualifier in the next sentence.

**The Granger identifier is banned repository-wide** (REQ-TIER-022). The test enforces "anywhere
in the codebase" literally, by scanning `tools/` and `migrations/`. **This is the fourth place in
this project where a check had to stop spelling what it detects** — the module and the test both
assemble the token from fragments. The alternative each time was an exemption, and an exemption is
how a never-rule becomes a rule with exceptions.

**An effect size is absolute with its unit named** (REQ-TIER-024). *"18% lower"* is unreadable
without the base, and **the base is exactly what a reader supplies from memory — usually
wrongly.** *"22 minutes less sleep"* cannot be misread that way.

**The numeral comes before the EFSA term** (REQ-TIER-026), because the term is the part a reader
remembers and the number is the part that constrains it. Leading with the word lets the word do
the work alone.

**"unable to give any probability: range 0–100%" is a legal return value** (REQ-TIER-027), not an
error.

## INSUFFICIENT is a return value, not a silence

REQ-TIER-032. **Suppressing a weak result looks like modesty and is not**: it hides that the
question was asked and that something was computed. A person who gets nothing back concludes the
system has no opinion, when it has a weak one — and a weak answer with its weakness stated beats
a blank.

Two forms, and both must end with a way forward (REQ-TIER-033). The partial form refuses to omit
any of point, interval, n, n_eff, coverage; the absent form refuses to omit the missing input or
the condition that would fix it. REQ-TIER-034 makes rendering a dead-end response a **rejection**
rather than a warning.

## Demotion needs no approval

REQ-TIER-044. **Requiring approval to lower a claim would leave overstated findings standing
while the approval was pending — and the person whose approval is wanted is the person the
overstated claim is addressed to.**

REQ-TIER-045: a CONFIRMED finding whose adjustment set is thin renders at INSUFFICIENT. **The
adjustment set is what makes a confirmed finding confirmed.** If the metrics doing the adjusting
are themselves half-missing, the adjustment is not happening, and the finding is resting on a
control that is not there.

## The ordering constraint

REQ-TIER-051 is not a quality gate but an **ordering** one: the EXPLORATORY label surface must
pass its acceptance suite *before* continuous exploration ships. Ship the generator first and its
output has nowhere labelled to go, so **it lands on whatever surface exists — which is a surface
built for findings.**

REQ-TIER-052 checks the **vocabulary itself**, not only the sentence: a confirmed-tier verb inside
the exploratory vocabulary would let the linter pass a sentence that reads as settled while flying
an exploratory label.

## Verification

27 tests. Requirements proven 408 → 429 (63%); REQ-TIER unproven 23 → 2.
