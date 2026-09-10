# ADR-0116 — Losing a capture is the worst outcome in this subsystem

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-CAP-019..029 (§A.5, §A.6), REQ-CAP-080..086 (§F.1)
**Implements:** B16's resilience and attention-budget sections. Eighteen requirements.

## The asymmetry these rules exist for

A transaction can be re-imported from a CSV next month. A HealthKit sample is still on the watch.
**A spoken sentence about what Joe just ate exists exactly once, for about four seconds**, and if
the network is down when he says it there is no second copy anywhere in the world.

Every rule below follows from that.

## §A.5 — the failure is silent, local, and Joe never sees it

**REQ-CAP-019 forbids the error dialog**, and that prohibition matters more than it looks. An
error at the moment of capture teaches Joe that capturing sometimes fails, and **the lesson he
draws is to stop bothering.** A queue he never sees teaches him nothing, which is correct: nothing
went wrong that he can act on.

**A line leaves the queue only on 200/202** (REQ-CAP-020). Removing on send rather than on
acknowledgement loses exactly the captures that were hardest to make — the ones sent while the
connection was bad.

Stop-on-first-failure is implemented but **deliberately not the default**: a single poisoned line
would otherwise block every capture behind it forever. The requirement asks for order and
acknowledgement, not for a barrier.

**`received_at` may bucket nothing** (REQ-CAP-021/022), and the check *raises*. A capture queued
Tuesday night and replayed Wednesday morning is a **Tuesday** capture. Bucketing by arrival moves
every offline capture forward a day — and offline captures are not random. **They cluster where
the signal is bad, which for Joe means exactly the places worth knowing about.** The resulting
distortion is invisible in the output, which is why this raises rather than warns.

**The unsynced indicator states an exact count** (REQ-CAP-024). *"3 entries not yet saved"* is
actionable; *"something is unsynced"* is anxiety with no next step.

## §A.6 — 202 even when enrichment failed

**The capture is safe the moment it is stored.** Transcription and extraction are downstream and
retryable, so REQ-CAP-025 returns 202 to the Shortcut regardless. Surfacing a downstream failure
would report an error for something that already succeeded, and **the Shortcut's only available
response would be to make Joe do it again.**

A store failure is still a 500 — the 202 is about enrichment, not about losing the capture.

**Seventy-two hours pending becomes a review item, not another retry** (REQ-CAP-027). Retrying
forever hides a provider that has changed its contract. Three nightly attempts is enough for a
transient outage and few enough that a real breakage surfaces **while Joe still remembers the
captures involved.**

**One push, not a stream** (REQ-CAP-029). A repeating alarm about a job Joe cannot fix from his
phone is a notification he turns off — and then he misses the next one that matters.

## §F.1 — the attention budget

Every limit is small enough to look arbitrary and they share one justification: **a screen that
asks for six things gets four answered and then abandoned, and the abandonment is permanent.**

**REQ-CAP-084 is the most interesting of them.** The evening screen must show the day's captured
meals, workouts, locations, mood and sleep *before* any field requiring recall. Recall is
expensive and inaccurate; showing the day first turns *"what did you do"* into *"is this right"* —
a different and much cheaper task.

**Review items are ordered by interval width** (REQ-CAP-085), because interval width *is* the
uncertainty: the item Joe can most improve by answering is the one the system is least sure about.

**Leaving the review screen is an answer** (REQ-CAP-086). Rows keep their provenance and interval
and are never re-raised. Re-prompting tomorrow converts a review list into a backlog, and **a
backlog is a thing people stop opening.**

## Verification

22 tests, no network and no clock of its own — every function takes `now` explicitly.
Requirements proven 367 → 385 (56%); REQ-CAP unproven 66 → 48.

Not claimed: no Shortcut, no PWA and no ingest endpoint exists. This is the behaviour they will
be held to, and the Shortcut in particular remains uninstalled (a standing Joe item).
