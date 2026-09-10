# ADR-0117 — The hard cap is the cost control, not an obstacle to it

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-CAP-030..046 (§B.1, §B.2, §B.3), REQ-CAP-100..107 (§G.2)
**Implements:** B16's model, budget and refusal sections. Seventeen requirements.

## The shape of the cost control

Workers AI's free allowance is 10,000 neurons a day, and RULE-28 forbids billing on overage.
REQ-CAP-042 makes the hard fail at 10,000 **the enforcement mechanism** for the $0 constraint
rather than a nuisance to route around: no payment method is attached, so the account cannot spend
money even if this code is wrong.

That is the right shape. **A soft check in application code fails open the day somebody edits it;
an account with no payment method fails closed forever.** The code-level checks below are for
graceful behaviour, not for solvency.

## The 9,000 / 10,000 split, and why the margin is reserved

The soft ceiling is 9,000 and the thousand above it is reserved **exclusively** for re-processing
already-deferred captures (REQ-CAP-039).

Without that reservation, **a busy day starves yesterday's backlog permanently.** Every new
capture competes with the deferred ones on equal terms, and the deferred ones lose every race —
they are older, nobody is standing over them, and their audio is sitting on a phone. The margin
is the only thing that guarantees the backlog eventually drains.

REQ-CAP-040 completes it: on a new day, deferred captures run **first, oldest first**. Oldest
rather than newest because the person who recorded it has already moved on, and the oldest is the
one closest to being forgotten.

## A refusal is never a deletion

When the allowance is exhausted the audio is kept, the status becomes `deferred_budget`, and the
capture is retried tomorrow. Nothing is truncated, overwritten, or marked complete (REQ-CAP-041,
043). **A capture lost to a budget ceiling would be lost to an accounting decision, which is the
least defensible reason to lose anything.**

## Empty is not the same as failed, and neither is complete

REQ-CAP-045. A transcript of `""` for two seconds of audio is plausibly silence and is a real
empty capture. The same for eleven seconds is a transcription that did not work, and treating it
as a successful empty capture would **file real speech as nothing** — the failure mode with no
symptom, because the row looks fine.

## The parameter that matters most

`condition_on_previous_text: false` (REQ-CAP-033) looks like a tuning detail. With it **on**,
Whisper carries context between segments and will happily continue a sentence it hallucinated, so
**one bad segment contaminates the rest of the transcript.** Asserted on every request rather than
set once in a config.

`vad_filter: true` and `language: "en"` are asserted the same way, because a request built by
merging dicts is a request where a caller can quietly override one of them.

## iOS dictation costs nothing

REQ-CAP-046. Re-transcribing dictated text would spend neurons to reproduce text the phone
already produced — against the budget that is the binding constraint on the whole subsystem.

## §G.2 — the seven things capture may never do

Enumerated as data with their requirement IDs, so a violation is reported by ID rather than
described. REQ-CAP-101 is the positive form of the same idea and is tested by **simulation
rather than inspection**: with the resolution service, the transcription service, the extraction
service and the database all unavailable, the capture still completes and still queues, and the
function that does it touches no network, no database and no model.

## Verification

21 tests. Requirements proven 385 → 399 (58%); REQ-CAP unproven 48 → 34.

Not claimed: no Shortcut, no ingest endpoint and no Workers AI call exists. `core.neuron_ledger`
(migration 0052, deployed) is the table these estimates are written to; nothing writes to it yet.
