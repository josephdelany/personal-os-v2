# ADR-0121 — A claim that commits to nothing cannot be wrong

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-300..307, 320..331 (§E)
**Implements:** B19's scored-forward-prediction and auto-demotion machinery. Eighteen
requirements. Scoring itself lives in `calibration.py` and is imported rather than restated.

## The premise

**A claim that never commits to anything observable cannot be wrong, and a system full of
unfalsifiable claims looks exactly like a system full of correct ones.**

So the moment a finding reaches PROMOTED it must also insert a row saying what it expects to see
and when — **in the same transaction**, not shortly after, so there is no window in which a
promoted finding exists with no commitment attached.

A finding at PROMOTED or above with no prediction is **refused on every surface**. Not warned
about: refused. **The absence is not a display bug; it is the claim having no exposure to being
wrong.**

## The parameter that does not exist

REQ-INF-322 says the layer "SHALL NOT provide any interface that suppresses, defers, or
overrides" a demotion. So `auto_demotion` has no `force`, no `skip`, no `defer`, no
`reason_to_keep` and no `approve` — and **a test inspects its signature and fails if any of them
appears.**

The reasoning is not abstract: **the moment such an argument exists, the demotions that get
suppressed are exactly the ones about findings somebody liked.** The absence of the parameter is
the requirement.

## Resolution reads the past, not the present

REQ-INF-307. A prediction resolves against the feature state reconstructible from its own
`feature_snapshot_hash`. Resolving against today's state would let a later correction change
whether a past prediction came true — **which makes the track record a function of the present.**

REQ-INF-328 completes it: no stored score is recomputed under a later model version. **A track
record that improves when the model changes is not a track record, it is a redraft.**

## Unresolvable is not false, and this is not hypothetical

REQ-INF-329/330. Joe's Watch stopped on **2026-08-21** and twenty-four predictions about `rhr`,
`hrv_sdnn` and sleep came due afterwards with nothing to resolve against.

Counting those as wrong would compute a Brier score saying the system is badly calibrated, when
what actually happened is that **an instrument stopped** — and the demotions that followed would
look earned. So an unresolvable prediction is excluded from scoring, and above a **25%**
unresolvable rate the system reports **its own calibration at INSUFFICIENT** and says its track
record cannot currently be assessed.

## Miscalibration widens rather than hides

REQ-INF-325/326. A bucket where *"70% likely"* comes true half the time is not a bucket to
suppress — **it is a bucket whose numbers mean something different from what they say.**

So the interval widens by the observed gap, the EFSA verbal term is downgraded to the band
matching the **observed** frequency rather than the nominal one, and the surface states why. The
claim survives; its confidence does not. A test asserts that a 70%-nominal / 50%-observed bucket
renders as *"about as likely as not"*.

## Recommendations carry their own prediction

REQ-INF-331, the recommendation-side analogue of REQ-INF-301. **Advice that commits to nothing
can never be found wrong — and advice is the output with the most direct effect on what Joe
actually does.**

## Verification

22 tests. Requirements proven 450 → 468 (68%); REQ-INF unproven 81 → 63.
