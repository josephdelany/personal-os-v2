# Project completion audit

## Current quality review — 2026-09-22

### Latest unit: immutable transcription consumption

At `d3639a3` plus recorded dirty sources, migration0080 and the private CLI are locally
verified. ADR0150 records scope and review. This is not a voice-to-atom release.

| Review lens | Result and limits |
|---|---|
| Contract fidelity | PASS for tested append-only text/timings, pending failures, immediate empty-text review and shared cost; media acquisition/extraction and full CAP scope remain PARTIAL |
| Complete user paths | PARTIAL: actual private CLI/service identity consumes and reads persisted transcript; upload-to-model-to-atoms and scheduled supervisor remain open |
| Failure behavior | PASS for tested invalid text/timings, empty output, replay/substitution, stale attempts, atomic rollback, budget and bound HTTP status; live concurrent recovery unverified |
| Data integrity | PASS tested immutable raw/results and applied-history selection; transcribed does not mean enriched; generic RULE04 and commit visibility remain open |
| Access/privacy | PASS tested service/model boundaries, narrow failure RPC, sanitized errors and credential guard; live ACL/media-source binding unverified |
| Runtime/deployment | NOT VERIFIED: private CLI exists; no deployment, actual provider/media request or observed nightly execution |
| Operations/recovery | PARTIAL: initial/retry queue, keyset pagination, preserved usable text and immediate reviews exist; durable supervisor and extraction remain required |
| Evidence/reproducibility | PASS local scope:887 SQL/1 skip;1093 no-DB/719 skips;79 migrations/719 statements;43 layout checks; no-DB collection predates one added SQL-only pagination case, covered by full SQL |

Independent review repaired immediate review omission, loss of HTTP failure codes,
divergent audio-cost formulas and queue starvation. Real service-role tests exposed
and repaired the missing voice-row read policy. All fixtures rolled back; disposable
servers stopped. Evidence/source manifest is under ignored `.local/evidence/capture-transcription/`.
Skips, narrow feature ledger14/15 and prepared code do not prove backend release.

### Latest unit: separated Ask foundation and insertion-time repair

Local evidence at `cd02e43` plus the recorded dirty source manifest; not deployed.

| Review lens | Result and limits |
|---|---|
| Contract fidelity | PARTIAL: durable fixed-cutoff jobs, five-attempt cap, validated plans and stored fallback verified; full Ask contract and executor split remain open |
| Complete user paths | PARTIAL: private CLI identity and real SQL computation/readback exercised; live process orchestration and default-date owner remain open |
| Failure behavior | PASS for tested malformed responses, substitution, replay, privacy/budget failure and parameter drift; actual concurrent/commit-survival proof remains open |
| Data integrity | PASS for tested immutable jobs/results and later-insert exclusion; current reads include later insert; commit visibility, historical measured search and generic RULE04 remain open |
| Access/privacy | PASS for tested service/model identities and immutable response receipt binding; production effective grants remain unverified |
| Runtime/deployment | NOT VERIFIED: CLI stages exist; no live separated runtime or provider call |
| Operations/recovery | PARTIAL: persisted readback and bounded retries exist; deployed scheduling and capture enrichment remain required |
| Evidence/reproducibility | PASS for local scope:1076 no-DB passed/704 skipped;871 SQL passed/1 skipped;78 migrations/689 statements;43 layout checks;54 focused SQL and15 dispatcher checks |

Independent review repaired response substitution, metadata permissions, failure-code
handling, pending parameter drift and current-read clock compatibility. SQL fixtures
rolled back and disposable server stopped. Feature ledger remains14/15; skips are not
passes. No production credentials, data or model requests were used. Earlier pending
integration notes are historical; remaining runtime and release gaps stay open.

### Latest unit: durable ingress and processing-history approval

Migration0075 plus the Cloudflare Worker are implemented and tested locally, not
hosted or observed. Joe resolved OQ-83; ADR-0144 amends REQ-CAP-025..027 without
relaxing raw-record immutability. Processing history/retry wiring is the next unit.

| Review lens | Current result and limits |
|---|---|
| Contract fidelity | PASS locally for client identity, durable-receipt mapping, exact rejection retention, atomic duplicates; full capture requirements remain partial |
| Complete user paths | PARTIAL: actual Worker export and real SQL RPC exercised separately; no deployed HTTP-to-commit/readback or device replay |
| Failure behavior | PASS for tested invalid auth/config/input, SQL conflicts, storage failure, missing/rollback/mismatched receipt; downstream recovery and real concurrency still unverified |
| Data integrity | PASS for immutable original, captured/recorded times, first-write retention; generic RULE-04 remains pending |
| Access/privacy/cost | PASS local scoped-role/table/RPC checks and credential refusal; PUBLIC grant and broad-credential findings repaired; live legacy ACL/RLS and Free-plan configuration not verified |
| Runtime/deployment | NOT VERIFIED: deployable entrypoint exists; no route/secret/device deployment; default-branch workflow gap persists |
| Operations/recovery | PARTIAL: exact deployment/cutover prerequisites documented; enrichment/retries and post-commit recovery remain |
| Evidence/reproducibility | PASS for stated local scope: 1061/649 deterministic,816/1 SQL,74 migrations/609 statements,43/43 layout; ignored artifacts/source hashes identify de97615 plus dirty sources |

Independent review reproduced two rejected-body losses and identified Worker
context misuse, excessive service-role capability and inherited PUBLIC execution.
All repaired, including refusing an unexpected pre-existing ingress role. The
sanctioned ledger remains14/15, not a backend completeness score. Historical
findings below describe earlier revisions; do not treat repaired auth as still open.


### Goal follow-up: merge and authentication repair

The pending nutrition merge was preserved and concluded at `a8bcbf4`; autonomous
setup/audit evidence is committed at `752f1ba`. The following remains a release
gap review, not a certification. New REQ-CAP-008 regression cases demonstrated
seven failures against the old handler by trapping actual body access. The repair
rejects absent/empty/non-string credentials and compares opaque UTF-8 token bytes
with `hmac.compare_digest`, without trimming/normalising the value. Focused capture
checks pass **75/75**. Hosting, insertion-conflict outcomes and downstream recovery
remain open; this local repair does not prove deployment or fix the other findings.
Full integration check after the repair: **1060 passed / 628 skipped**, no failures
or errors; layout **43/43**. Sanctioned ledger unchanged; local evidence and exact
source hashes retained in `.local/evidence/capture-auth/` (ignored, not public).

Production connection was attempted read-only and rejected with SQLSTATE **28P01**,
including outside the sandbox. No live schema/freshness query completed. Credential
refresh was requested through the environment, never via chat. Code work continues.

Review of the next capture unit also found that B16's proposed status UPDATE is
incompatible with RULE-02 and migration 0012's statement-level mutation trigger.
REQ-CAP-025..027 name lifecycle columns on raw_captures; ADR-0035 explicitly notes
that status cannot be flipped. The serving/lifecycle design must resolve this
contract conflict explicitly before implementation; do not relax the trigger or
quietly claim the current in-memory resilience helpers persist their state.

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


## 2026-09-22 — shared model reservation/dispatch local review

Scope: draft0077/ADR0146 at22a9d2d plus root-owned changes. This is a shared
prerequisite, not completed capture enrichment or backend release.

| Lens | Finding and evidence boundary |
|---|---|
| Contract fidelity | PARTIAL: serialized shared budget, exact caps, request identity and restricted RPCs tested; actual consumer wiring and provider price calibration remain open. |
| Complete user paths | PARTIAL: prepared-request CLI through dispatch/commit ordering is exercised with a connection probe; private-reader/result-consumer orchestration and actual enrichment remain open. |
| Failure behavior | PASS locally: reservation commit uncertainty prevents send; duplicates/expiry refuse; failed provider settles once; uncertain settlement returns no success; private error text suppressed. |
| Data integrity | PASS locally: immutable raw/history retained; failed spend not refunded; stale/duplicate sends refused. No actual two-process or post-commit proof (OQ82). |
| Access/privacy | PARTIAL: disposable role calls deny private reads; direct session identity required. Model redirect credential forwarding reproduced and fixed. Live ACL and process secret separation unverified; source-API redirect issue remains open. |
| Runtime/deployment | NOT VERIFIED deployed: no provider call, role password, job deployment or new production credential. Legacy cursor model calls now refuse; Ask falls back deterministically until isolated consumer is wired. |
| Operations/recovery | PARTIAL: reserved/outcome logs and refusal codes exist; workflow and recovery runbook for separated consumers remain open. |
| Evidence | Source hashes and reports in ignored .local/evidence/model-egress/. No-DB 1073 passed/690 skipped, plus three later CLI tests in a15-case targeted run; full SQL857 passed/1 skipped, chain76/659, layout43/43. Generic RULE04 remains pending. |

Independent reviewer found UTC permit rollover, planning's access to the retry
margin and model redirect credential forwarding. SQL permits now expire at UTC
midnight, client verifies expiry before send, planning stays at9000 and redirects
fail before a new request. Reviewer rechecked the model transport fix; no further
material issue found within this scope. No change authorizes release or frontend.
