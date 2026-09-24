# ADR-0167 — V0 owner meal save and history

Date:2026-09-24. Status: accepted; local implementation verified, activation pending.
Requirements:CAP005/006/014/016/017, RULE02/03/06/10/29; approved daily V0 scope.

Joe explicitly requested meal photo/text entry and corrections in V0. This expands
CAP005’s previous written-input restriction to meal text and the approved V0 entry
flows; it does not authorize arbitrary editing of imported facts. Record that scope
in CAP005. Preserve the image-origin rules: photo bytes come from the approved
Shortcut/helper, and a meal may reference only an existing shortcut_photo capture
with matching verified private-media receipt. No public bucket or URL exposure.

Owner-JWT save_v0_meal/get_v0_meals use UUIDv7 exact retry and append-only versions,
reusing the V0 check-in receipt/history pattern. Text or a completed photo is
required. Corrections name the current predecessor; changed reuse refuses. Save
acknowledgement means stored evidence, not nutritional verification. Day reads show
saved meals even when no resolved nutrition exists, with explicit pending status.
Only results attached to that exact meal version may appear; never copy old values
onto a changed description/photo. No model/extraction success is fabricated.

Day reads return private bucket/path metadata. Supplemental Storage policies allow
owner-authenticated downloads of linked completed photos; bucket stays private,
owner inserts/updates/deletes refuse. The Boolean policy helper is callable only by
explicit Storage-facing roles (anon, authenticated, service_role, capture_media_upload,
capture_media_reader); capture_ingest has no execute grant. It supports restrictive
PUBLIC policy evaluation but returns false unless invoker role is authenticated
and the owner JWT matches. This avoids PostgreSQL ACL checks breaking unrelated
reads on inactive policy branches. Actual Storage activation/delivery remains
required by the V0 handoff. Existing voice processing
is not claimed to process V0 text/photos automatically. Connect actual processing
only when its supported path is verified; saving/history must not depend on it.

Acceptance: owner/anon/nonowner, text/photo/both, missing or mismatched receipt,
empty/invalid payload, exact/conflicting retry, correction/current history and raw
immutability, pending versus actual results, atomic rollback. All fixtures rollback.
No production or frontend change; independent review/full integration required.

Targeted27SQLpassed1.11s, including pending/results_available/removed states and
no predecessor results after a meal correction. Stored-result fixtures prove the
read contract, not automatic V0 text/photo enrichment. Storage-policy fixtures
prove access bounds in disposable tables, not live image delivery. Final review accepted. Full SQL1132passed1skip389.81s; feature writer1451passed
959skipped172.02s; migration chain91files960statements; layout43pass. Four spine
invariants pass; generic RULE04 pending. Merged43unverified skips:41production,
2NumPyro. Evidence/hashes: .local/evidence/v0-meals/final/. No live activation.
