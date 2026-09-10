# ADR-0108 — Presentation restraint: the one feature with measured evidence of harm

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-210..228 (§E)
**Implements:** B17 §E. Nineteen requirements, none previously proven.

## Context

Most design rules in this project are reasoned. This section is *measured*.

Pocheptsova Ghosh & Huang found that precise, frequent budget feedback caused overspending of
about **$40 (n=283, p=.002)** and **$32 (n=363)**. A **range** instead of an exact figure
attenuated the effect (n=198). Splitting a budget into sub-categories **increased** total spending
(n=251).

The mechanism is worth stating because it is counter-intuitive: **certainty removes the safety
margin.** When you do not know exactly how much is left, you keep a buffer. A precise app tells
you exactly how much room you have, and you spend into it.

So a running *"you have $312 left"* counter is not a style disagreement. It is **the single
identified feature in this entire system with measured evidence of causing harm**, and this module
exists so that a well-meaning surface cannot reintroduce it later.

## Decisions

### The banned-word list extends the reasoning layer's rather than copying it

REQ-FIN-218's ten words are REQ-NAR-023's seven plus `overspent`, `bad`, `should have`. So
`BANNED_WORDS` is built from `narration.MORALISING` rather than restated.

Two copies of a banned-word list drift, and the drift is invisible until a word ships on one
surface and not the other — **which is exactly what REQ-FIN-218's own 2026-08-24 note records
happening**, when `necessary` was present in one list and missing from the other. Importing makes
that failure impossible rather than unlikely.

### Blocking, not redacting

REQ-FIN-219 blocks publication and writes a `copy_violation` row. Silently deleting the offending
word would ship a sentence nobody wrote, and **the sentence would still be built on the judgement
the word expressed**. The copy has to be rewritten, not laundered.

### The width floor on a forward range

REQ-FIN-212 requires forward amounts to be ranges at least 20% of the midpoint wide. Without the
floor, `$311–$313` satisfies the letter and defeats the purpose: **a range that tight is a point
estimate with a hyphen in it.**

### The banned words are the small part

The ten words are the easiest rule to keep and the least of it. The rules that matter are
structural, and each of them **looks like good product design**:

| refused | why |
|---|---|
| running spent/remaining counter | the measured harm |
| any figure updating more than daily | frequency is half the mechanism |
| forward point estimate | the "you will spend $312" that removes the buffer |
| pie / donut / treemap / sunburst | a pie chart *is* a share-of-total; banning the word and allowing the shape is theatre |
| concentration as share of total | REQ-FIN-216 wants absolute amounts and counts |
| retrospective figure with no prior period | a figure with nothing beside it invites the reader to supply the comparison, and the one they supply is usually a judgement |
| an insight with no "not useful" control | without it, an unwanted insight can only be endured |

### A total that omits a dead account is not a total

REQ-FIN-225 fires at 35 days. This is not hypothetical here: **the bank CSV export died
2026-05-13 and a successor began 38 days later carrying a seventh of the value.** A total spanning
that boundary is arithmetically correct and materially incomplete, and the requirement forbids
presenting it as complete.

### Coping behaviour is not a malfunction

REQ-FIN-228 is contradicted-by-evidence, not merely unkind: the published finding is that making
purchase decisions restores a sense of personal control and measurably reduces residual sadness.
`check_alcohol_surface` rejects "problem", "bad habit", "relapse", "failure", "slip".

## Verification, including the negative result

21 tests. One asserts that **a realistic compliant review surface produces zero violations** — a
policy nothing can satisfy gets disabled, so it has to survive contact with an actual review page.

Run across every publishable string in every migration, the copy checker found **one** hit:
`'ingest_location: bad source'` in 0038. That is **out of scope** — REQ-FIN-218 governs words used
*"in reference to Joe's spending"*, and this is an error message about a data source. Recorded
rather than silently ignored, because it is the same scope lesson as ADR-0107's linter: a checker
run outside the boundary its requirement names produces noise, and noise gets checkers deleted.

**On finance copy specifically: zero violations.** That is the honest result — there is very
little published finance copy yet, so this is a policy established before the surfaces exist
rather than a cleanup of surfaces that already do.
