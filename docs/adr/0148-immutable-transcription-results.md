# ADR-0148 — Immutable transcription results

Status: accepted by Joe, 2026-09-22. Resolves OQ84; extends ADR0144.

Joe approved the exact OQ84 replacement for REQ-CAP-034. Returned transcript text
and segment timings are appended as capture enrichment results linked to the raw
capture and processing attempt. Current results follow effective processing history;
old/stale attempts remain available as history and cannot replace a newer effective
result. Raw captures are never updated.

The separate result consumer must validate and persist results atomically with
effective processing status. This does not permit models to provide measured
nutrition values, delete media, change retention, or deploy without authorization.
Failure stays explicit/pending; accepting this storage contract is not evidence of
implemented or deployed transcription. Implementation can now proceed.
