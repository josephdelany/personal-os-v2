# Capture runtime — implementation and activation checklist

Current local foundation: ingress936f5cd ancestry plus uncommitted private media read
(ADR0151). This is a runbook under construction, not an activated capture service.
Production authentication is held per NEXT_SESSION; do not retry the unchanged secret.

## Process capabilities

| Process | Required capability | Must not inherit |
|---|---|---|
| Private preparation/consumption | Direct private DB login; fixed Supabase Storage origin and anon API key; Storage read JWT restricted to private captures | CF_API_TOKEN, MODEL_EGRESS_DB_URL |
| Model dispatcher | Direct model_egress DB login; Cloudflare account/token | SUPABASE_DB_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_READ_JWT |
| Future supervisor | Validated stage messages and scheduling state | A combined private/model credential environment |

The supervisor must not solve process separation by holding every secret itself.
Provision separately scoped workers and validate effective role/Storage permissions
before activation. Environment guards are tested local refusal mechanisms, not proof
of an OS sandbox or deployed permission boundary. No generic SQL reaches the model.

## Stages already implemented

`tools.capture_transcription prepare-media REQUEST_ID CAPTURE_ID` reads the immutable
voice capture reference and digest, downloads only its private captures object and
builds the fixed transcription payload. It commits the attempt before emitting JSON.
The capture path is UUID/filename. Missing hash refuses; never modify a raw row to add it.
The internal `prepare` primitive accepts already prepared JSON and is not the media
source-authentication boundary; the media runner must use `prepare-media`.

`tools.model_egress` consumes one prepared JSON request on stdin in its isolated
process. It commits the shared reservation before sending, then commits a response
receipt or bounded HTTP failure metadata. Do not publish stdout/stderr as CI artifacts:
success data is private; error output exposes only controlled codes/status.

`tools.capture_transcription consume` accepts the correlated response, verifies its
settled receipt and stores the immutable transcript/status together. `fail` records
budget/provider failures, including matched HTTP status. `readback CAPTURE_ID` returns
current processing state and usable transcript. A transcribed capture still needs
extraction; it is not enriched or a stored atom merely because the transcript exists.

`queue` returns items and a next_cursor. Continue every page, even when older items
fail. Preserve the cursor only after its page's outcomes are handled. A new run begins
without a cursor; retries must not loop forever over page1. Pagination does not claim
work or solve concurrent workers; durable run/attempt supervision remains to be built.

## Deadlines and recovery

Private media retrieval rejects redirects, limits reads to50MiB and checks SHA256.
The socket timeout is30s; a dedicated POSIX main-thread45s signal timer also surrounds
the acquisition and hash check. Pre-existing signal timers cause a fail-closed refusal.
The original handler is restored. Non-POSIX/non-main-thread callers refuse.

This is not a hard process-kill guarantee for every native-library stall. The future
supervisor must terminate/reap stalled stage processes under an overall deadline,
retain a stable request identity, and reconcile uncertain commits before deciding the
next action. Never treat a lost acknowledgement as proof that a write rolled back.

## Required before activation

- Implement authenticated upload issuance and an append-only hash/object receipt,
  private bucket policies and replacement refusal. Provision scoped credentials via
  normal secrets configuration; no secret belongs in chat, source or a Shortcut.
- Generate/install the Shortcut media payload path, including upload reference/hash.
  Reconcile existing unbound media using trusted append-only evidence. Do not declare
  old captures unrecoverable just because strict preparation refuses missing hashes.
- Connect validated extraction to atomic atom persistence and nutrition resolution.
  Complete dictated-text and photo paths and their required scenarios.
- Implement the separate worker supervisor, durable per-run work tracking, timeout
  recovery and observed nightly schedule. Counts-only maintenance is not enrichment.
- Complete approved production migration/ACL checks, real voice/photo replay,
  post-commit readback, freshness/withheld-feed evidence and authorized cutover.

Media retention/deletion and reserved measurement decisions remain Joe's. No uploads,
provider calls, deletion, production migration or deployment were performed to create
this document or the associated local tests.
