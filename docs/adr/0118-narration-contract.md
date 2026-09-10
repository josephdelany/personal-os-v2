# ADR-0118 — The language layer's contract, enforced in both directions

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-NAR-001..006, REQ-NAR-010..015
**Implements:** B20 §A. Twelve requirements. Complements `narration.py`, which already carries the
tier-vocabulary linter.

## The arrangement

Every number in this system is computed by SQL or by a pure Python engine. The model's entire job
is to put those numbers into a sentence. RULE-09 and RULE-11 say so; this module is what makes the
saying enforceable, and it works in **both directions**:

- **What goes in** (REQ-NAR-001): a structured result object and nothing else — no atom rows, no
  photo references, no coordinates. **A model that receives raw rows will summarise them, and its
  summary is a computation nobody registered.** Refused *before* the call, because a bad input
  cannot be repaired once the sentence is written.
- **What comes back** (REQ-NAR-004/005/006/012): every numeral must already exist in the result
  object, every entity must already be named there, every causal link must already be an edge
  there.

## The fallback is a template, not an error

REQ-NAR-013. A refused sentence still has a perfectly good number behind it. **Showing an error
would hide a real answer because the prose around it was wrong**; showing the deterministic
template shows the same answer in plainer words. The violation row is written either way, so a
model that keeps failing is visible without the user paying for it.

## The judgements

**A literal numeral in template prose is refused at construction.** It did not come from the
result object and no slot binds it, so nothing can trace it — the same defect as a model-supplied
numeral, arriving through the author instead.

**Prose fields do not license their own numerals.** `scalar_values` excludes `note`, `caveat`,
`summary` and their kin, for exactly the reason migration 0059's SQL verifier had to: **a clause
stored in the result and compared against itself is self-certifying**, and a check that cannot
fail is decoration.

**"A registered rounding of one" is the requirement's own phrase**, and it is what lets a template
show `7.4` for a stored `7.4213` without opening the door to any convenient number. Ad-hoc
rounding is a computation: 7.44 as *"7"* is a different claim from 7.44 as *"7.4"*, and neither is
traceable unless the rule itself is stored.

**A numeral without its unit is a defect, not a shorthand.** *"Your sleep was 7.4"* is not a
shorter way of saying *"7.4 hours"* — it is a sentence the reader completes, and half of them
complete it wrongly. The unit travels with the slot, not with the template's prose.

**Entity checking compares against the result's own strings**, not a global list. The question is
not *"is this a real merchant"* but *"did the input mention it"*. A model that adds a plausible
entity is inventing a claim, and **plausibility is exactly what makes it dangerous.**

**A causal connective needs an edge in the input.** The model may say two things happened; it may
not say one happened because of the other. The edge is the thing that was computed, tiered and
registered — the sentence is not.

**`narration_log` is append-only.** A narration is evidence of what the system *said*, and a
system that can revise its own account of what it said cannot be audited on it.

## The contract is not a refusal machine

One test exists to prove that: a clean model sentence passes through **unchanged**, with no
violation rows. A guard that rejected everything would be trivially safe and useless, and the
first thing anyone would do is turn it off.

## Verification

17 tests, no model call: the model's output is passed in, and what comes back is what may be
shown. Requirements proven 399 → 408 (60%); REQ-NAR unproven 21 → 12.

Not claimed: no model narrator is connected. This is the contract that will bind one, and
migration 0059's `_ask_*` numeral verifier is the SQL-side equivalent for answers `ask` renders
without a model.
