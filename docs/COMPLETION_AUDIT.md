# Project completion audit

## Current quality review — 2026-09-22

### Latest unit: isolated reference dispatch — 2026-09-23 (locally integrated)

At b114093 plus root-owned draft0084/ADR0155. This is the source half of the same
voice-to-atoms path; private saved-reference preparation/cache consumption is next.

| Review lens | Result and limits |
|---|---|
| Contract fidelity | PARTIAL: database USDA/OFF ceilings, shared USDA cooldown, exact existing source adapters and receipt binding; source-order/TTL and complete nutrition contracts remain open |
| Complete user paths | PARTIAL: actual reference CLI reaches adapter and receipt-gated stdout in injected tests; private prepared-request/cache-consume bridge and complete capture orchestration still open |
| Failure behavior | PASS scoped redirects, oversized bodies, credentials, changed identity, failed commits, delayed permits, recorded429 and interrupted predecessor recovery; real process crashes not yet exercised |
| Data integrity | PASS scoped immutable request/result digests and explicit uncertain outcomes without fake hashes/statuses; no cache/atom writes by source process |
| Access/privacy | PASS direct-login check, private-read denial and private-stage source-credential rejection; actual production privileges and OS boundaries remain unverified |
| Runtime/deployment | NOT VERIFIED: source CLI exists but is not deployed, scheduled or observed against a live provider |
| Operations/recovery | PARTIAL: durable quota/audit and interrupted-request cooldown policy locally exercised; separate-session kill/restart, bounded process lifetime and unattended recovery remain open |
| Evidence/reproducibility | PASS local scope:939 SQL/1 production-only skip;1181 noDB/772 guarded or dependency skips;83 migrations/829 statements; layout43; targeted123 SQL/32 pure. All handles terminal and disposable server stopped |

Review found the reservation/send-time quota gap; repaired by including permit TTL
in the count window. Session lock covers request through settlement. Self-review
identified lost-response cooldown risk; interrupted predecessors now become uncertain
and conservatively gate USDA for an hour from discovery. Reviewer accepted scoped
repairs. Rollback fixtures and simulated commit acknowledgements cannot establish
real commit durability, concurrent sessions or crash survival. Generic RULE04 remains
pending; full SQL includes scoped spine queries. Feature ledger14/15 is unchanged.
Evidence archive: `.local/evidence/reference-dispatch/`.

### Latest unit: saved extraction to reference-backed atoms — 2026-09-23

Local evidence at dca0ac4 plus draft0083/ADR0154, archived under
`.local/evidence/capture-resolution/`. This advances the same voice-to-atoms outcome.

| Review lens | Result and limits |
|---|---|
| Contract fidelity | PARTIAL: strict receipt-bound extraction, household counts and fractional components exercised; complex quantity/unit language and other profiles remain open |
| Complete user paths | PARTIAL: actual private CLI/service role reaches persisted extraction, cached-reference atoms and readback; isolated reference runtime and complete device/provider path remain open |
| Failure behavior | PASS for tested malformed/nutrient output, quarantine, stale/duplicate delivery, missing references, exact-item recovery and atomic rollback; real concurrency/durability unverified |
| Data integrity | PASS scoped immutable items/components, distinct repeated phrases, time/quantity provenance and default exclusions; generic RULE04 and correction/retranscription lifecycle remain open |
| Access/privacy | PASS tested cache-only private resolution, role denial of private reads for reference egress, model receipt binding and sanitized errors; process launch/production ACLs unverified |
| Runtime/deployment | NOT VERIFIED: hand-run CLI connected; no live provider, deployment, separated supervisor or observed schedule |
| Operations/recovery | PARTIAL: persisted next-stage queue and saved-stage recovery; unattended source refresh/supervisor/device recovery remain required |
| Evidence/reproducibility | PASS local scope:929 SQL/1 production-only skip;1149 noDB/762 skips;82 migrations/815 statements;43 layout checks; full SQL includes invariant queries, generic RULE04 still pending |

Independent review found and repaired hidden quarantine reviews, nutrient leakage,
stale transcription selection, count/serving confusion, private source egress and
lost defaulted provenance. Final follow-up found no remaining scoped repair blocker.
Rollback fixtures and commit-order probes do not establish real commit survival.
Two noDB NumPyro dependency cases remain skipped; feature ledger14/15 is unchanged.
Merged report's673 named requirements with passes is an index, not full coverage.

### Latest unit: private media retrieval (locally verified)

At936f5cd plus dirty sources. This covers the download/preparation boundary, not upload
or complete capture activation. ADR0151 and CAPTURE_RUNTIME describe the limits.

| Review lens | Result and limits |
|---|---|
| Contract fidelity | PARTIAL: immutable reference/hash drives request bytes; upload/hash issuance and existing unbound-media recovery remain open |
| Complete user paths | PARTIAL: prepare-media command is connected to private acquisition/preparation; SQL test verifies service-role engine flow with mocked download; no live capture path |
| Failure behavior | PASS tested invalid origin/path/hash, absent credentials, redirect, oversize and signal deadline; hard native-stall process termination remains supervisor work |
| Data integrity | PASS tested byte/hash binding before request preparation and existing immutable consumption; device provenance and object replacement policies remain unverified |
| Access/privacy | PASS local fixed Supabase destination and model rejection of Storage read capability; effective Storage policies and OS isolation remain open |
| Runtime/deployment | NOT VERIFIED: POSIX CLI deadline implemented; no upload, provider request, deployment or observed schedule |
| Operations/recovery | PARTIAL: documented stage capabilities, pagination and timeout limits; supervisor, upload receipts, legacy media recovery and real replay still required |
| Evidence/reproducibility |18 pure tests passed0.23s;17 SQL passed8.86s; full noDB1111/721skip189.42s; layout43; fullSQL888/1skip249.52s; unchanged79-migration/719-statement chain evidence reused |

Independent review accepted path/digest/redirect and credential boundaries. It found
socket timeout was not a whole-acquisition deadline; a POSIX signal timer now interrupts
a blocking read and preserves signal state. This is not a universal process-kill claim.

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


## 2026-09-23 — M3 upload-to-transcription integration boundary

Scope: HEAD08b967a plus root-owned upload/receipt draft0081 and forward repair0082.
The active outcome remains voice capture to atoms; this boundary is partial.

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: binary hash/identity, immutable upload receipt and raw acknowledgement connected. Device silent ten-second queue/replay remains unimplemented/unverified. |
| Complete user paths | PARTIAL: actual Worker entrypoint and scoped SQL chain upload→raw→transcript exercised in separate harnesses; no device→live Storage→model→atoms run. |
| Failure behavior | PARTIAL: rollback/mismatched receipt/lost completion, duplicate delivery, stalled body and unknown route refusal tested. Real concurrent/post-commit recovery remains unproved under OQ82. |
| Data integrity | PASS for tested local scope: upload identity and raw evidence unchanged, repeated consumption stores one result, transcript is not marked enriched. |
| Access/privacy | PASS for tested local scope: scoped upload/ingress/model/service roles exercised; no private reads granted to uploader/model. New service history SELECT policy repairs previously invisible idempotency receipts without mutation grants. |
| Runtime/deployment | NOT VERIFIED: Worker routes implemented but undeployed. Scoped secrets, private bucket, maximum-size hosting resources and signed device automation remain pending. |
| Operations/recovery | PARTIAL: private hash reconciliation handles ambiguous completed upload; no deployed reconciler schedule or observed device replay. No retention/deletion decision inferred. |
| Evidence/reproducibility | Targeted31 SQL passed19.51s; independent review accepted0082 and route repair. Chain81 migrations/746 statements and layout43 passed. FullSQL902 passed/1 production-only skip256.92s; noDB1111 passed/735 skipped169.40s (DB/live guards plus two NumPyro dependency cases). Both exited0; ledger14/15 unchanged. Generic RULE04 remains pending. |

The connected service-role test reproduced23505 on repeated transcript consumption:
0076 granted SELECT but omitted an RLS read policy on processing history.0082 adds
that policy; the same assertion now passes. Review also caught zero-duration input
and unknown-route fallback, both repaired. No fixture commit or production action.

## 2026-09-23 — Device source packet within M3 voice path

Scope: e4497b0 plus local Scriptable transport and extraction-verifier repair.

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: local save-before-send, UUIDv7, same-ID replay and matching raw acknowledgement tested. Signed Shortcut and native ten-second return remain unverified. |
| Complete user paths | PARTIAL: actual Scriptable entrypoint exercised with platform adapters; real-file queue traverses actual combined Worker with substituted backend transport. No physical-device/live-provider path yet. |
| Failure behavior | PASS locally: offline, wrong/late/upload-only ack, torn publication/ack marker, conflicting metadata, orphan recording and missing source all exercised. Native crash durability/concurrency remains unverified. |
| Data integrity | PASS in tested scope: no source/media deletion, pending removal follows validated raw acknowledgement; recovery never invents missing metadata. Extraction names must occur within their verified spans. |
| Access/privacy | PASS in tested scope: local-only files, one coupled Keychain config, masked manual setup input, redirects refused and endpoint restricted to reviewed Workers route shape; no credentials/network used in tests. |
| Runtime/deployment | PARTIAL: actual scripts and reproducible source zip exist; package truthfully excludes signed Shortcuts. Install, lock-screen execution, native filesystem behavior and deployed endpoint require physical/live verification. |
| Operations/recovery | PARTIAL: recoverable metadata repair and explicit recovery_errors exist; hourly device automation is documented but not installed/observed. Media retention remains undecided. |
| Evidence/reproducibility | Targeted34 passed2.52s; independent read-only review accepted repairs and source packet. Full noDB1122 passed/735 skipped191.56s; ledger14/15 unchanged; layout43 passed. Prior902-pass SQL/chain evidence unchanged; no migration/SQL code changed. |

Reviewer findings (torn metadata, false retention claim, invisible orphan media)
were repaired without weakening acknowledgements. Official Scriptable documentation
supports these APIs, not a native atomicity guarantee. Source-only package:
`.local/device/PersonalOSCapture.zip`, generated by `tools/package_capture_device.py`.

## 2026-09-23 — Private reference handoff within M3 voice path (0085)

Scope: f54f1c9 plus root-owned0085, private reference engine/CLI and source settlement changes.

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: prepared lookup derives only from verified saved extraction; receipt binding and existing deterministic source parser govern cache publication. Automatic source ordering, brand/barcode extraction and365-day refresh remain open. |
| Complete user paths | PASS within local handoff: actual prepare, source dispatch, lost-output reconciliation and resolve CLIs persist expected kcal162/180/198 from a source fixture. No live provider or observed device outcome. |
| Failure behavior | PASS within tested scope: substituted request/result, forged computed nutrients, invalid source match, HTTP failure, stale extraction and alias-write failure cannot publish false resolved output. Lone interrupted reservation and lost settled stdout recover without unrelated traffic. |
| Data integrity | PASS within tested scope: immutable attempts/outcomes/response bodies, source receipt clock for freshness, cache/alias/outcome rollback together and idempotent consumption. Conflicting/expired cache versions refuse; versioned refresh remains open. |
| Access/privacy | PASS within tested scope: actual service/source roles, source historical-body read denied, hash-only settlement denied, private source credentials refused. Source receives bounded item query without capture ID/transcript. |
| Runtime/deployment | PARTIAL: actual CLI functions connected with explicit injected provider and real SQL roles; commits are ordering probes in rollback fixtures. Independent processes, commit survival, supervisor and deployment unverified. |
| Operations/recovery | PARTIAL: reservation reconciliation and atomic response handoff repaired; cooldown persists in SQL state. Real process crash/concurrency, runtime scheduling and native-device recovery remain unverified. |
| Evidence/reproducibility | Capture-reference SQL19 passed14.95s; noDB1182 passed/791 skipped162.13s; chain84/850; layout43; transport33 passed0.32s after owner-dependency test patch. Full SQL958 passed/1 production-only skip288.12s; session83471 exit0, server stopped. Ledger14/15 unchanged; F006 unmatched-ID diagnostic unchanged, generic RULE04 pending. |

Independent review found the old hash-only RPC remained callable by the source role;
0085 revokes it and actual-role tests verify denial. Review accepted this repair and
the owner-bound transport test patch, without claiming process/device proof. Full
noDB evidence predates only the transport-test import rewrite and unused-import
removal; targeted33 tests re-exercised those unchanged assertions. Initial CLI test
used nonexistent config_pytest; corrected to config per the disposable harness.
Earlier layout43 claims missed the test's import before it was tracked; this run
found and repaired it without changing the lint gate. No production action occurred.

## 2026-09-23 — Ordered name lookup and reference freshness (0086)

Scope: ec2cda2 plus root-owned0086/ADR0156 and existing nutrition/capture owners.

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: name-only fresh-cache→Foundation→Branded→OFF sequence uses saved outcomes; Branded/OFF expire after365 days, Foundation/Joe do not. Brand/restaurant and barcode evidence remain open; this does not close full REQ-NUT-001/013. |
| Complete user paths | PASS in local scope: default prepare CLI emits first ordered request after commit; persisted misses advance stages, success stops on fresh cache, all misses reach exact-item review eligibility. Real provider/device path unverified. |
| Failure behavior | PASS in tested scope: reserved request directs reconciliation; deferred provider outcome retries without becoming no-match; stale cache misses; fresh conflicting data refuses; snapshot modes that invalidate lock/read ordering refuse. |
| Data integrity | PASS in tested scope: refresh appends a new food_id/version and retains prior rows/aliases; current aliases follow that identity to newest fresh version under correction precedence. Review projection changes append old reason/knowledge time to immutable history in the same transaction. |
| Access/privacy | PASS in tested scope: private automatic preparation performs no egress; service can update only review tried projection and read its history; history insertion belongs to the trigger owner. Existing source/private separation remains. |
| Runtime/deployment | PARTIAL: actual CLI default, owner engines and SQL roles exercised. Supervisor, independent-session crash/concurrency, deployment and physical device remain unverified. |
| Operations/recovery | PARTIAL: no-match differs from operational hold in both current review item and immutable prior evidence; no repeat source calls are needed merely to advance a saved stage. Live scheduling/storage bounds remain release gates. |
| Evidence/reproducibility | Latest targeted146 passed30.52s; scoped independent review accepted isolation and persisted-review repairs. Chain85 migrations865 statements; layout43. FullSQL972 passed/1 production-only skip340.26s; noDB1182 passed/805 skipped180.64s; all handles terminal, servers stopped. Ledger14/15 unchanged, genericRULE04 pending. |

Review repaired missing READ COMMITTED enforcement in the shared cache publisher and
stale persisted review reasons after outage→three misses→terminal no-match. A further
owner check refuses fresh conflicting reference data and supplies the existing food_id
for an identical concurrent publication. Full release, brand/barcode fidelity and
historical consumer coverage are not inferred from these scoped passes.

## 2026-09-23 — Explicit supplier context in the M3 voice path (ADR0157)

Scope: d70923a plus root-owned context, capture and shared nutrition changes.

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: supported explicit food-from-supplier clauses preserve a verified transcript span without extending the seven-field extraction schema. General brand prefixes, possessives, complex clauses and barcode remain open. |
| Complete user paths | PASS locally for this slice: saved extraction prepares a branded query, consumes a receipt-bound source result, persists atoms and reads back source owner and supplier evidence. No live voice-to-atom proof. |
| Failure behavior | PASS in targeted tests: generic/wrong-brand cache entries cannot satisfy a branded item; ambiguous top-priority identities refuse; two branded-source misses persist brand-preserving review without Foundation fallback. |
| Data integrity | PASS in tested scope: immutable transcript anchors supplier offsets; resolution stores context version; original spoken alias and normalized query survive publication. Exact alias selects identity and correction precedence remains. |
| Access/privacy | PASS in scoped review: context derivation stays private; outbound query carries food and supplier only, not the transcript or evidence offsets. No additional credentials, services or model fields. |
| Runtime/deployment | PARTIAL: private/source interfaces and SQL roles exercised locally. Runtime supervisor, process crash durability, deployment and physical iPhone tests remain open. |
| Operations/recovery | PARTIAL: repeated preparation uses normalized query and reuses successful cache; terminal misses retain context for review. Broader supplier-language support and legacy pending-attempt context compatibility remain unproven. |
| Evidence/reproducibility | Targeted SQL152 passed40.75s; pure12 passed0.10s. Full noDB1194 passed/809 skipped146.63s; ledger14/15 unchanged, existing F006 diagnostic unchanged; staged layout43 passed. Full SQL976 passed/1 production-only skip365.32s, including invariant checks; session44382 terminal exit0, server stopped. No migration changes; prior chain85/865 remains applicable to unchanged SQL. |

Independent scoped review caught a repeat-lookup mismatch when the extracted name
included the supplier clause. Preparation now uses the same normalized food query
as publication/resolution, and regression coverage verifies both cache reuse and
original spoken alias retention. Review accepted the repair and strengthened
wrong-brand/no-match cases. Generic RULE04 remains pending; no production action.


## 2026-09-23 — Runtime progression and model response recovery (0087, locally integrated)

Scope: b46846f plus root-owned0087/ADR0158, private advance CLI and bounded model worker.

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: saved stage progression preserves REQ-CAP-025/026/034/050 and quarantine; retry creation requires explicit scheduled retry, existing result consumption does not. Full schedule/profile/language contracts remain open. |
| Complete user paths | PARTIAL: actual private CLI with SQL roles traverses voice preparation, saved transcription/extraction, reference request/receipt and immutable atoms/readback. Real provider, independent role services and physical device remain unverified. |
| Failure behavior | PASS in tested scope: lost stdout, duplicate/unconfirmed reservation ownership, timeout/reaping, provider errors, budget holds, invalid extraction/quarantine, oversized response and commit failure covered. Supervisor SIGKILL/host loss before durable completion remains an explicit hold. |
| Data integrity | PASS in tested scope: body/digest/status settlement is atomic, immutable and receipt-bound; interrupted calls retain budget charge; stopped-call reconciliation preserves saved successes; raw rows and atoms remain immutable. |
| Access/privacy | PASS locally: old hash-only/status RPCs revoked from model role; historical bodies private; only model role can reconcile its stopped call. Model worker refuses foreign credentials/disposable launch and passes an env allowlist. Separate OS secret-file isolation not yet deployed/proven. |
| Runtime/deployment | PARTIAL: real child timeout/reap and actual private CLI exercised; no mixed-credential parent added. Durable scheduler handoff, reference supervisor, installed schedule and live provisioning remain open. |
| Operations/recovery | PARTIAL: receipt recovery, source-stage progression, explicit retry gate and quarantine prevent blind retries. Missing acknowledgements remain unconfirmed; orphan recovery requires ownership evidence. Storage retention and full crash recovery remain release work. |
| Evidence/reproducibility | Targeted runtime30 passed24.80s, recovery89 passed88.34s, process/dispatch37 passed2.39s. Full noDB1214 passed825 skipped149.70s; chain86/877; staged layout43; ledger14/15 unchanged. Full SQL992 passed/1 production-only skip311.68s, including invariant suite; session25546 exit0 and server stopped. GenericRULE04 pending. |

Review found disposable-marker loss in child environment and missing quarantine
handling. Integration tests exposed SQL NULL-head lookup generating duplicate work,
and a retry-creation gate incorrectly preventing receipt consumption. These were
repaired with unchanged acceptance assertions and new behavioral regressions.
No production action, physical capture or independent SQL commit-survival proof.


## 2026-09-23 — Worker mailboxes and private queue connection (integration in progress)

Scope: dirty sources after5356c09,0088/ADR0159. Full noDB26545 and SQL51143
were launched against pre-review sources archived under
`.local/evidence/capture-mailbox/pre-review-sources.json`; reader-group repair
followed. Do not treat these runs as final evidence for later repairs.

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: existing CAP025/026/038 owners now connected through private worker; nightly retry cursor is operational UTC state, not a measurement definition. Installed nightly run and full capture profiles remain open. |
| Complete user paths | PARTIAL: actual private worker/SQL roles verify preparation, budget deferral and retirement; prior private runtime reaches atoms. No deployed multi-identity voice/provider path. |
| Failure behavior | PARTIAL: commit ambiguity retains work; failed poll entries advance fairly; terminal controls prevent redispatch; saved SQL success overrides stale budget control. Host-loss and simultaneous-process proofs remain open. |
| Data integrity | PASS in targeted scope: request identities immutable, payload hashes bind retirement, SQL owns processing outcomes, raw captures preserved. Files never substitute for successful SQL evidence. |
| Access/privacy | PARTIAL: per-role guards and ACL tests; mailbox owner/group/mode checks, no symlink/FIFO reads. Root review repaired reader-group inheritance with explicit group assignment and fail-closed publication. Actual OS identities/secret permissions not deployed. |
| Runtime/deployment | PARTIAL: bounded outbound child supervision, one-capture private polling and durable cursors implemented. Private DB/lock stall bounds and installed service-manager packet remain open. |
| Operations/recovery | PARTIAL: regular/nightly cursors, daily gate, failure status and request retention tested. Capacity/retention, supervisor-host-loss ownership and observed schedule/freshness remain open. |
| Evidence/reproducibility | Pending full suite/reviewer completion. Chain87 migrations880 statements clean, session67388 terminal0. Targeted reader-group/mailbox/private22 passed0.62s before temporary-file creation-mode hardening. No full release claim. |


Integration disposition: fullSQL1000 passed/1 production-only skip439.31s,
terminal51143/server stopped; fullnoDB1246 passed833 skipped250.53s, terminal26545.
Ledger14/15 unchanged, F006 unmatched test-ID warning unchanged. Skips include
guarded SQL/live checks and two NumPyro cases. Chain87/880 and stagedlayout43 pass.
Full suites cover the pre-review source manifest; final reader-GID/temporary0600
repair has22 scoped tests passing0.45s. Final source hashes archived separately.
Independent read-only review found no new reproducible blocker in commit ordering,
receipt precedence, identity binding, poll progress or GID repair. No deployment,
OS isolation, host-loss, private invocation deadline or retention proof. Generic
RULE04 remains pending; invariant suite passed within fullSQL. These results close
local handoff integration, not the full M3 voice path or M6 release.


## 2026-09-23 — Capture service activation packet after b2078cd (checks running)

| Lens | Evidence and remaining gate |
|---|---|
| Contract fidelity | PARTIAL: CAP026 regular/nightly semantics and incomplete daily gate tested; observed nightly work and full capture profiles remain open. UTC06 service window is operational scheduling, not measurement-day interpretation. |
| Complete user paths | PARTIAL: private SQL path reaches enriched atoms then recovers all three stages' leftover request files via actual polling; process entry refuses missing credentials. Real multi-identity/provider/device path remains open. |
| Failure behavior | PASS in scoped local cases: real SIGKILL cursor and temporary-file recovery, competing writer refusal, budget hold, ambiguous commit retention and failed sweep preservation. Independent SQL crash durability and provider-supervisor host loss unverified. |
| Data integrity | PASS in tested scope: transient retirement requires matching immutable SQL outcome/payload; raw/atom counts unchanged. Control cleanup removes only orphan transport projections. No authoritative data eviction. |
| Access/privacy | PARTIAL: role secret-file ownership/mode/type, inherited-credential refusal and fixed exec environment tested; generated plists carry no secret. Dedicated OS users/channel groups/ancestors still unprovisioned. |
| Runtime/deployment | PARTIAL: private120-second process bound, existing outbound90+10 bounds, nonblocking locks, four generated plists pass plutil. No installed daemon or real schedule evidence; filesystem/host failure bounds remain limited. |
| Operations/recovery | PARTIAL: one-entry cleanup cursors,1024-file/1GiB channel caps and64MiB reserve tested. Exhaustion retains work; operator restores space when cursor writes cannot proceed. Deployed monitoring, media/SQL retention and host-loss ownership remain open. |
| Evidence/reproducibility | Final targeted46 recovery/retention tests and23 entry/service tests pass; targetedSQL10 pass8.17s. Full noDB60268/SQL79887 running, manifest .local/evidence/capture-services/source-hashes.json. No migration changed since verified87/880 chain. |

Independent review identified abandoned temporary accumulation; repaired with
exclusive-lock owner/type/name checks and real SIGKILL/hardlink regressions.
Reviewer accepted the repair and found no scoped launcher/schedule blocker.
An initial test insertion misplaced an existing contention test body; restored its
original assertions and all targeted checks pass. No threshold/gate was relaxed.


Service integration disposition: fullnoDB1285 passed833 skipped181.01s;
fullSQL1000 passed1 production-only skip335.68s, server stopped. Both handles
terminal0 (60268/79887). Stagedlayout43 and four plutil checks pass; code hashes
match the launch manifest. No SQL migration changed; prior87/880 chain applies.
Ledger14/15 unchanged; F006 evidence-name warning unchanged. Skips cover guarded
SQL/live checks and two NumPyro dependency cases. GenericRULE04 pending; invariant
suite covered by fullSQL. Evidence archive `.local/evidence/capture-services/`.
This closes local operational integration only; all deployment/physical/host-loss
limits above remain. Next voice-path contract defect: verified possessive supplier
context currently drops brand and can route a named item through generic lookup.
