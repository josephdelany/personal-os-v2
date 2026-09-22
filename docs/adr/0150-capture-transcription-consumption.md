# ADR-0150 — Private transcription consumption with immutable results

Status: locally verified foundation; deployment and orchestration open.
Date: 2026-09-22. Implements the storage approval in ADR0148; no new vendor or dependency.
Requirements: REQ-CAP-025/026/030..036/038/043/045; RULE02/12/29.

A private preparation stage binds a request UUID, capture, expected processing head,
model/kind, canonical payload digest, duration and estimated cost. It stores no second
copy of audio. Duration comes from the immutable capture payload. The media adapter
must still prove that its supplied audio belongs to that capture; accepting a prepared
payload is not evidence of Storage acquisition or media-source authentication.

The private consumer verifies the exact request and response digests against the
isolated dispatcher's committed receipt, plus capture/model/kind/cost. Valid returned
text and segment metadata append with a `transcribed` processing event in a savepoint.
Any failure rolls back both writes even if the caller catches the exception. The
caller still owns the outer transaction and must commit before displaying/exporting.
No raw row is updated. Replays return the stored outcome; changed replays refuse.

`transcribed` is an intermediate state, not full enrichment. Extraction and atom
persistence must finish before `enriched`. The current transcript view selects only
applied, valid transcription outcomes. Later stale responses remain history; later
extraction failure does not erase a usable transcript. The work queue includes initial
received captures and retries, and routes captures with usable text to extraction.
Photo, dictated text, extraction execution and actual nightly orchestration remain open.

Empty text for audio longer than two seconds remains pending with `empty_transcript`
and atomically creates an immediate owner-visible review. Existing permanent capture
dismissal and one-review-per-pending-episode semantics remain in force. Invalid shape
or timing produces an explicit pending failure; it never produces current text.

Independent review found that generic dispatcher errors lost HTTP status. Dispatch
now appends only bounded status metadata (300..599) after error settlement and before
its commit. The isolated role owns that RPC, has no private result reads, and cannot
attach a status to a successful request. Consumption matches the full failed receipt
before preserving the status as last_error. A lost settlement acknowledgement exports
no confirmed status receipt; raw error bodies and URLs remain private.

The audio-cost owner is now pure `lib.model_contract.audio_neurons`, reused by egress,
the older budget helper and preparation. It retains the unrounded float estimate;
attempt storage uses its decimal string, matching JSON transport/reservation values.
This removes divergent per-consumer rounding and is tested at one second, not only
whole audio minutes. The configured estimate is not a measured vendor bill.

Cloudflare's [model contract](https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/)
was checked September22: it documents language, boolean VAD/previous-text options,
and returned text/segments. The request adapter/live model behavior is still unverified.
No provider call, account change, media upload/delete, production migration or deployment
occurred. Test fixtures live only in disposable schemas and roll back; connection
probes establish call ordering, not actual post-commit durability or concurrency.

## Verification

16 capture-result SQL cases passed (10.10s);56 processing/budget/capture cases passed
(33.42s) before the final pagination case; full SQL887 passed/1 skipped (265.83s).
Full sanctioned no-DB suite1093 passed/719 skipped (160.36s), zero failures/errors.
That collection predates the final SQL-only pagination case; full SQL includes it.
All79 migrations/719 statements applied from empty;43 layout checks passed.
The feature ledger remains14/15; generic RULE04 remains pending. All disposable
servers stopped. Independent review accepted the repaired behavior and private CLI.

Review also found oldest100 failed items could starve the rest. Queue output now
includes a validated keyset cursor and fixed insertion cutoff. A103-item regression
includes unchanged failed heads, tied capture times, a late arrival, and cursor
replay. Eligibility can change between pages: this is neither claiming nor evidence
of commit visibility. Actual orchestration still must finish each page before
advancing and preserve/recover its cursor after interruption.

The new foreign keys caused an existing TRUNCATE test to stop before its append-only
trigger. The test now attempts TRUNCATE CASCADE and still requires the explicit
append-only error, exercising the invariant rather than accepting any failure.
No integrity assertion or production permission was relaxed.
