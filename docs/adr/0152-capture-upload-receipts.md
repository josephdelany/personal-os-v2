# ADR-0152 — Immutable upload identity and recoverable media receipts

Status: locally verified integration; HTTP uploader implemented, device and platform activation open.
Date: 2026-09-23. REQ-CAP-006/009/011/012/016; ADR0148/0151.

An upload identity records capture UUIDv7, media kind, canonical UUID/audio-or-photo
object path, SHA256, byte count and MIME type before raw capture acknowledgement.
Repeated identity must match every field. The identity is not evidence of a completed
upload: its status remains awaiting_upload until an append-only completion receipt.
No row, raw payload or existing object is overwritten.

The authenticated upload handler in `workers/capture-media/index.mjs` hashes the actual body, commits the identity,
performs a non-upserting upload, and appends its receipt only after verifying the Storage
success response. A conflicting/ambiguous upload without a receipt stays retryable.
The private reconciler uses the recorded expected hash and size to verify downloaded
bytes before appending a private_hash_check receipt. Neither receipt RPC can itself
prove an external upload: it trusts its narrowly authorized caller to perform this step.

Raw captures with a matching path but no embedded hash can use the immutable verified
receipt for that capture/path. This does not alter the raw row. Truly unregistered old
media, unknown original hashes and noncanonical legacy paths still need trusted recovery
and a real inventory; this draft does not manufacture original-device provenance.

## Roles and platform policy

capture_media_upload has narrow identity/completion and Storage predicate RPCs, not
private table reads. capture_media_reader has only its Storage predicate. service_role
reads metadata and calls reconciliation. New role names fail on collision rather than
adopting unknown privileges. No credential is provisioned in this migration.

supabase/capture_storage_policies.sql is a separately approved platform activation
artifact. It requires an existing private captures bucket with a <=50MiB file limit and
RLS already enabled. A restrictive PUBLIC guard contains existing permissive policies
for that bucket while preserving unrelated buckets. Role restrictions prevent upload
reads, reader inserts, and either role updating/deleting. Public TRUNCATE/TRIGGER/
REFERENCES privileges cause preflight refusal because RLS cannot safely contain them.
Privileged Storage administrators remain trusted and can bypass RLS.

[Supabase documents](https://supabase.com/docs/guides/storage/uploads/standard-uploads)
that existing-object uploads fail by default, and recommends resumable transfer for
larger files. Its [access-control contract](https://supabase.com/docs/guides/storage/security/access-control)
requires extra permissions for upsert. These sources informed the no-replacement
policy; actual vendor HTTP behavior and custom JWT-role integration remain unverified.
No new dependency or vendor is added; Free-plan upload resource limits require actual
hosting evidence before activation. Media retention/deletion is still Joe's decision.

## Verification and remaining scope

The expanded receipt/transcription run passed31 cases in19.51s, including the
scoped cross-stage regression and read-only policy permissions. Upload and ingress
HTTP tests include24 passing cases with substituted transport. Policy tests use actual PostgreSQL
RLS against a disposable Storage-shaped table, not a claim of vendor Storage behavior.
Independent read-only review found no material defect in the scoped design.

Still required: observed live byte/hash/receipt flow and device integration, bucket creation/provisioning, device payload generation, all unbound-media recovery,
full integration, live permissions, real voice/photo capture, extraction and separate
scheduled workers. No production write, Storage object, credential or deployment exists
as a result of these local tests; fixtures roll back completely.


The explicit `/capture` route connects uploaded media to committed raw ingestion;
`/upload` acknowledges only media, and all other routes return404. Scoped stage
integration exposed a pre-existing missing RLS policy on processing events: a
service worker could not see its prior outcome during duplicate consumption.
Forward migration0082 enables the already granted history SELECT capability only;
it grants no writes and exposes no media or transcript payload. The rollback-only
integration regression now reaches one saved transcript through upload, ingress,
model receipt and private consumption. It does not prove live delivery or commit
visibility. Device silent queue/replay and extraction remain open.
