# ADR-0147 — Persisted private Ask stages around isolated model dispatch

Status: locally verified foundation; runtime orchestration and deployment open. Date: 2026-09-22.
Requirements: REQ-ASK-004/006/008/012/031; RULE-04/13/15/29; ADR0020/0064/0146.

A private preparation stage records the original question, explicit subject-date
cutoff, server knowledge cutoff, registry options and deterministic fallback. It
exports only the planner's prepared prompt/registry metadata. A separate model
process receives that request, reserves/commits budget and returns a correlated
response. The private consumer verifies the settled reservation and payload digest,
validates the response against the saved registry and question, and calls the single
SQL Ask executor using the fixed two clocks. Both private stages refuse provider
credentials; model database identity has no private job-table access.

Jobs, attempts and outcome receipts are append-only. Replayed prepare identity must
match its question/date. Replayed model response must match its digest and returns
the saved transition without executing another computation. Readback recovers the
latest state. Invalid plan attempts produce at most five requests; the cap returns
"I cannot compute that." with nearest registered operations and no evidence tier.
No model code is executed. A per-job transaction lock serializes consumers.

A shared pure byte encoder fixes JSON ordering across preparation, JSONB storage
and transport, so equivalent serialized prompts bind to the same reservation.
No new service or dependency is added ($0 recurring). SQL fixtures remain entirely
rollback-only and are not actual model calls or post-commit/concurrent proof.

## Still required before this unit closes

- Failure/budget fallback consumption and malformed provider shape retries are now
  implemented; expand receipt mismatch and concurrency/replay evidence at integration.
- Actual private CLI is exercised with a direct service_role identity in a rollback
  fixture. It accepts only matching session/current identity postgres or service_role
  before setting the existing single-owner SQL context. This trusts the backend DB
  credential; it is not validation of an external JWT. Model identity is rejected.
- Prove receipt mismatch, raw-data exclusion, knowledge-cutoff replay, changed
  duplicate response and role boundaries; test persisted numerical result traces.
- Review and full integration. Current drafts are uncommitted.
- Actual process orchestration and default-date selection shared with the SQL owner
  remain open; the CLI currently requires explicit as-of. Existing direct Ask uses
  deterministic fallback until the separated path is connected.
- Full REQ-ASK-005 read-only execution/write separation is not established merely
  by reusing the existing public.ask RPC; its writes require the existing M2 audit.

Transcription storage is independently approved under ADR0148. Complete this bounded
Ask piece, then return to actionable capture enrichment; no frontend work.


## Independent review repairs

The first consumer could read reservation metadata only as schema owner, hiding a
service_role denial. Explicit metadata SELECT grants/policies and owner-checked
executor access now support actual service_role preparation/consumption tests.
The model role still cannot read these private tables.

Request identity was also insufficient evidence for response identity. Settlement
now records an immutable canonical response digest before returning to the private
consumer; the consumer checks it as well as the request digest, model, kind, cost
and null capture binding. The previous three-argument settlement is revoked from
model_egress; the new four-argument form validates and records response identity in
the same transaction. Error responses record no successful digest.

The first numerical fixture hit the absent-data refusal rather than a computation.
Full-chain diagnosis found that aggregation methods are seeded only for pre-existing
atoms during migration. The fixture now explicitly registers its test method and
uses the actual activity_sample taxonomy, raw captures and atoms. No production
registry definition or gate was changed. The delayed-response test additionally
inserts a later atom and requires the earlier knowledge cutoff to exclude it.


Further review fixed legitimate PayloadRefused fallback and persisted complete
model/kind/cost dispatch parameters per attempt, so changed constants cannot alter
an already prepared request. Unknown model CLI failures use DispatcherUnavailable,
while known refusal classes retain their codes; no provider error body is exposed.
Targeted54 SQL and15 dispatcher tests pass; full integration remains pending the
recorded-time/current-cutoff compatibility work in ADR0149.

## Integration evidence

Current-cutoff compatibility is repaired under ADR0149. Full local integration:
1076 no-database tests passed /704 skipped;871 SQL passed /1 skipped;78 migrations
/689 statements;43 layout checks. Response substitution, changed duplicate response,
service/model permissions, bounded retries and persisted numerical trace are exercised.
Independent review found no further blocker in this scope. Earlier pending-review
notes above are superseded by this evidence; orchestration, default-date ownership,
REQ-ASK-005 and live/concurrent evidence remain open.
