# ADR-0145 — Persisted capture reviews, separate from enrichment

Status: accepted for local implementation; deployment held. Date: 2026-09-22.
Requirements: REQ-CAP-025..027; RULE-02/27. Extends Joe-approved ADR-0144.

Migration0076 records immutable processing outcomes and projects current status.
The writer takes an expected predecessor and idempotent attempt ID. Per-capture
transaction locks serialize writers, with READ COMMITTED required so a waiter sees
the preceding commit. Stale outcomes remain history with applied=false; they never
change the current status. This is not a substitute for OQ-82 concurrency evidence.

Pending age follows the unresolved provider-failure episode. Repeated errors and
budget deferrals do not reset it. Deferred work without a provider failure does not
invent a pending failure age. Operational events use server clock_timestamp at
append, not the transaction's potentially much earlier start time. Raw event time
and raw recorded time are unchanged. Historical ingestion-time terminal states are
preserved when no processing history exists.

An overdue episode creates one persisted enrichment_stalled review, linked to the
capture and nominated processing event. Refreshes are idempotent. Current owner-only
readback hides recovered/old episodes. Owner dismissal is an immutable, permanent
capture-level record; subsequent processing episodes cannot re-create a dismissed
review (RULE-27). No Web Push or prompt-delivery claim is made. The queue is a backend
review-list input, not frontend construction.

`tools/capture_processing.py` and its nightly workflow call actual maintenance SQL
and record a counts-only ops heartbeat. The CLI previews by rollback unless
--commit is explicit. The supplied maintenance clock is internal and deterministic
for rollback-only tests; the CLI always supplies the actual UTC clock. No user/API
can invoke the write function except the trusted backend service role. No payload
or capture identity appears in CI output. Existing pg8000/Actions only, $0 recurring;
no provider call, new service or dependency is introduced.

## Explicit remaining work

This maintenance job is not the REQ-CAP-026 enrichment runner. Initial capture
selection, validated model request/result transport with separate private-read and
model-egress capabilities, shared budget/log reservations, persisted transcription
and extraction, and actual retry execution remain required. A status RPC accepting
enriched does not prove corresponding results exist. The eventual result consumer
must persist verified results and effective status atomically, and treat stale
receipts as stale, never as successful processing.

Existing `lib.egress.call` accepts a database cursor and does not commit its pre-call
ledger itself. Reusing it with a broadly privileged reader would violate ADR-0020;
rolling its transaction back after a network failure would lose the audit record
despite ADR-0063's stated survival guarantee. These are implementation dependencies,
not authorized deferrals or reasons to declare the backend complete. Do not add a
second unbudgeted provider path while connecting the runner.

## Review disposition

Independent review found that caller-selected read/log schemas could diverge from
migration-bound mutation RPCs. The CLI now exposes no schema routing knobs; one
migration-bound maintenance RPC owns review insertion, status counts and heartbeat
in the same transaction. Targeted processing/ingress tests pass 43/43. Full integration passes: 1061
no-database tests (671 skipped), 838 disposable SQL tests (1 skipped), 75 migrations
and 646 statements, layout43/43. Final read-only review found no further material
defect; real concurrency, live commits and actual enrichment remain unproven. The history TRUNCATE test includes its
referencing review table so it reaches the append-only trigger rather than stopping
at the foreign-key restriction. No integrity assertion was weakened.
