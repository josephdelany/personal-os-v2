# ADR-0127 — Five small contracts, five prefixes closed

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-ASK-001/024/026/029, REQ-ACT-004/007/008/010, REQ-SLP-020..023,
REQ-REC-013/015/016, REQ-TIER-023/025
**Result:** REQ-ASK, REQ-ACT, REQ-SLP, REQ-REC and REQ-TIER all reach zero unproven. **Ten of
fourteen prefixes are now complete.**

## Plan, then answer

REQ-ASK-001. **A model that plans and answers in one breath has already decided the answer before
the numbers arrive, and the plan becomes a justification written after the fact.** Two steps means
the plan is a commitment the deterministic layer executes — and if the numbers say something else,
they win. The guard rejects any "plan" carrying an answer.

## Informative missingness cannot be fixed by more data

REQ-ASK-026. If a metric is missing *because* of the thing being asked about — Joe does not log
dinner on the nights he drinks — then the observed rows are a biased sample of exactly the
question. **No amount of data fixes that, because the missing rows are the informative ones.** So
the answer states it and the tier caps at INSUFFICIENT.

REQ-ASK-029 is the counterweight, and it needed stating: **the medical boundary is easy to
over-apply.** *"Why do I feel flat on Thursdays"* is a question about logged behaviour, not a
request for a diagnosis, and refusing it would make the system useless for the thing it is
actually for.

## One instruction a day, pulled

REQ-ACT-008. **Two recommendations compete, and the one Joe acts on is whichever is easier rather
than whichever matters.** Pulled rather than pushed because **a pushed instruction arrives when
the system is ready, and the system is never the thing with the context.**

REQ-ACT-007 requires the **counter-frame**: *"22 minutes more sleep"* and *"22 minutes less of the
evening"* are the same number. **A recommendation that gives only the flattering reading is an
argument, not a measurement.**

## Four recovery measures, four coverages

REQ-SLP-020. HRV, resting heart rate, respiratory rate and wrist temperature have different
capture rates and different failure modes — the Watch stopped recording some before others. **A
combined recovery score built from one live measure and three lapsed ones looks identical to one
built from four.**

REQ-SLP-021 is the failure that produced the requirement: **an HRV from 2026-08-21 rendered
without its date reads as today's HRV**, and the reader has no way to know the Watch stopped.

REQ-SLP-022 returns a **stored** referral string, because a generated refusal is a generated
sentence about a medical topic — which is the thing being refused.

## Inferred inputs are not independent

REQ-REC-013. **Three events reconstructed from the same receipt are one observation wearing three
hats**, and an analysis that counts them as three has tripled its own confidence for free. The
function groups by lineage and reports the shared groups.

REQ-REC-015: *"we are not sure"* is not an answer. *"We are not sure, and a receipt timestamp
would settle it"* is one Joe can act on; *"nothing available would settle it"* is one he can stop
thinking about.

REQ-REC-016 refuses a single verdict, because the families fail for different reasons —
**contradictory evidence is a data problem, model unavailability is an ops problem, and
inferred-input propagation is a correctness one.**

## Two attachment rules

REQ-TIER-023: the adjustment set, the E-value and the negative-control result travel **in the
payload**, not behind a trace. **A CONFIRMED claim whose adjustment set is one click away is one
most readers will meet without it — and the adjustment set is what the word "confirmed" is
resting on.**

REQ-TIER-025: no frequentist confidence interval. **A 95% CI is not a 95% probability that the
value is inside it, and every reader outside statistics reads it as one.** Reporting the quantity
people already think they are reading is more honest than reporting the other one correctly and
being misread.

## Verification

18 tests. Requirements proven 564 → 581 (85%).
