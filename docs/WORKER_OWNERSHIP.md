# Worker ownership — session 21

## 2026-09-22 separated Ask planning consumer

Root reserves migration0078 and ADR0147, `tools/engines/ask_jobs.py`,
`tools/ask_jobs.py`, `tests/test_ask_jobs.py`, SQL harness and maintained docs.
Requirements REQ-ASK-004/006/008/012/031: persisted prepare/consume stages, fixed
question/date/registry, bounded retries, correlated model receipts, deterministic
execution and idempotent readback. Provider credentials never enter these stages.
Shared model foundation committed at `cd02e43`.

## 2026-09-22 shared egress prerequisite

Root owns migration **0077**, ADR **0146**, `tests/test_model_reservations.py`,
`lib/egress.py`, `lib/db.py`, `tools/model_egress.py`,
`tests/test_model_dispatch.py`, shared budget/client tests and SQL harness. Outcome: serialized
shared reservations and restricted logging RPCs (REQ-CAP-035..039, RULE-29), then
commit-before-send wiring. Acceptance: exact ceiling, idempotent request identity,
invalid costs rejected, no private reads for model role, preserved failed spend.
Processing foundation committed at `22a9d2d`; no production deployment.

## 2026-09-22 goal resumption

Joe explicitly authorized reconciling the pending merge and completing M0–M6.
The root goal owner reviewed/preserved and integrated the four pending nutrition
files at `a8bcbf4`. No child agent is active; the nutrition worktree has no tracked
uncommitted changes and its branch last changed September 11. Historical
assignments below are not evidence of active work today.

Root now owns durable capture ingress, allocating migration **0075** and ADR
**0143**, `workers/capture-ingest/`, `tests/test_capture_ingress_sql.py`,
`tests/test_capture_http.py`, `tests/capture_http.test.mjs`,
`tools/test_local_sql.py`, `.github/workflows/tests.yml`, and maintained docs.
No deployment is authorized by this allocation. Root also retains
ADR **0144** for Joe's approved OQ-83 storage-contract amendment. Migration **0076**
is reserved for processing history after the receipt unit closes. Root retains
`tools/engines/capture_processing.py`, `tools/capture_processing.py`, and
`tests/test_capture_processing.py` for that unit. Receipt work is committed at `b4752b6`.
Root additionally owns `.github/workflows/capture-processing.yml` and ADR **0145**
for persisted reviews, operations wiring and remaining runtime boundaries.
The reviewer was read-only and has finished. Root retains
`tools/engines/ingest_endpoint.py` and `tests/test_ingest_endpoint.py`, and maintained
checkpoint/audit/progress documents. Subsequent units must update ownership before
overlapping an old assignment. No parallel implementation is active.

Who may edit what, so no two sessions edit one file. Confirmed against `48745d9` before any
worker began. The integration owner (main) allocates every migration and ADR number.

**`WORKER_BRIEF.md` lives in each worktree and is deliberately NOT carried on the integration
branch.** All three worktrees tracked it at the same path, so every merge collided add/add. The
briefs are per-worktree operating documents; this file is the durable record.

| Owner | Worktree / branch | Owns |
|---|---|---|
| **main** | `PERSONAL_OS_V2` / `session-21-recovery-and-ask` | reconstruction methods, runner, Ask/Record integration, correction and replay; **all migrations and ADR numbering**; shared SQL/API contracts; `lib/`; `tools/import_drop.py`, `tools/importers/*`; `.github/workflows/analysis.yml`; the checkpoint; integration and deployment |
| **Worker 1** | `PERSONAL_OS_V2_release_evidence` / `work/release-evidence` | evidence tooling and its tests; test harness and fixtures (`tests/conftest.py`, `tests/_sql_fixture.py`, `tests/_location_fixture.py`, `tools/test_local_sql.py`); `.github/workflows/tests.yml`; coordination of the final verification run |
| **Worker 2** | `PERSONAL_OS_V2_nutrition_finish` / `work/nutrition-finish` | `tools/engines/nutrition*.py`, `tools/resolve_nutrition.py`, `tools/nutrition_acceptance.py`, nutrition CLIs, `tests/test_nutrition*.py` |
| **Worker 3** | `PERSONAL_OS_V2_capture_finish` / `work/capture-finish` | `ops/capture_schedule.py`, freshness and continuity tooling, `tools/engines/{capture_budget,capture_resilience,extraction,ingest_endpoint,vision_and_prompts,compliance}.py`, `tests/test_capture*.py`, **new** capture-specific workflows |

## Shared files that need coordination, not parallel editing

- **`tools/test_local_sql.py`'s `TESTS` tuple** — Worker 1 owns it and three sessions append to
  it. Additions so far: `test_workout_session_r2.py` (main), four from Worker 1,
  `test_nutrition_usda.py` (Worker 2, requested by handoff and applied by main).
  **An unregistered SQL test file skips in every environment and counts as nothing.**
- **`.github/workflows/analysis.yml`** — main owns it; Worker 3 proposes the exact edit.
- **`tools/importers/apple_health.py` and `tools/import_drop.py`** — main owns both. Worker 3's
  brief says so explicitly because main changed `apple_health.py` for R2 during that session.

## Numbering

Migrations and ADRs are allocated by main **on request**, never picked in a worktree. A worktree
cannot reserve a number, and two have now collided:

| collision | resolution |
|---|---|
| ADR-0091 (capture worker, session 20) | renumbered **0094** |
| ADR-0138 (nutrition worker, this session) | renumbered **0139** — main's `0138-workout-session-reconstruction.md` was committed to the integration branch first |

## Handoffs

Worker handoffs are integrated under `docs/handoffs/`.

Root reserves ADR0148 for Joe-approved OQ84 transcription result storage amendment.

Root reserves migration0079, ADR0149 and tests/test_capture_ingress_sql.py for the
reproduced transaction-start timestamp defect in raw/atom insert stamping.

## 2026-09-22 — root capture transcription unit

Root owns migration0080, ADR0150, tools/capture_transcription.py,
tools/engines/capture_transcription.py, tests/test_capture_transcription.py,
shared egress/model_contract and dispatch CLI/tests, capture_budget/tests, SQL harness
and maintained docs. Read-only reviewer owns no files. Media acquisition/extraction
and actual orchestration remain required; no production writes or deployment.

## 2026-09-22 — root private media unit

Root owns lib/db.py, lib/egress.py, capture_transcription engine/CLI/tests, new
tests/test_capture_media.py, ADR0151 and maintained docs. Reviewer is read-only.

Private media unit also owns docs/CAPTURE_RUNTIME.md and its DOCUMENTATION_MAP entry.

## 2026-09-23 — root upload identity/receipt unit

Root owns0081, ADR0152, supabase/capture_storage_policies.sql, capture_media_receipts
tests, capture_transcription engine/CLI additions, SQL harness and maintained docs.
Read-only review owns no files; no platform activation or production mutation.

Root also owns forward repair0082, workers/capture-media/, shared ingress auth export, HTTP tests/harness and COMPLETION_AUDIT for this same voice-path unit. Reviewer remains read-only.

## 2026-09-23 — same voice-path device transport

Root owns device/scriptable/, ADR0153, tests/capture_device_queue.test.cjs, HTTP harness, extraction verifier/tests and maintained checkpoint/decision/runbook docs. Reviewer is read-only. Joe approved the free Scriptable helper; no device installation or production action has occurred.

Device packet ownership includes PersonalOSSetup, tools/package_capture_device.py, DOCUMENTATION_MAP and COMPLETION_AUDIT. Source-only artifact is under ignored .local/device/. No separate worker edits these files.

## 2026-09-23 — extraction consumer connection

Root owns draft0083/ADR0154, capture_extraction engine, capture_transcription CLI branch, extraction/transcription tests, CI Pydantic dependency and maintained docs. Preparation, consumption and cache-backed atom resolution are locally integrated in the same voice-path unit. No parallel file writer.

Root's draft0083 ownership includes immutable extraction outcomes/fields, actual
consume-extraction/fail-extraction CLI, transcription engine readback/resolve queue,
quarantine owner RPC amendment and their targeted tests. Reviewer was read-only
and completed scoped follow-up; no other writer owns these files.

Root now owns `tools/engines/capture_resolution.py`, nutrition persistence's optional
capture-item identity/time-precision arguments, resolution CLI/readback/queue,
draft0083 resolution tables/atom FK, and their SQL tests. Same voice-to-atoms gate:
REQ-CAP-053–060/063–066, REQ-NUT-001/014/034/036/050 and RULE-02/05/08/12.
Acceptance: saved verified count -> reference-backed atoms/readback, duplicate and
repeated-phrase identity, unknown-time fallback, invalid fields/no-source behavior,
atomic rollback and scoped role access. No independent writer assigned.

Root also owns nutrition_day/nutrition_display missingness and provenance filtering,
draft0083 statistics views/triggers, and associated tests. Final read-only reviewer
follow-up completed; no remaining scoped blocker. No concurrent file writer.


## 2026-09-23 — isolated reference dispatch in the same voice path

Root owns draft0084/ADR0155, lib/egress.py source transport, lib/db.py reference
connection, reference_dispatch engine and reference_egress CLI, new reference
transport/dispatch/SQL tests, test_egress transport inventory and disposable-suite
registration. Private capture credential guard and maintained checkpoint/audit/docs
are also root-owned. Acceptance: direct source login, bounded HTTPS/no redirects,
quota reservation and audit before send, settled response binding, persistent429,
no private reads, no repeated-ID sends. Private preparation/cache consumption and
supervisor remain the next connected gates. Reviewer is read-only.

## 2026-09-23 — private reference handoff in the same voice path

Root owns draft0085, capture_reference engine, prepare-reference/consume-reference
private CLI branches, capture readback reference history, reference transport guard
and their tests, plus maintained ADR0155/runtime/checkpoint/audit docs. Acceptance:
REQ-NUT-002–005/024/025 and CAP053–060: verified saved item -> immutable bounded
request -> matching isolated receipt -> exact reparsed source cache/alias -> existing
atom resolver. Duplicate/stale delivery and failed writes must not publish partial
or substituted data. Source-order/TTL and supervision remain open, not waived.
Reviewer is read-only; no other file writer assigned.

Root continues0085 recovery and owns updates to `tests/test_reference_dispatch_sql.py`
for the new durable-body settlement capability. Reviewer remains read-only.
Root also owns `tests/test_reference_transport.py` for the transport-owner patch
needed to satisfy the unchanged network-import lint at integration.

## 2026-09-23 reference freshness within the same M3 outcome
Root owns migration0086, ADR0156, nutrition.py/nutrition_off.py,
capture_reference.py and their tests/maintained docs. REQ-NUT-008: stale Branded/OFF
misses trigger fresh publication without overwriting prior food/provenance rows;
Foundation/Joe remain non-expiring. Then connect ordered source selection.
No implementation worker runs concurrently; reviewer is read-only.
Root extends the same0086 unit to `tools/capture_transcription.py` and
`tools/engines/capture_resolution.py`: automatic name-source preparation and
persisted no-match review transitions. Migration0086 also preserves review-reason
history before updating the current unresolved-item projection.

## 2026-09-23 brand context within M3 capture
Root owns `tools/engines/capture_food_context.py`, capture_reference.py,
capture_resolution.py, nutrition.py, tests/test_capture_reference.py,
tests/test_capture_transcription.py, new context tests and maintained docs/ADR0157.
REQ-NUT-013/016/025, REQ-CAP-053: preserve explicit verified supplier context in
both reference query and private cache resolution; refuse ambiguous cache identities.
No model schema field addition, external request or production mutation is authorized.

## 2026-09-23 model handoff recovery within M3
Root owns migration0087, lib/egress.py, capture model recovery engine/private CLI,
related tests, ADR0158 and maintained evidence/checkpoint docs. Reviewer read-only.
Gate2/4 currently fail if successful model stdout is lost: digest-only settlement
cannot reconstruct a response. Implement bounded durable settlement and private
reconciliation before the separated supervisor can safely resume saved work.
Root also owns tools/test_local_sql.py registration and tests/test_capture_transcription.py fixture migration to atomic settlement.
Root extends this same runtime unit to tools/model_worker.py, tools/model_egress.py,
tools/engines/capture_runtime.py, tests/test_model_worker.py, tests/test_capture_runtime.py
and the existing media-receipt fixture. No parallel implementation owner.

## 2026-09-23 reference supervision / durable handoff continuation
Root owns shared lib/worker_process.py, tools/model_worker.py, new reference worker,
reference dispatcher/CLI callback, migration0088 and their tests/docs. Gate2/4 needs
the same bounded owned-process recovery for reference requests before scheduler
handoff can connect all stages. No external calls/deployment or other writer.

Root also owns lib/capture_mailbox.py, tools/capture_dispatch_mailbox.py and
tests/test_capture_mailbox.py for the same durable runtime handoff.
Root additionally owns tools/capture_transcription.py, tools/engines/capture_mailbox.py
and tests/test_capture_runtime.py for commit-before-publication and SQL-gated retirement.
Root owns tools/capture_private_worker.py and expanded mailbox/runtime tests for
the same capture scheduling connection; no additional implementation worker.
Root owns tests/test_capture_private_worker.py and ADR0159/index for private
pagination and operational nightly sweep gating in the same capture unit.

Root owns tools/capture_private_service.py and tests/test_capture_private_service.py
for bounded private polling after b2078cd; same M3 voice path, no external activation.
Root extends the same deadline unit to tools/capture_private_worker.py and
tests/test_capture_private_worker.py for durable pre-work cursor/incomplete state.
Root extends the same service-boundary unit to lib/capture_mailbox.py,
tools/capture_dispatch_mailbox.py and tests/test_capture_mailbox.py for nonblocking
writer contention and real-process refusal/retry proof.
Root additionally owns tests/test_capture_runtime.py for real SQL verification of
terminal-capture mailbox retirement; same private worker and same M3 unit.
Root owns tools/capture_service_entry.py, ops/capture_services.py and tests
test_capture_service_entry.py/test_capture_services.py for uninstalled role service
packet and protected secret loading; no account or production provisioning performed.

## 2026-09-23 possessive supplier preservation after5ea1cd8
Root owns capture_food_context.py, its tests and capture-reference/runtime SQL
regressions plus ADR0157/checkpoint evidence. REQ-NUT013/016,CAP053: a possessive
qualifier inside verified evidence but outside the extracted food name must not be
dropped to generic lookup. Preserve offsets; refuse ambiguous/narrowed evidence.
No model-schema, measurement definition, dependency or production change.

2026-09-23 root continuation after bc5c92c: next same M3-B16 source-backed supplier
recognition; root owns capture_food_context, capture_reference, source brand-token
helpers, related pure/reference SQL tests and checkpoint/ADR/audit. Reviewer remains
read-only. Current code clean at commit; acceptance/replay safeguards in NEXT_SESSION.

Source-context v3 review repair: root additionally owns tools/engines/nutrition.py,
capture_runtime.py, capture_mailbox.py and tools/capture_private_worker.py for
source identity and late terminal receipt cleanup; associated existing tests.

Root after a7fd2b4: stated mass connection in same M3-B16 path; owns quantity
binding in capture_resolution/capture_extraction, common mass conversion plus
OFF/USDA consumers, tests/test_capture_quantities.py and existing transcription
SQL fixture/tests. Reviewer read-only; no competing implementation agent.
