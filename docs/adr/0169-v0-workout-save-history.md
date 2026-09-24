# ADR-0169 — V0 workout entry and history

Date: 2026-09-24. Status: accepted; local implementation verified, activation pending.
Requirements: WKT001–007/018/020, CAP005, RULE02/03/05/06/10/29.
Scope: the approved daily V0 backend, not coaching or derived strength analysis.

## User outcome

The owner can log an individual strength set, receive a durable saved receipt,
read it on its day and correct it without erasing earlier evidence. Preserve
exercise text, stated load/unit, repetitions, optional RPE and event time.
An empty day means no entries, not zero exercise. Imported workout sessions
remain distinct from logged strength sets; no inferred session grouping.

## Implementation boundary

Reuse the owner-authenticated V0 save/read and immutable ledger pattern, with
UUIDv7 request identity and a typed unique predecessor. Each set is individually
addressable. Exact retries return the original receipt; conflicting reuse and
stale corrections refuse. Raw capture and ledger insertion are atomic.

Retain stated kg/lb units and deterministic canonical load in the existing
strength_load_lb unit. Explicit external-load, bodyweight and assisted modes
preserve what was recorded. Do not invent body mass, effective resistance or a
zero load for bodyweight. An assistance amount is not a positive external load
available for e1RM. Missing RPE remains null. When supplied, RPE uses the existing
0–10 half-step subjective scale, never the new 1–10 check-in definitions.

The legacy extractor accepts only weight_lb, lacks movement-mode support and
uses a textual evidence-span match to find correction targets. New captures
must use a distinct versioned kind until a tested adapter can preserve these
contracts. Save/read must work independently of derived analysis. Do not mark
WKT005/006 or full strength processing complete from a raw entry ledger alone.
Retain unresolved exercise names rather than inventing canonical identities.

Joe explicitly authorized V0 workout text entry. Reconcile WKT002 and the
workout_contract capture-path validator narrowly for that named text path;
retain the prohibition on browser microphone/camera capture. This is not an
implicit general PWA media permission or reinterpretation of manual_logger.

## Acceptance required before integration

Exercise the actual owner RPCs for saved/read/retry, invalid input, anonymous and
nonowner refusal, kg/lb fidelity, bodyweight and assisted distinctions, null
versus zero, correction and day movement, immutable raw history, atomic rollback,
and isolation from legacy extraction. Test the capture-path scope explicitly.
Include deploy/activation instructions and example caller payloads. Full gates
and independent review remain required. Real-account activation is separate.

Read-only assessment of current code confirmed these gaps; no implementation,
new measurement definition, deployment or atom-shape ruling is claimed here.

Implementation0093 records both canonical external load and canonical assistance
separately. Only external load uses the existing strength_load_lb bound; it does
not silently redefine assistance as that metric. Initial34SQLpass and19purepass.
Review caught mutable registry validation before saved receipt lookup. Fixed by
checking immutable exact retries first under the identity lock; new entries still
validate. Expanded40SQLpass1.97s includes changed-registry replay/new refusal,
mode correction and ledger access/immutability. Re-review accepted. FullSQL1162passed1skip462.59s; writer1451passed989skip
201.25s; chain92/971; layout43pass. Four spine invariants pass; generic RULE04
pending. Merged43unverified skips (41production,2NumPyro). Evidence/hashes:
.local/evidence/v0-workouts/. No production activation or real-account claim.
