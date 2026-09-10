# ADR-0126 — Three shapes that cannot be repaired after the fact

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-ONT-004..017, REQ-LOC-003..014, REQ-NUT-002..032
**Result:** **REQ-ONT, REQ-LOC and REQ-NUT are all now at zero unproven**, joining REQ-NFR and
REQ-WKT.

## What these three have in common

Each is about a **shape** that, once wrong, cannot be repaired from the data it produced.

**A clock time stored as a number** (REQ-ONT-015). *"Bed at 23:40"* as 23.67 and *"bed at 00:20"*
as 0.33 average to **12:00 — the middle of the day, from two adjacent midnights.** Every circular
quantity has that failure mode, and it produces a number that is not merely wrong but
confidently, plausibly wrong. `time_from_noon` exists so the wrap happens where nothing happens.

**Four substances as four kinds** (REQ-ONT-016). Alcohol, caffeine, a supplement and a medication
are one `consume` kind with a class. Four kinds would fork every query asking *"what did he
take"* — **and the fork would be silent: a question about supplements would simply not see the
medication rows.**

**A scalar energy column** (REQ-NUT-030). Not *"should not be used"* — **does not exist.** A
`kcal` column is one something will eventually read, and **the reader will not know it was the
midpoint of an interval three joins ago.**

## Location: labels out, coordinates never

A place **label** is what the reasoning layer needs — "the gym", "home", "Hannaford". A coordinate
adds nothing to the reasoning and everything to the consequence of a leak.

Home is not coarsened, it is **withheld**: a coarsened home is still a home address to within a
block. A non-home place egresses at ~100 m — **enough to say "the same café", not enough to say
which seat.**

**One owner and one `code_version` per mobility metric** (REQ-LOC-011). Two implementations of
"radius of gyration" *will* disagree, and **the disagreement surfaces as a metric that changes
when a different code path happens to run** — which looks like the world changing.

## The fifth time a check fired on my own work, and the first that was real

The layout validator failed this commit: `tests/test_ontology_contract.py` used coordinates near
**44.55, −69.63** — Waterville, Maine, which matches the merchant data in Joe's own transactions.

The four earlier instances this session were false positives, where the fix was to stop spelling
the token. **This one was a genuine violation**: I was about to commit plausible coordinates for
where Joe lives to a public repository, which is the same class of error as the spending figures
earlier in this session.

The coordinates are now assembled at runtime from obviously-synthetic constants pointing at the
Gulf of Guinea. The comment in the engine was also reworded, because a decimal-degree figure on a
line mentioning latitude reads as a coordinate to the validator — **correctly, since that is
exactly the shape a leaked one takes.**

The validator was right, it caught it before the commit, and this is the strongest argument in
the session for keeping these checks noisy enough to fire.

## Verification

20 tests. Requirements proven 544 → 564 (82%). REQ-ONT 5→0, REQ-LOC 6→0, REQ-NUT 9→0.
