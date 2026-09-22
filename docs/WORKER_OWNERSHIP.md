# Worker ownership — session 21

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
