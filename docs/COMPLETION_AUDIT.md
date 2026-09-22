# Project completion audit

## Current quality review — 2026-09-22

**Disposition: backend release not ready.** This is a fresh, multi-checklist review,
not a claim that every line or every requirement has received independent review.
Baseline: `6fe21e60763e84fcce1a5c544d745737bbdaa889`, plus the pre-existing staged/
unstaged nutrition changes in `tests/test_nutrition_day.py`,
`tools/engines/nutrition.py`, `tools/nutrition_day.py`, and `tools/test_local_sql.py`.
Those files were preserved, not edited or staged by this review. Results describe
that working tree, not a clean checkout of the commit. Execution order remains in
EXECUTION_PLAN; the checklists below are evidence lenses, not another backlog.

### Checklist results

| Review lens | Result | Evidence and remaining acceptance |
|---|---|---|
| Contract fidelity and test quality | **FAIL** for reviewed capture edge cases | REQ-CAP-008 rejects absent tokens, but `handle(..., expected_token=None)` accepts an absent token. The existing test exercises only a configured expected token. Requirement-to-test counts cannot close this behavior. |
| Complete user paths | **PARTIAL** | Static import analysis now finds 10 scheduled, 13 CLI and 33 tests-only engine modules. Some tests-only modules are legitimate lint/support libraries; this is not a count of 33 missing features. Capture hosting is absent: the repository's only Edge Function is `location-ingest`. Nutrition's new read CLI exists in uncommitted work. |
| Failure and recovery behavior | **PARTIAL; concrete capture gaps** | The capture handler ignores the insert callback result and cannot distinguish an insert suppressed by a racing duplicate; its precheck is not a database conflict result. An enqueue exception propagates after the insert callback succeeds. Separate resilience helpers have tests but are not called by this handler. |
| Data integrity and historical behavior | **PARTIAL** | Migration chain passes from empty: 73 migrations / 592 statements, including prerequisite schema scaffolding. SQL behavior and invariant tests are exercised on a disposable server. The invariant checker still explicitly treats the generic RULE-04 query as pending when `derived_measures` is absent; an overall successful return must not be read as that query passing. Live integrity and real historical replay were not reverified in this review. |
| Access, privacy and cost | **PARTIAL** | Layout/privacy lint passes 43/43, including network-import restrictions. Missing-token probe fails. Actual deployed role permissions, service account billing settings and provider limits were not reverified. No personal records were sent to GitHub. |
| Runtime deployment | **FAIL** | Fresh GitHub API reads: default branch `v2-day1`, latest repository push 2026-09-03. Its workflow directory contains analysis/extract/gates/keepalive/pages, but neither freshness nor tests. Freshness is absent from registered workflows. Latest tests workflow run is 2026-09-03, event `push`, branch `main`. Successful scheduled analysis/extract/keepalive runs exist on 2026-09-22; they do not establish input freshness or deployment of local code. |
| Operations and recovery | **NOT VERIFIED / documentation stale** | No fresh production observation, withheld-feed alarm, restore rehearsal, storage-headroom or cutover parity evidence was produced. `docs/build/RUNBOOK_NO_CLAUDE.md` still says Ask has no design and importers need rebuilding; those statements no longer describe the local backend. Update and exercise the runbook before release. |
| Evidence and reproducibility | **PARTIAL** | Fresh suites, layout and migration-chain results are recorded below. Dirty nutrition work prevents attributing the entire result to committed HEAD. The named B23 artifacts `tools/req_coverage.py`, `tools/gherkin_to_tests.py`, `docs/REQ_COVERAGE.md`, and `docs/DEFERRED.md` are absent. Existing audit tools provide part of the intended instrument; exact replacement-contract equivalence, scenario execution and release-surface publication remain to be established. |

### Reproduced capture findings

1. **Missing configuration fails open (REQ-CAP-008).** In a pure Python call,
   `handle({'body': {'capture_id': 'audit-probe', 'captured_at':
   '2026-09-22T00:00:00Z'}}, expected_token=None)` returns status 202. Expected:
   absent bearer token is rejected before reading the body. This is a defect in
   an unhosted component, not evidence of an exposed production endpoint.
2. **Database duplicate outcome is not represented (REQ-CAP-016/017).** An insert
   callback returning `False` still produces `inserted=True`, status 202 and one
   enqueue. The callback has no documented conflict-result contract; this probe
   demonstrates the missing integration contract, not a real database race test.
   The hosted path must use the database's insertion result, not just the
   potentially stale `existing_capture_ids` snapshot.
3. **Enqueue failure escapes after insertion (REQ-CAP-011; resilience integration).**
   With an insert callback succeeding and enqueue raising `RuntimeError`, the
   handler raises instead of returning an acknowledgement. This was a pure
   callback probe, not proof of a committed database write. Persistence, retry
   ownership and REQ-CAP-025 downstream-failure behavior must be tested together
   through the eventual hosted path.

All probes were in memory; no captures or personal observations were written.
These findings remain open engineering work. No defect-count target was used.

### Fresh execution evidence

- Full pytest without production credentials: **1030 passed, 628 skipped**, no
  failures, 145.71 seconds. Two skips explicitly name missing NumPyro; database
  skips must be reconciled with the disposable suite, not counted as passes.
- Disposable SQL suite: **795 passed, 1 skipped**, no failures, 188.28 seconds;
  temporary server shutdown confirmed.
- Merged named-test evidence: **673 of 685**, with 12 requirements still skipped.
  These are REQ-ASK-003/011, REQ-INF-109/505/520, REQ-LOC-005/012,
  REQ-NAR-014, and REQ-TIER-005/035/050/053. No failed, errored, uncollected or
  assertion-free requirement evidence was reported. The capture findings above
  show why this count does not establish full behavioral fidelity.
- `ops/requirement_evidence.json` is absent: the auditor has no machine-readable
  integration/deployment/observation evidence for any requirement. This means
  those levels are unknown to that instrument, not that no deployment exists.
- Layout: **43 passed, zero warnings or failures**.
- Migration chain: **73 migrations, 592 statements, clean from empty**.
- Git staged and unstaged whitespace checks passed before documentation edits.
- SQL startup initially failed under sandbox shared-memory restrictions. It was
  rerun with approved escalation, production credentials removed, TCP disabled,
  and temporary local PostgreSQL 17 servers.

Commands/artifacts (local `/tmp` artifacts are ephemeral):

```sh
env -u SUPABASE_DB_URL -u PERSONAL_OS_TEST_SOCKET -u PERSONAL_OS_PRODUCTION_CHECKS PYTHONPATH=. python3 -m pytest tests/ -q -o xfail_strict=true --junitxml=/tmp/backend-audit-unit-20260922.xml
env -u SUPABASE_DB_URL PYTHONPATH=. python3 tools/test_local_sql.py --junitxml=/tmp/backend-audit-sql-20260922.xml
env -u SUPABASE_DB_URL PYTHONPATH=. python3 tools/validate_layout.py
env -u SUPABASE_DB_URL PYTHONPATH=. python3 tools/verify_migration_chain.py
env -u SUPABASE_DB_URL PYTHONPATH=. python3 tools/evidence_report.py --report /tmp/backend-audit-unit-20260922.xml --report /tmp/backend-audit-sql-20260922.xml --out /tmp/backend-audit-evidence-20260922.md
```

### Next boundary and verification limits

Reconcile/preserve the existing nutrition unit, then prioritize actionable capture
recovery under M1. The next capture implementation contract must include absent
configuration, durable acknowledgement, database-conflict idempotency and
downstream-failure recovery before hosting it. Prepare migrations and publish the
matching default-branch workflows under applicable production authorization;
prove unattended fresh input and withheld-feed detection. External holds do not
stop the independent R1/R11 and other required backend work.

**WHAT I DID NOT DO:** no production DB reads/writes, deployment, new hosted
endpoint, defect repairs, capture acceptance exception, personal-data export,
full semantic audit of all 685 requirements, or release approval. The sanctioned
feature-ledger writer was not run: this was an audit/documentation unit, not a
backend implementation integration, and no feature status was changed. Older
production figures below remain historical, not fresh observations.

## Historical review — 2026-09-09

Re-checked **2026-09-09** against the live database, after two adversarial review rounds. The objective remains the whole Personal
OS described in `docs/THE_FILE.md`, the specifications, the roadmap gates, and the B0–B23 /
L0–L8 build orders. This is an inventory, not a completion certificate. Earlier PROGRESS
entries are historical evidence; they do not prove current operation.

## What changed since the 2026-09-08 audit

| Claim in the previous audit | Status now |
|---|---|
| "current DB authentication fails" (SQLSTATE `28P01`) | **Resolved.** Connection succeeds; OQ-46 closed. |
| "94 passed, 5 failed, 104 errors" | **Resolved.** `206 passed, 0 failed, 0 errors, 55 skipped of 261 collected`, exit 0, against the live database; the 55 skips all execute on the disposable local server (127 passed there, verified under three timezones). The original failures were entirely the credential. |
| "no fresh DB evidence this turn" for invariants | **Run live: ALL PASS.** RULE-04 remains PENDING by the Phase-5 deferral (OQ-22), printed as pending, not counted as passed. |
| "September 6 handoff reports stale feeds" — historical | **Measured, and worse than reported.** See below. |

## The capture position, measured

Device-side capture stopped on **2026-07-28** and has not resumed. `public.intraday`
(`hr`, `hrv_window`, `spo2`, `sleep_stage`, `resp_rate`, `walking_*`), the browser-history
feed and OwnTracks all stopped within two days of each other. The `apple_sleep` / `apple_hrv`
/ `apple_circadian` / `apple_vitals` signal feeds are derived from `intraday` and stopped with
their input. Server-side pulls (`weather`, `gmail`, `calendar`, both keepalives) never stopped,
which is why `ops.runs` stayed green for 43 days.

`tools/check_freshness.py`, run 2026-09-09 before any repair:

```
freshness as of 2026-09-09  fresh=0 stale=4 misconfigured=1 never_seen=12 unmonitored=6
```

**Zero of seventeen monitored metrics are fresh.** That number, not the test count, is the
honest headline for the project's state.

The gap is **recoverable but not recovered**: Apple Health holds the samples on the phone and
Takeout holds the browser history. Nothing has been imported yet.

## Inventory

| Required outcome | Current evidence | Remaining proof / work |
|---|---|---|
| Continuous unattended capture | Measured: stopped 2026-07-28; 0/17 metrics fresh. `health_auto_export` posts daily but only aggregates, not intraday samples | Restore device-side capture (OQ-50); import the gap from Apple Health + Takeout; demonstrate a real unattended day |
| Freshness detection | **Built.** `tools/check_freshness.py`, REQ-NFR-005..014 authored, 14 tests, daily `freshness` workflow (ADR-0060) | Gate 4 still open: 0/17 sources inside their limit, and the withheld-feed demonstration has not been run. `never_seen` can still hide a naming mismatch a string comparison cannot detect (OQ-51) |
| File-drop recovery path | **Built.** Migration 0051, three importers, 28 tests incl. a 300 MB memory bound and a three-timezone idempotency proof (ADR-0057/0058/0059) | Migration 0051 **not applied to production**; no real file imported; institution headers unverified (OQ-49) |
| Reliable operational status | `tools/status.py` repaired earlier; invariants pass live; suite green | Source-level (not metric-level) freshness limits remain unspecified |
| Canonical metric wiring | **Two defects found.** `steps` wired to a source dead since 2026-06-23 while a live one exists; `screen_active_hours` wired to a metric that has never existed | OQ-51 — needs Joe's ruling per metric before any rewiring |
| B0–B10 backend | Committed migrations, engines, historical tests; suite green | Re-verify live schema/jobs; resolve disclosed limitations incl. recommendation interval assumptions |
| B11 Ask | Draft migration 0049 (untracked); calendar/descriptive paths and computation reads tested; its fixture now runs on the disposable server, where it had begun timing out against Supabase | Deterministic operations, provenance, replay, tier and numeral enforcement; planner; budget/egress; all B11 acceptance examples. Placeholder money/contrast branches must be **replaced, not shipped** |
| B12 nutrition | Build order only | Cache-first resolution, interval nutrients, egress client, acceptance checks |
| B13 importers | **This session.** See above | Live apply; a real import; panel `src` distribution before/after |
| B14 entities and links | Build order only | Resolution, cross-source links, correction precedence |
| B15 period and compare | Build order only | Both RPC contracts |
| B16 voice/photo capture | Build order only | Media storage, extraction/verifier, budget, real capture proof |
| B17 finance | Build order only | Gmail tier, recurrence, budgets, forecast, reconciliation, the canonical-transaction dedupe engine B13 deliberately did not build |
| B18 workouts | Build order only | Derived measures, rest-day presence |
| B19 inference remainder | Build order only | Registered methods, calibration, trials |
| B20 narration/ontology | Build order only | Vocabulary enforcement, closed taxonomies |
| B21 body/sleep/context | Build order only | Author missing requirements, implement, verify |
| B22 retirement | Old-stack freeze binding | Replacement must first capture for real; per-table approval required |
| B23 completion instrument | Absent | Requirement-by-requirement evidence; `open = 0` |
| L0–L8 interfaces | `app/index.html` exists; deployed interface unverified | Verify every screen against real RPCs |
| Roadmap Gates 0–8 | Gate 0 closed. Gate 4 mechanism built, gate open | Audit each gate against live evidence |

## The honest summary

654 requirements exist. The test suite is green and the invariants hold. **Neither fact means
the system is working**, because the thing it is for — collecting a life, continuously — has
been stopped since 2026-07-28 and 0 of 17 monitored metrics are fresh. The most valuable work
available is not the next build order; it is restoring capture and importing the gap while it
is still recoverable.
