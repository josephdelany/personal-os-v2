# ADR-0128 — The model is an improvement, not a dependency

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-NAR-024, 026, 030..039
**Result:** **REQ-NAR reaches zero unproven** — eleven of fourteen prefixes complete. Only
REQ-FIN (36), REQ-CAP (34) and REQ-INF (22) remain.

## No error path for the model being down

Every number in this system is computed deterministically; the model's contribution is the
sentence around it. So `render()` has **no error branch** for model unavailability — it has a
template path, and **the template path is the default the model improves on rather than a
fallback it replaces.**

A surface that goes blank when the model is unavailable has made the model load-bearing for facts
it did not produce — **and it will go blank on exactly the day something is worth reading.**

## The chart goes below the verdict, and a candidate gets none

REQ-NAR-034. Above the text, a chart is read first, and **a reader who has already formed a view
from the shape reads the sentence as confirmation.** Below, the sentence sets the claim and the
chart shows the evidence — the order in which they were actually produced.

REQ-NAR-035 goes further for a CANDIDATE: **a chart is the most persuasive object this system
renders.** On an unconfirmed candidate it converts *"a generator flagged this"* into something
that looks measured, **and no label under it undoes that.**

## The half of REQ-NAR-026 that gets forgotten

Not re-proposing a declined suggestion for 7 days is the obvious half. The other is that **a
skipped day is never mentioned** — *"you did not log yesterday"* is a reproach dressed as a status
line, and it is the sentence most likely to end the logging altogether.

## Where RULE-25 draws its line

REQ-NAR-024 bans a moralising judgment on a rating, total or behaviour — but **permits a
decision-under-uncertainty recommendation carrying its tier and interval.**

The distinction is real and worth keeping: *"you spent too much"* is a verdict on Joe, while
*"consider moving caffeine earlier (DESCRIPTIVE, 22 ± 18 min)"* is an option with its evidence
attached. **Banning both would leave the system unable to suggest anything at all.**

## The vocabulary comes from the table

REQ-NAR-039. The recommendation verbs are the `recommendation` row of `tier_vocabulary`, passed
in — never a hardcoded list. **A hardcoded list cannot be corrected without a deploy, and the
wording of a recommendation is precisely the thing Joe is most likely to want corrected.**

A recommendation with *no* hedged verb is refused too, not only one with a forbidden verb: a flat
imperative with an interval attached is still an instruction.

## Three load-bearing words in the export rule

REQ-NAR-037: complete, free, synchronous. **A paid export is a hostage; a deferred one is never
checked; and one missing `tier_history` cannot answer "what did the system claim before it changed
its mind" — which is the question an export is for.**

## A defect this module's own test found in it

`check_recommendation_numerals` parsed *"22 minutes (4-40)"* as `4` and **minus 40**, and flagged
its own example sentence as containing an invented number.

**The hyphen in a range is not a minus sign**, and a hyphenated range is exactly how every
interval on these surfaces is rendered. The fix is a lookbehind: a sign only counts when it is not
preceded by a digit or a decimal point. A test now pins both the range and a genuinely negative
effect size.

This is the same shape as the numeral-verifier defects the earlier reviews found in migration
0059 — **a checker that is subtly wrong about what a number is will reject correct output and be
switched off for it.**

## Verification

18 tests. Requirements proven 581 → 593 (87%). REQ-NAR 12 unproven → 0.
