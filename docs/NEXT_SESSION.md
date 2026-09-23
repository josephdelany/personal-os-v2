# Autonomous backend control — 2026-09-22

This is the single active instruction sheet. Follow EXECUTION_PLAN's autonomous
loop and M0–M6; older checkpoints below are evidence, not competing task orders.
Joe's `/goal` is active. Do not start backend execution from the monitor.

<!-- backend-control:start -->
```json
{
  "version": 1,
  "status": "running",
  "updated_at": "2026-09-23T13:50:19.517523+00:00",
  "last_progress_at": "2026-09-23T13:50:19.517523+00:00",
  "unit": "M3-B16-voice-capture-to-atoms",
  "next_action": "Same M3 voice-to-atoms unit:0085 private reference handoff is connected through actual CLIs and locally verified, including lone-orphan and lost-stdout recovery. FullSQL958/1skip288.12s; noDB1182/791skip162.13s; chain84/850; layout43; all handles terminal and disposable servers stopped. Scoped review accepted repairs. Next enforce automatic source order and365-day cache refresh through the existing nutrition owner, then separated runtime supervision and process/device proof. No production access/deployment; full M0\u2013M6 remains active."
}
```
<!-- backend-control:end -->

## Current active unit — M3 / B16 voice capture to persisted atoms

Joe's 2026-09-22 steering: align execution with the working plan and stop
switching among prerequisites without completing a usable outcome. EXECUTION_PLAN
remains the only delivery plan. This checkpoint selects one acceptance outcome;
it does not reduce M3 or the full M0–M6 backend goal.

**Outcome:** an authenticated voice food capture follows the actual runtime path
from private media upload and immutable raw receipt through saved transcription,
validated extraction and atom persistence to owner readback with provenance.
The finish line is an exercised path, not another helper, migration or green suite.
B16 Scenario 1 supplies the consumer; current requirements and accepted ADRs
supersede its historical raw-update and retry wording.

**Binding coverage:** REQ-CAP-011/012 (receipt and immutability), 025–027
(recovery), 030–042 (transcription and shared budget), 050–060 (extraction and
provenance), and Scenario 1's reference-backed nutrition requirements. Reuse the
existing nutrition owner; do not let model output become nutrient quantities.
ADR-0020 preserves process separation; ADR-0144/0148 preserve append-only history
and transcription results. Photo, other capture profiles, the remaining Ask and
nutrition gates, and M4–M6 remain open under the existing plan.

**Acceptance gates, in execution order:**
1. Authenticated upload binds bytes to the capture identity; ingestion retains raw
   evidence before model work. Same-UUID retries cannot replace media or duplicate
   facts. Finish the current upload boundary only to support this consumer.
2. The runtime connects existing private preparation, isolated budgeted dispatch
   and private result consumption. A saved transcript proceeds to extraction;
   retries resume the saved stage rather than repeating completed model work.
3. Verified extraction reaches atom persistence and owner readback. Each accepted
   field retains its evidence/provenance and raw-capture link; invented spans and
   prohibited model-generated nutrient values are rejected and logged.
4. Exercise missing media, invalid extraction, provider failure, exhausted budget
   and duplicate/stale delivery through that path. Raw evidence survives; no false
   enriched status or fabricated atom appears. Recovery and status are observable.
5. Record local integration evidence separately from deployment and a real voice
   capture. Prepare the concrete activation packet before any required approval.
   A mocked provider or disposable SQL proof does not close the real-capture gate.

**Work selection:** finish these connected steps before starting unrelated Ask,
domain work, new monitors, generic refactors or additional planning documents.
Add a prerequisite only when a named gate above cannot pass without it. Record
that failing gate and the smallest repair. Switch only for a concrete external
hold or urgent integrity issue, as EXECUTION_PLAN requires. Report the gate closed,
what the user can exercise, and the next missing gate; test counts are evidence,
not milestone completion. Apply the plan's existing eight review lenses at the
integration boundary rather than creating another checklist.

**Current integration checkpoint — private reference handoff0085:** saved verified
extraction now prepares a bound lookup; isolated source settlement stores an immutable
exact response and receipt atomically; private consumption reparses source-owned raw
food, publishes cache/alias/outcome together and feeds the existing atom resolver.
Actual prepare/source/reconcile/resolve CLIs were exercised with respective session
identities and an injected source, deliberately discarding source stdout. Readback
returned the expected nutrition interval; only one provider transport call occurred.
Source workers cannot read historical bodies or use the old hash-only settlement RPC.

Lone abandoned reservations reconcile under the dispatcher's lock without unrelated
traffic, retaining uncertainty and USDA cooldown. Lost settled output recovers from
saved response bytes. Mismatched receipts, altered nutrients, wrong source matches,
HTTP failures, stale work and partial cache writes cannot publish false success.
Independent review found and repaired the old-RPC bypass; final scoped review found
no remaining blocker within this handoff. Commit probes remain rollback-only: they
do not prove independent processes, real crash durability or concurrency.

Final evidence at f54f1c9 plus root-owned0085 sources: capture-referenceSQL19 passed
14.95s; fullSQL958 passed/1 production-only skip288.12s; fullnoDB1182 passed/791 skipped
162.13s; chain84 migrations850 statements; layout43; final transport33 passed0.32s.
FullnoDB predates only the test's owner-dependency import patch and unused-import
removal, both covered by targeted33. Skips remain guarded DB/live checks plus the two
NumPyro dependency cases. Ledger14/15 unchanged, unmatchedF006 diagnostic unchanged,
genericRULE04 pending. All handles terminal (SQL83471 exit0); servers stopped.
Archive `.local/evidence/capture-reference/`. Initial CLI test used nonexistent
config_pytest instead of the fixture's config; repaired from harness evidence.
Layout caught an earlier test's direct network import after tracking; test now patches
the existing egress owner's dependency without weakening the lint. First narrowed
SQL launch hit sandbox shared-memory restriction; approved rerun completed.

**Next dependent operation:** automatic source ordering and365-day Branded/OFF cache
refresh through the existing nutrition owner. Current lookup can return expired
entries;0085 refuses conflicting/expired cache publication rather than claiming a
refresh. Explicit source selection is not REQ-NUT-001 completion. Keep brand/barcode
extraction, quantity language, asymmetric daily-total point behavior and separated
supervisor/process/device proof open in this same voice path. No production call,
write, deployment or physical-device observation occurred. Full M0–M6 remains active.

**Current integration checkpoint — isolated reference dispatcher:** root-owned0084/ADR0155
adds actual `tools/reference_egress.py`, dedicated connection/direct-login checks,
shared persisted USDA/OFF quota reservation, durable pre-send audit, immutable
request/response digest receipts and persisted USDA429 cooldown. It reuses existing
source adapters and migration0072 meters. A session lock spans reservation, HTTP
and settlement; quotas include the60-second permit lifetime. Initial source
transport defect (redirect following/unlimited body) is repaired with HTTPS-only,
redirect refusal and2MiB bounds. Private capture stages reject source credentials.

Final evidence at b114093 plus recorded sources:123 targeted SQL passed14.53s;
32 pure passed0.39s; fullSQL939 passed/1 skipped341.04s; full noDB1181 passed/772
skipped207.21s; chain83 migrations829 statements; layout43; diff clean. All handles
terminal and disposable server stopped. Archive `.local/evidence/reference-dispatch/`.
SQL skip is production-only shape inspection; noDB skips are guarded DB/live checks
and the two existing NumPyro dependency cases. Ledger14/15 unchanged; generic RULE04
remains pending despite scoped spine queries passing in fullSQL.

First targeted launch was sandbox-rejected; approved disposable rerun passed.
Reviewer found delayed permits could escape quota accounting; count window now
includes permit lifetime and session lock spans reservation through settlement.
Self-review found loss of response could lose cooldown: the next owner appends an
uncertain outcome with NULL hash/status and starts a full USDA cooldown at discovery.
Denied permits commit that maintenance. Reviewer accepted scoped final repairs;
actual separate-process crash, concurrency and commit-survival proof remains open.
Earlier fullSQL938/noDB1181 results were superseded by final runs after this repair.
This dispatcher is not the complete capture runtime: private saved-request preparation,
receipt-bound cache consumption, source-order/TTL fidelity and supervision remain
open. No source call, private production read or deployment occurred.

**Current integration checkpoint — extraction and reference-backed atoms:**
Draft0083/ADR0154 connects saved transcription to receipt-bound strict extraction,
then the actual private `resolve` CLI to the existing nutrition owner. Immutable
attempts/outcomes/fields and per-item/component atom identities preserve retry and
repeated-phrase behavior. Extraction quarantine reaches the owner review RPC;
readback includes source, evidence, intervals and time/quantity provenance.

Private resolution is cache-only under ADR0020. Missing reference data stays pending;
a later cache entry resumes the saved extraction and closes only that item's
unresolved record. Supported household counts map to reference servings; fractional
Branded counts persist separate whole/portion components. Defaulted time/quantity
is retained in evidence but excluded from statistics, with omissions disclosed in
nutrition-day. Empty totals remain missing, not zero. All writes in each consume or
resolve operation share a rollback boundary; raw captures remain immutable.

**Evidence at dca0ac4 plus root-owned draft, 2026-09-23:** full disposable SQL
929 passed / 1 skipped (256.76s), noDB sanctioned ledger run1149 passed /762 skipped
(162.92s), migration chain82 files/815 statements, layout43 passed. All handles
terminal, disposable server stopped. SQL skip is the explicit production shape
check. noDB skips cover guarded DB/live checks and two existing NumPyro dependency
cases; ledger14/15 unchanged, generic RULE04 remains pending. Evidence archive:
`.local/evidence/capture-resolution/`. CLI commit-order probes and rollback fixtures
do not prove real commit durability or concurrent processes.

Independent review repaired quarantine visibility, nutrient leakage, unsupported
count token acceptance, stale transcript selection, count-to-serving mapping,
private reference egress, and missing defaulted quantity/time exclusions. Final
follow-up found no remaining blocker within those repairs. Runtime orchestration,
production and physical-device behavior were outside that review's proof.

**Next dependent operation:** connect isolated reference prepare/fetch/cache-consume
runtime so cache misses recover through actual separate processes. Then complete
quantity language/unit conversion, conservative rejection of legitimate nutrient-
bearing food phrases, and separated runtime supervision. The nutrition daily-total
owner's midpoint behavior for asymmetric intervals also remains open. Do not start
unrelated work or call capture complete: all five acceptance gates above still
require the remaining runtime and observed-device evidence. Root owns draft0083,
engines/CLI/tests/CI and maintained docs; reviewer is read-only.

The device sections below describe preceding checkpoints; their old next-action
sentences are historical, superseded by the next dependent operation above.

**Current checkpoint — device source packet verified locally:** actual Scriptable
queue → actual combined Worker regression now preserves the original ID/time/bytes
and removes pending only after raw acknowledgement. `PersonalOSSetup` uses a masked
on-device token field and one coupled local Keychain configuration; no setup request.
`tools/package_capture_device.py` produces `.local/device/PersonalOSCapture.zip`
with source hashes and explicit unsigned/uninstalled status. Independent review found
no further material blocker in this local scope. README contains physical acceptance
steps; it is not a generated/signed Shortcut or an installed hourly automation.

Full noDB ledger writer1122 passed/735 skipped191.56s at e4497b0 plus current
changes; layout43 passed, diff check clean, archive `.local/evidence/capture-device/`.
Ledger14/15 unchanged. Skips remain guarded DB/live tests and two NumPyro dependency
cases; generic RULE04 pending. No migration/SQL code changed, so prior902-pass SQL
and81-migration chain evidence is reused. All handles terminal; no running tests.
Joe was reminded to refresh the normal production DB secret at the activation
boundary; no new production access occurred and no secret was requested in chat.

Next executable backend action: reproduce the missing saved-transcript→persisted
extraction consumer, then add receipt-bound private prepare/consume stages and
atomic item/atom output. Cover REQ-CAP-050–060/063–066 and Scenario9 before marking
any capture enriched; reuse the shared budget, append-only processing history and
nutrition owner. Keep device installation/signed Shortcut/physical observations open
alongside this same user path; do not substitute this source packet for those gates.

**Current device draft (after committed upload integration e4497b0):** Joe
approved free Scriptable as a local transport helper; Shortcuts still owns recording.
ADR0153 records cost/privacy before introducing the helper. `device/scriptable/`
contains actual Scriptable entrypoint and queue module plus installation/acceptance
instructions. Source recording is copied before dispatch; each capture has a UUIDv7,
retained metadata and local JSONL entry. Matching raw202/duplicate200 removes only
the pending line; media/manifests remain. Redirects refuse; a separate ten-second
wait timer ignores late receipts. Native idle timeout alone is not a total deadline.

Reviewer found torn metadata publication, false retained-source reporting and orphan
media omitted from recovery. Repaired: validated saved metadata repairs partial
publication, mismatched pending metadata cannot send, acknowledgement marker is
validated before pending removal, unavailable metadata is counted without invention,
and errors report unconfirmed. Node exercises the actual Scriptable entrypoint with
platform adapters and real temporary files; it does not prove native iOS persistence,
timing or app lifetime. Device install, signed/generated Shortcuts, hourly automation
and physical acceptance remain open. No server or device was contacted.

While the helper choice was pending, extraction review reproduced an invented-name
hole: real bagel evidence could mark salmon extracted. `resolve_field` now requires
the name within the verified span (case-insensitive, word boundaries); malformed,
empty and boolean-offset spans refuse. Big Mac within a Big Mac remains valid.
This verifier repair does not itself persist extracted items or close gate3.

Latest targeted check: `env -u SUPABASE_DB_URL PYTHONPATH=. python3 -m pytest -q
tests/test_capture_http.py tests/test_extraction.py` passed34 in2.36s (HTTP harness
includes14 device Node cases and24 Worker cases; extraction33). Layout43 passed; git diff --check clean. No test process remains live. Root owns device draft,
extraction verifier/tests and docs; no other writer. Prior upload integration and
full-suite results below are historical evidence, not instructions to redo them.

**Current state / ownership:** root owns draft0081, ADR0152,
`supabase/capture_storage_policies.sql`, `tests/test_capture_media_receipts.py`,
capture_transcription engine/CLI additions, SQL harness and maintained docs.
These uncommitted changes preserve upload identity and completion as separate
immutable facts; reconciliation verifies hash/size. They are a partial dependency
of gate 1, not a delivered upload/runtime path. Preserve this work. No other file
writer is assigned. Private media/transcription foundations are committed at
`08b967a` and `936f5cd`; reuse them.

**Upload connection implemented locally:** `workers/capture-media/index.mjs` now
checks authentication before reading bytes, hashes a bounded body, commits upload
identity, uploads with replacement disabled, validates the Storage path and commits
the completion receipt. Confirmed retries avoid another upload. Ambiguous responses
remain unconfirmed for private reconciliation. Root additionally owns this Worker,
its configuration, the shared ingress authentication export and HTTP tests/harness.
`node --test tests/capture_media_http.test.mjs tests/capture_http.test.mjs`: 18 passed.
Transport is substituted; vendor behavior, hosting memory/CPU at the maximum file
size, device integration and live permissions remain unverified. No gate closed yet.

**Combined device backend connection:** the explicit `/capture` route accepts
binary media plus retained device identity/metadata, confirms media, then invokes
the existing ingress handler. It returns 202/duplicate200 only after committed raw
receipt. `/upload` remains media-only; all other paths return404. Independent review
identified zero-duration voice acceptance and unknown-path upload fallthrough;
both repaired with no-read/no-send regressions. A stalled-body test also proves
cancellation cannot upload a truncated prefix. Latest Python HTTP harness passed
in0.26s (24 underlying Node cases). Worker README records the exact device contract.
Actual Shortcut generation, ten-second silent queue/replay and real device execution
are still missing, so gate1 remains partial. Root owns these route/docs/test changes.

**Connected SQL finding and repair:** upload→raw ingress→private media preparation
→scoped model reservation/settlement→private consumption now runs through actual
RPCs in one rollback-only transaction. It exposed repeated consumption failing23505:
service_role could not see processing events through RLS. Forward0082 supplies the
missing SELECT policy, preserving existing mutation denials. Same test now confirms
one raw capture/result and no premature atoms. Reviewer accepted repair scope.
Targeted31 passed19.51s, chain81 migrations/746 statements passed, layout43 passed.
FullSQL902 passed/1 skipped256.92s; noDB1111 passed/735 skipped169.40s.
Both handles exited0; disposable server stopped. No test process remains live.
Logs are `/tmp/capture-upload-full-sql.log` and `/tmp/capture-upload-full.log`.
Evidence archived in `.local/evidence/capture-upload/`. The SQL skip is the
production-only check; noDB skips cover disposable/live DB tests and two NumPyro
dependency cases. Existing generic RULE04 remains pending. Feature ledger remains
14/15 and is not a backend completion score. Root additionally owns0082 and COMPLETION_AUDIT.

**Latest verification:** at HEAD `08b967a` plus the current upload draft,
`env -u SUPABASE_DB_URL PYTHONPATH=. python3 tools/test_local_sql.py --tests
tests/test_capture_media_receipts.py tests/test_capture_transcription.py
--junitxml=/tmp/capture-upload-targeted.xml` completed: 29 passed in 15.95s;
`/tmp/capture-upload-targeted.log` confirms disposable server shutdown. Independent
review accepted the scoped receipt/policy design. That targeted run is terminal; the newer full integration runs are listed above.

**Holds and limits:** no actual upload, live model call, deployed policy, complete
runtime or real voice-to-atoms observation is established. Production verification
is held on SQLSTATE 28P01; Joe owns refreshing the normal secret configuration.
Remind at the next production verification/deployment boundary, not repeatedly
during local work. Unknown-hash legacy media remains unresolved. M1 regains
priority when its recovery dependencies are actionable. These holds do not block
local completion of this path. Do not infer permission to deploy or send data.

## Completed local unit — private media acquisition

- Root owns lib/db.py, lib/egress.py storage credential guard, capture_transcription
  engine/CLI/tests, new tests/test_capture_media.py and ADR0151. Private download
  now validates captureUUID/filename, immutable SHA256, fixed private Supabase host,
  credentials, redirect refusal,50MiB size cap and30-second socket timeout.
  Review confirms boundary checks. A45-second POSIX main-thread SIGALRM now also
  bounds acquisition including body/hash checks, preserving existing timers/handlers.
  Native-stall hard process termination remains a supervisor responsibility.
-18 pure tests passed0.23s (including real timer interruption);17 disposableSQL
  passed8.86s, rollback/server shutdown
  confirmed. Layout43 passed. SQL uses mocked download; transport uses mocked opener.
  No live media/network call. Independent review accepted the deadline repair with
  native-stall limitation recorded. Full noDB1111 passed/721 skipped189.42s;
  fullSQL888 passed/1 skipped249.52s;layout43. All processes exit0 and disposable
  server stopped. Chain79/719 reused with unchanged migrations verified by Git.
  Logs /tmp/capture-media-full.log and full-sql.log/XML; archive `.local/evidence/capture-media/`.
  Full feature ledger14/15 is not backend completion; generic RULE04 remains pending.
- Still required: actual upload/hash receipt and bucket policy, trusted recovery for
  unbound legacy media, Shortcut payload generation, extraction/atoms and separated
  runtime/schedule. Strict hash refusal alone does not close capture recovery.

Transcription foundation committed at `936f5cd`; clean worktree verified before this
checkpoint update. Next work must bind actual private media to its immutable capture
and connect extraction/atom persistence plus separate runtime stages. Do not treat the
prepared-payload CLI or queue pagination as a deployed capture path.

## Completed local unit — capture transcription foundation

- Root owns migration0080/ADR0150, capture_transcription engine/CLI/tests, shared
  egress/model_contract and dispatch CLI/tests, capture_budget/tests, processing
  immutability test, SQL harness and maintained docs. No parallel file writer.
- Atomic immutable result/history consumption verifies exact settled request/response
  and capture/model/kind/cost. `transcribed` is intermediate; extraction still required.
  Stale results remain history but never current. Usable text survives extraction failure.
- Reviewed repairs: actual service voice read policy, immediate empty-transcript review,
  bounded committed HTTP error receipts, single audio-cost owner and paginated queue.
  Actual private CLI/service identity and model denial are tested. Pure validation does
  not prove uploaded media belongs to the capture; Storage adapter remains required.
- Final evidence:887 fullSQL passed/1 skip265.83s;1093 noDB passed/719 skip160.36s;
  79 migrations/719 statements;43 layout checks.16 captureSQL10.10s;56 broader targeted
  33.42s before added queue pagination case. NoDB collection predates that final SQL-only
  case; fullSQL covers it. Feature ledger14/15, generic RULE04 pending. No active tests;
  fullSQL/chain/noDB process handles returned exit0, disposable servers stopped.
- Final read-only review found no further blocker in this local scope. Remaining:
  media-source binding/acquisition, native dictated text/photo paths, extraction into
  atoms, separate runtime orchestration and observed nightly execution. No live model,
  production query/write/deploy, or commit/concurrency durability proof occurred.
- Reports: `/tmp/capture-transcription-full.log`, matching full-sql XML/log,
  chain/layout logs; archive `.local/evidence/capture-transcription/` with source hashes.
  Dependencies committed together at `936f5cd`; continue capture delivery. B16 historical
  raw-update/three-retry wording is superseded by current CAP requirements/ADRs.

## Completed local unit — separated Ask stages and insertion-time integrity

- Prior unit committed at `cd02e43`. Root now owns drafts0078/0079, ADR0147/0149,
  `lib/model_contract.py`, dispatcher/db consumers, `tools/ask_jobs.py`,
  `tools/engines/ask_jobs.py`, `tests/test_ask_jobs.py`, affected reservation/dispatch/
  ingress tests, SQL harness and maintained docs. These changes are now committed at `d3639a3`.
- Joe **approved OQ84** this turn. REQ-CAP-034 and ADR0148 now require append-only
  transcript/timing results linked to capture/attempt and selected through effective
  history. No further approval is needed for that storage contract. Media retention
  and deployment permissions remain separate. Finish this bounded Ask piece, then
  return to actionable capture enrichment.
- Draft0078 persists immutable question, as-of and server known-at cutoff, registry
  options, fallback, complete per-attempt dispatch parameters and outcome receipts.
  Private prepare/readback/consume/fail stages refuse provider credentials. Actual
  service_role calls now exercise metadata grants/policies and owner-checked Ask.
  CLI trusts only direct matching postgres/service_role session/current identity
  before setting the existing owner's SQL context; model identity is rejected.
- Shared canonical JSON bytes bind prepared payload to budget reservation. Independent
  review found response substitution was possible: four-argument settlement now
  appends an immutable response digest; consumer checks both digests plus saved model,
  kind, cost and null capture binding. Old three-argument settlement is revoked from
  model role. Review also repaired missing service metadata access, privacy refusal
  fallback and pending request parameters drifting with model/cost configuration.
- Bounded invalid-plan retries stop at5 with refusal+nearest and no evidence tier.
  Saved fallback handles budget/provider/privacy failure. Changed duplicate inputs
  refuse; repeated outcomes return stored transition. Readback resumes latest state.
  Actual IPC/hosting/orchestration is still missing; no live model call was made.
- **Integrity defect reproduced:** a later atom changed delayed-answer max100 to9100
  despite the question's fixed known_at. Full-chain diagnosis found0012's forced
  recorded_at=now() stamps transaction start, not insertion. Draft0079 forces server
  clock_timestamp for future raw/atom inserts; no existing data changes. Receipt
  test now brackets insertion by server clocks; late-atom exclusion remains strict.
- **Integration evidence:** 54 focused SQL tests passed (17.58s), 15 dispatcher
  tests passed (0.13s), 1076 no-database tests passed (704 skipped), and 871 full SQL
  tests passed (1 skipped). All 78 migrations / 689 statements applied from empty;
  all 43 layout checks passed. Disposable server shutdown confirmed. Reports are
  `/tmp/ask-jobs-full.log`, `/tmp/ask-jobs-full-sql.xml`,
  `/tmp/ask-jobs-chain.log`, and `/tmp/ask-jobs-layout.log`. Refresh the evidence
  archive/source manifest before commit; its earlier targeted snapshot is stale.
- **Current-cutoff repair verified:** migration0079 preserves installed function
  bodies and ACLs while changing the exact current-read wrapper/default whitelist
  to statement_timestamp(). Current APIs see the late insertion (9100), while the
  saved Ask question excludes it (100). Independent review found no new blocker.
  Commit visibility remains a separate unproven snapshot issue/OQ82; historical
  measured-search replay still ignores its known-at cutoff. Generic RULE04 is open.
- **Next:** refresh evidence/integration notes and commit the reviewed local unit,
  then implement approved capture results and enrichment consumption. Explicit
  as-of remains required by the private CLI pending one shared default-date owner.
  Full REQ-ASK-005 read/write separation and live separated orchestration remain open.

## Committed prerequisite — durable shared model reservations

- Prior turn made progress: processing foundation committed at `22a9d2d`; clean
  worktree verified before starting this prerequisite. Prior integration evidence
  below applies to that commit, not the new draft.
- Root owns uncommitted migration0077, ADR0146, `tests/test_model_reservations.py`,
  SQL-harness registration and maintained docs. No parallel implementation worker.
- Draft serializes shared budget reservations under one transaction lock, rejects
  invalid/nonfinite costs, binds request UUID to digest and metadata, refuses any
  duplicate dispatch, and preserves failed spend. Restricted model_egress role can
  reserve/settle but cannot read private tables or owner review APIs in the fixture.
- **Runtime added:** `lib.egress.dispatch` verifies direct model_egress session
  identity, commits reservation before send, enforces monotonic permit expiry and
  commits settlement separately. Uncertain reservation commit sends nothing;
  duplicate permits refuse; uncertain settlement returns no successful result.
  `tools/model_egress.py` accepts prepared stdin and outputs correlated results for
  a private consumer. `lib.db.connect_model_egress` uses a dedicated environment
  credential and rejects broad DB credentials. The role has LOGIN with PASSWORD
  NULL; no credential was provisioned. Existing cursor-based call refuses real
  dispatch; Ask retains deterministic fallback until separated orchestration exists.
- **Review repaired:** UTC permit rollover, planning borrowing capture retry margin,
  and default model HTTP redirects forwarding Authorization. Model redirects now
  fail before following any new destination. Independent reviewer rechecked fixes.
  Source-API GET redirect/capability handling remains an independent open issue.
- **Integration:** 857 disposable SQL passed/1 skipped (257.06s); 1073 no-DB
  passed/690 skipped, zero failures/errors (202.55s). Three supplementary CLI checks
  were added afterward; all15 dispatcher/CLI tests pass (0.21s). The full no-DB
  count excludes those three later checks. Chain76 migrations/659 statements;
  layout43/43. Feature ledger unchanged14/15; F006 no-DB skip is covered by SQL.
  Generic RULE04 pending; disposable spine invariants passed. Reports/source hashes
  under ignored `.local/evidence/model-egress/`, at22a9d2d plus root changes.
- **Still open:** scoped commit; actual separated private-reader/provider/result
  orchestration and Ask/capture consumers; live effective ACL, production role
  provisioning, real provider request/observed schedule and post-commit durability/
  concurrent proof (OQ82). Connection probes prove ordering, not actual commits.
- OQ84 was subsequently approved by Joe; see ADR0148 and current unit above.
  No production action was authorized by that storage decision.

## Completed local foundation — append-only capture processing history

- **Committed foundation:** `22a9d2d` includes migration0076, processing engine/CLI/
  tests, nightly maintenance workflow, ADR0145, SQL harness and maintained docs. Targeted processing + ingress
  SQL tests passed **43/43** (10.87s), with rollback and server shutdown confirmed.
  Latest reports: `/tmp/capture-processing-targeted.log` and matching JUnit XML.
- **Implemented locally:** immutable outcome history, current-status view, stable
  pending age across repeated failures and budget deferrals, predecessor matching,
  idempotent attempts, and retained stale outcomes that cannot become current.
  Existing raw terminal states survive projection. Deferred-only captures do not
  acquire an invented provider-failure age. Raw captures remain unchanged.
- **Persisted reviews:** strict >72-hour episodes create deduplicated review rows;
  owner readback hides recovered episodes, and permanent append-only dismissal
  prevents recurrence. Actual CLI exercises maintenance SQL with rollback preview
  by default and counts-only heartbeat. Prepared nightly workflow runs maintenance
  only; it does not execute enrichment and has not been deployed.
- **Review repairs:** failure-age reset and unsupported snapshot isolation were
  repaired previously. Latest review found schema-routing knobs could redirect
  counts/logs while writes stayed bound elsewhere. Removed those knobs and put
  queue writes, counts and heartbeat in one migration-bound RPC. READ COMMITTED
  remains mandatory. No real two-process proof is claimed (OQ-82).
- **Integration verified:** no-database suite 1061 passed/671 skipped, zero failures
  or errors (156.03s); disposable SQL 838 passed/1 skipped (190.25s); chain
  75 migrations/646 statements; layout43/43. Ledger unchanged14/15; F006 no-DB
  skip is covered by disposable SQL. Generic RULE04 remains pending. Final read-only
  review found no further material defect; rollback/error sanitization and real
  permission-denial checks pass. Evidence under `.local/evidence/capture-processing/`.
- **Still required:** actual initial/retry consumer
  remains open: preserve separate private-read/model-egress capabilities, durable
  shared budget/log reservations and atomic verified-result/status persistence.
  Stale receipts cannot count as success. Maintenance is not retry execution.

- **Outcome/requirements:** implement Joe-approved REQ-CAP-025..027 storage amendment
  (ADR-0144, OQ-83 resolved), retaining durable acknowledgement and RULE-02.
- **Acceptance:** persisted provider failure/success history linked to raw capture;
  current-status readback; no synthetic success for unprocessed captures; retries
  select pending work on each nightly run; repeated failures cannot reset pending
  age; >72-hour review reason enrichment_stalled; duplicate attempts are safe;
  raw captures stay byte-for-byte unchanged. Existing terminal ingestion states
  (e.g. file/location imports) must survive the projection.
- **Owned files:** root reserves migration0076; processing engine/runner/tests to be
  named before edits, plus SQL harness, active workflow and maintained docs. No
  implementation worker is active. Read ADR-0063/0115/0116 and current egress/budget
  contracts before integrating media calls; preserve capability separation.
- **Receipt unit verified locally:** migration0075 and actual Cloudflare Worker
  entrypoint implement authenticated raw-body retention, client UUIDv7 identity,
  atomic insert/conflict receipts and HTTP 202/200/400/503 mapping. Scoped ingress
  role avoids service-role read capability; effective PUBLIC grants were repaired.
  Exact commit-preference header is mandatory, so rollback/unproven storage never
  acknowledges. No enrichment call occurs inside the HTTP acknowledgement path.
- **Evidence at de97615 + recorded dirty sources:** 21 targeted SQL tests; eight
  Node HTTP cases executed by one pytest wrapper; full sanctioned writer **1061
  passed / 649 skipped**, zero failures/errors (180.37s); full disposable SQL **816
  passed / 1 skipped** (176.80s); chain **74 migrations / 609 statements**; layout
  **43/43**. Ledger unchanged14/15. Skips are not passes; generic RULE-04 stays
  pending, though disposable spine invariant tests passed. Exact reports, logs and
  source hashes: ignored `.local/evidence/capture-ingress/`.
- **Review repaired:** JSONB Unicode/numeric rejection escapes (two demonstrated
  failures), Worker ExecutionContext/transport mixup, excessive server credential,
  inherited PUBLIC application RPC execution, and pre-existing-role adoption.
  Independent reviewer confirms remaining live ACL/cutover evidence gaps.
- **NOT deployed/observed:** no production writes, Worker route, scoped JWT
  provisioning, device replay, post-commit readback or real concurrency proof.
  Legacy anonymous RPC remains until approved cutover; live anon/ingress private
  reads must be audited including old public tables. See Worker README. OQ-82 stays
  open. Do not treat prepared code as complete capture recovery or backend release.
- **Prior unit complete locally:** REQ-CAP-008 rejects missing/empty/non-string
  credentials before body access. Seven new cases failed against old code; focused
  capture suite **75/75**; sanctioned full suite **1060 passed / 628 skipped**, zero
  failures/errors (150.16 s); layout **43/43**. Ledger unchanged at 14/15. No hosting
  or deployment claim. Full results are saved under ignored `.local/evidence/capture-auth/`.
- **M0 closed:** merge `a8bcbf4` integrates the four nutrition files, preserving their
  reviewed working contents. Source hashes and original index/worktree patches are
  in ignored `.local/recovery/goal-start/`. No active child agent exists; nutrition
  worker branch last changed September 11 and has no tracked uncommitted changes.
  User explicitly authorized reconciliation. The old merge is concluded.
- **Integration evidence:** sanctioned writer `tools/update_features.py --strict`
  with production URL/socket/checks unset: **1047 passed / 628 skipped**, 0 failures
  or errors (143.22 s). Reuses today's **795 passed / 1 skipped** disposable suite
  and **73 migrations / 592 statements** chain: the four backend source hashes
  were unchanged; only the 17 separately passing watchdog tests were added.
  Disposable spine tests include invariant queries; generic RULE-04 stays pending.
- **Ledger:** sanctioned writer changed 9 failing entries to named-test passing;
  **14/15** narrow features now say passing. This is not scenario completion: its
  F-013 description says an end-to-end slice but its proof is an origin helper test.
  F-006's reported no-database regression is explained by its disposable-only test,
  which passed in the SQL suite. Do not hand-edit the ledger or use it as release proof.
- **Remaining nutrition findings (M3):** REQ-NUT-052 fractional Branded servings are
  not split; empty days currently render a zero interval and can imply a deficit;
  daily-total midpoint replaces asymmetric stored points; stored method and applied
  width must be reconciled. These were review findings, not repaired by the merge.
- **External hold revalidated:** production connection rejects the configured
  credential with **SQLSTATE 28P01** on September 22, including outside the sandbox.
  No production queries/writes completed. Joe was asked to refresh the environment
  secret (never chat). Continue independent code work; no repeated auth probes
  until credentials change. Deployment authorization and reserved definitions remain
  required; OQ-82 is not implicitly resolved.
  **Joe's steering:** remind him later. Reminder trigger is the next production
  verification/deployment boundary; do not repeat the credential request during
  independent local work or imply that a clock-based notification was scheduled.
- **Monitor:** installed 900-second launchd schedule, initial run observed, header
  now `running`; it does not launch agents or prove release. Goal remains active.

# Quality review — 2026-09-22 (no backend implementation integrated)

Joe requested multiple independent quality checklists because he is directing
implementation without routine code review. The maintained review lenses are now
in EXECUTION_PLAN, with findings and limits in COMPLETION_AUDIT's 2026-09-22 entry.
Read that entry before relying on the older status below.

Fresh evidence at `6fe21e6` plus pre-existing nutrition work: **1030 passed / 628
skipped** without production credentials; **795 passed / 1 skipped** on disposable
PostgreSQL; layout **43/43**; migration chain **73 migrations / 592 statements**.
Merged evidence remains **673 of 685 named-test requirements**, not backend
completion. Engine reachability is now **10 scheduled / 13 CLI / 33 tests-only**:
the uncommitted `nutrition_day.py` connects `nutrition_display`.

Fresh GitHub reads confirm `v2-day1` is still default, lacks freshness/tests YAML,
and the latest tests run is still September 3. Scheduled analysis/extract/keepalive
runs succeeded September 22; input freshness was not queried. No production DB
read/write or deployment occurred.

**Open capture findings for its implementation owner:** absent request/configured
tokens compare equal and return 202 (REQ-CAP-008); the handler ignores database
insert outcomes needed for racing duplicate suppression (REQ-CAP-016/017); enqueue
exceptions escape after a successful insert callback. These were pure in-memory
probes, not a hosted endpoint test. Require fail-closed configuration, durable
acknowledgement, conflict-result handling and recovery in the actual serving path.

Preserve the four pre-existing changed nutrition/test-harness files. This review
changed documentation only and did not stage, repair or integrate their work.
M1 remains first when actionable; external holds do not block independent backend
work. No backend release is approved by this audit.

# Checkpoint — 2026-09-11 (integration boundary, `2e9f547`)

## LATER: the alias bridge is closed (0074)

The nutrition worker delivered the `food_aliases` read/write path at `6897583`. The resolver
writes no bridge row, verified across the tree rather than taken on trust: the only surviving
mentions of `raw->>'alias_of'` are 0071's own backfill reading it, a docstring recording the
history, and a test asserting it is gone.

**0074 completes the three-step sequence** 0071 opened — create and backfill, move the read
path, then delete and forbid. **The CHECK is the part that closes it**; a delete alone lets the
next resolution recreate a bridge row, so the tree would read as clean and drift straight back.

Their ordering argument deserves recording because it is the kind of defect that survives a
green suite: an alias points at exactly one `food_id`, so consulting REQ-NUT-001 step (1)
*first* would let an alias learned from Open Food Facts outrank a correction Joe made later for
the same food — answering with the crowd figure, never looking at Joe's, silently.
`lookup_cached` unions both candidate sets and ranks by `SOURCE_PRECEDENCE` instead. **Every
other test in that file passes under the sequential version.**

Also adopted: **0071 is the first nutrition migration to REVOKE on `anon`/`authenticated`**, and
a bare PostgreSQL 17 cluster has neither. Six fixtures died on `role "anon" does not exist` for
reasons unrelated to what they tested. Any fixture applying 0071+ needs the three idempotent
`CREATE ROLE` lines — nothing in the migration text predicts it, since 0050 referenced no role.

At `1f0a9cc`: deterministic **1030 passed / 612 skipped / 0 failures**; disposable SQL **779
passed, 1 skipped**; **673 of 685**; layout 43/43; chain clean from empty, **73 migrations / 592
statements**; nutrition acceptance 7 of 7. **Deployment frontier is now 0055–0074.**

## LATE ADDITION: five disposable servers were running on the wrong clock

Reported by the nutrition worker, verified here, and it was **five files, not the two they
found**. Only `tools/test_local_sql.py` passed `-c timezone=UTC`. Measured rather than argued:
a server left on the machine's zone returns **2026-09-10** for
`'2026-09-11 02:00:00+00'::timestamptz::date`, and 2026-09-11 with the flag. Production runs
UTC, so every server-side date cast under those harnesses was a day out.

**It fails open**, which is why it is now a lint and not a convention: none of the harnesses'
own cases exposed it, because they use explicit `+00` timestamps. The harness is wrong and
every test inside it passes, until one does date arithmetic.
`test_every_disposable_server_is_pinned_to_UTC` found `verify_migration_chain.py` — which
nobody had suspected — and was verified against a planted sixth harness.

Re-verified after the fix: deterministic **1030 passed / 605 skipped / 0 failures**; disposable
SQL **772 passed, 1 skipped**; **673 of 685**; layout 43/43; chain clean at 72 migrations.
Acceptance tools under the corrected servers: reconstruction **7 of 7**, nutrition **7 of 7**,
capture **10 of 10**.

**OQ-82 narrows by one.** `tools/nutrition_acceptance.py` rolls back every case and commits
nothing, so it is not in the class the capture worker disclosed. **Only
`tools/capture_acceptance.py` is**, and only it is excluded from counting toward requirements.


All three workers have delivered and are integrated. **Five statuses stay apart: implemented /
tested / integrated / deployed / observed. Nothing in this session reached the last two.**

## VERIFIED ON THE COMBINED TREE at `5455c69`

Every figure below was regenerated here, not inherited from a worker branch, with
`SUPABASE_DB_URL` removed from the environment (OQ-80 — a bare `pytest` in this repo runs
against production).

| check | result |
|---|---|
| **requirements with a named test that ran and passed** | **673 of 685** (was 635 at the session checkpoint) |
| deterministic suite | **1029 passed, 605 skipped, 0 failures, 0 errors** |
| disposable SQL suite | **772 passed, 1 skipped** (was 527) |
| layout | 43 / 43 |
| migration chain | clean from empty, **72 migrations / 589 statements** |
| reachability | 245 scheduled, 54 cli, 361 tests-only, 25 none |
| engines with no caller | **34 of 56** (was 37 of 55) |

**673 is both higher than the old 635 and reproducible without production**, which the old 666
was not. The remaining 12 are all skips — no failures, no errors, no vacuous tests, nothing
uncollected.

## THE FINDING THAT MATTERS MOST: THE ALARM HAS NEVER RUNG

Found by the capture worker, verified independently here against GitHub before being accepted.

`.github/workflows/freshness.yml` is the one mechanism built to stop a repeat of 2026-07-28,
where every scheduled job wrote `status='ok'` for 43 days while its inputs were dead.
**It has never fired.** GitHub delivers `schedule` events only from the default branch; the
default branch is `v2-day1`; the file has never reached it.

It is worse than that, and this was measured rather than assumed:

- **`tests.yml` is registered but absent from the default branch.** Its cron has never fired
  either. Last run: **2026-09-03, `event=push`, branch `main`** — eight days ago.
- **The nightly `analysis.yml` that IS firing is `v2-day1`'s copy**, which runs `run_analysis`,
  `run_resolve` and `run_scan` only — not `run_confirm`, `run_recommend`, `reconstruct_run` or
  the clarification dispatcher.
- So the checkpoint's "223 scheduled" reachability figure — now 245 — is computed from workflow
  files in the working tree, **four of which are not on the default branch at all.**
  Reachability was never claimed to mean deployed; the gap is simply larger than it looks.

The thing built to detect silent failure failed silently. Same class of error, one level up.

## INTEGRATED THIS BOUNDARY

| from | what landed |
|---|---|
| **main** | R2 workout-session reconstruction (0070); R4 service usage (0073); `food_aliases`/`portion_aliases` (0071); rate-limit persistence (0072); the clarification dispatcher wired into the nightly |
| **Worker 1** evidence | eight test modules that were applying the migration chain **inside production** on every CI run — the real cause of OQ-78's 38 timeouts; the guard is now structural and a lint stops a ninth; JUnit artifacts and `tools/evidence_manifest.py` |
| **Worker 2** nutrition | the two USDA FoodData Central legs (previously `UnconfiguredLeg`, a class whose only behaviour is to raise, while being the 1st and 2nd reference sources); REQ-NUT-017 `accept_correction`, without which Joe's review list could never be emptied |
| **Worker 3** capture | the drop-folder acceptance harness; freshness workflow; `ops/clarification_prompts.py`; `--ops`/repeatable `--file` on `tools/import_drop.py` |

**Three ADR-number collisions.** 0138 (nutrition → 0139), 0140 (capture → 0141), plus ADR-0091 →
0094 last session. A worktree cannot reserve a number; `docs/WORKER_OWNERSHIP.md` now records
ownership and every collision. `WORKER_BRIEF.md` is no longer on the integration branch — all
three worktrees tracked it at one path, so every merge collided add/add.

## R2 AND R4, THE TWO PRODUCT SCENARIOS CLOSED

**R2 — the training history was in the file all along.** `apple_health.py` counted every
`<Workout>` element and discarded it. 32 sessions, 25 of them strength, 2023-02-26 to
2026-06-30. The previous checkpoint called this *"pending observation, not missing
implementation"*; it was the opposite. **A counter recording a discard is not a deferral.**
Against the real export on a disposable server: 93 atoms, **32 sessions → 32 events, 1:1**,
all DESCRIPTIVE, 0 strength set atoms created, 0 `did_not_occur`.

  *The 32→30 question, since it was asked:* a first version grouped by subject day and produced
  30 events. Neither loss nor deduplication — 2023-04-05 carries a 120.31-minute lift at 14:06
  and a 7.83-minute run at 21:10, and 2023-09-23 carries a 39.80-minute lift and a 27.72-minute
  run. Every atom was stored either way, but an event count was silently two short of a session
  count. Now one event per session, each timed by its own span and citing its own atom.

**R4 — an outage is not proof of nonuse.** `usage_status.from_evidence` returned `unused`
whenever evidence was older than the threshold, with no concept of whether anything had been
watching. The Watch stopped 2026-08-21 and the bank CSV died 2026-05-13, so the largest silences
here are this system's own instruments failing. `usage_observation_window` is now **required
evidence** the gatherer emits only when something was demonstrably watching, so there is no
branch from a dead sensor to a conclusion — the refusal is structural, not a check someone
remembered. `unused` is reported and never stored: nonuse is the absence of a class of events,
not an event.

INTENT_COVERAGE: **nine STORED, one PARTIAL, two OPEN** (R1, R11).

## DECISIONS THAT ARE GENUINELY JOE'S

Everything else below the line is engineering work and is not waiting on him.

| # | decision | recommendation | consequence of not deciding |
|---|---|---|---|
| **OQ-82** | RULE-01's fixture exception says "roll back the whole transaction". `tools/capture_acceptance.py` COMMITS inside a disposable server it creates and destroys. **A compliant version cannot exist**: case 5 is two concurrent processes, and two processes cannot share an uncommitted transaction, so an overlap test inside one would pass against a completely broken implementation | **amend**, exact text in OQ-82 | the two-process overlap and file-settling behaviour have **no executable evidence anywhere**. Until ruled, that harness counts toward no requirement |
| **workflow publication** | `freshness.yml` and `tests.yml` must reach the default branch to ever fire. **Switching the default to `main` would make it worse** — `main` is at migration 0048 against this branch's 0073, so `tests.yml` would fire against B10-era code | push this branch to `v2-day1` **after** the migrations are applied, not before | the freshness alarm and the nightly suite never run |
| **migrations 0055–0073** | nineteen, plus the transaction backfill and resolver/link/category population | apply, then publish the workflows | everything built since the September import stays unreachable in production |
| **launchd activation** | `ops/capture_schedule.py --emit-launchd` installs nothing; `RunAtLoad` false. The first firing is a production write (ADR-0094) | Joe runs the documented steps in `docs/CAPTURE_ACTIVATION.md` §3 | the local import never runs unattended |
| **OQ-81** | one strength record is 0.175 min / 0.54 Cal — started, paused 11 seconds in, closed 10.5 hours later | no threshold; show duration beside any count | nothing blocked; frequency counts include it |
| still open | OQ-32, OQ-55, OQ-57, OQ-59, OQ-60, OQ-61, OQ-62, OQ-67, OQ-74, OQ-75, OQ-76; the USDA `api.data.gov` key; Gmail OAuth; `role='lever'` on one metric; the Log Workout shortcut; the review sheet (40 ticks, 157 names) | | |

**OQ-78 can close** on its own recommendation (a): the 38 timeouts were eight test modules
building schema inside production, now structurally prevented.

## ENGINEERING WORK REMAINING — NOT BLOCKED, NOT WAITING ON JOE

- **25 of the 28 required runtime capabilities still have no caller.** Three were connected this
  session (`recurrence`, `usage_status`, `vision_and_prompts`) — each because a product scenario
  needed it, never to move the statistic. The largest cluster is capture's own serving path:
  `ingest_endpoint` (a complete dependency-injected REQ-CAP-003..018 endpoint with no HTTP
  host), `extraction`, `capture_budget`, `capture_resilience`. **Assigned to Worker 3.**
- **`nutrition_display.py` still has no caller** — priority 1 of Worker 2's brief, unstarted; its
  session was scoped to the USDA path. B12 §D.4/§E.3/§G.1 remain tested and unreachable.
  **Assigned to Worker 2.**
- `remember_alias` onto the new `food_aliases` table, then a migration removing the bridge rows
  and a CHECK so `foods_cache` can never carry `alias_of` again. **Worker 2**, requested.
- R1 (purchase vs consumption) and R11 (discovery across history) — **main**.
- `tools/import_drop.py` cannot be run against a disposable server: `lib/db.connect()` is
  TLS-to-host only and the local harness disables TCP, so the real import CLI is exercisable
  only against production. **Worker 1.**
- **RULE-29 finding:** `tools/engines/resolve_merchants.py:7` carries a real merchant name from
  Joe's transactions in a docstring, in a repo intended to be public. Pre-existing.

# Superseded checkpoint — 2026-09-11 (R2)

Session 21 continues. Starting revision `48745d9`, tree clean. Four worktrees from prior
sessions were inspected and **fully harvested** — every file they carry is in HEAD, and the
capture worker's ADR-0091 is present as the renumbered `docs/adr/0094-scheduled-local-import.md`.
Nothing unintegrated is at risk; none was discarded.

Three new worktrees exist at `48745d9`:
`work/release-evidence`, `work/nutrition-finish`, `work/capture-finish`.

## FIRST TASK COMPLETE: the 37 unreachable engines are triaged

Measured with `tools/evidence_report.module_reach()` at `48745d9`, with the reverse import
graph supplying each module's non-test callers. **55 engine modules: 9 scheduled, 9 cli,
37 tests-only.** The 37 were classified by reading each module's public API and its brief,
not by counting lines.

**The headline is worse than "37 modules have no entry point": 28 of the 37 are required
runtime capabilities with no caller.** Only 9 are legitimately callerless.

| Class | n | Modules |
|---|---|---|
| **(A) Required runtime capability, not connected** | **28** | ingest_endpoint, extraction, capture_budget, capture_resilience, vision_and_prompts, compliance, email_ingest, dedupe, recurrence, usage_status, money_position, cooccurrence, category_cascade, finance_insights, habit_rhythm, nutrition_display, strength, sleep, workout_contract, chains, regimes, trials, forecast_ledger, multiplicity, preregistration, interrupted_series, render_pipeline, bayes_model |
| (B) Supporting library, caller is another engine | 2 | calibration (←forecast_ledger), tier_contract (←forecast_ledger, interrupted_series, multiplicity) |
| (C) Validation-only contract — the test suite IS the enforcement | 6 | finance_never, finance_presentation, generator_gate, narration, narration_contract, ontology_contract |
| (D) Superseded / duplicate | 1 | bayes_numpyro |

Notes that change what the table means:

- **(B) is real but inherited.** `calibration` and `tier_contract` are correctly libraries; they
  have no entry point because *their consumers* have none either. Connecting the consumer
  connects them. They are not separate work.
- **(C) is not a gap and will not be "fixed".** `finance_never.scan_repository` greps the source
  tree for banned language; `narration` lints the 13 live templates. A linter whose job is to
  fail CI is connected when its test runs in CI. Wiring these to a runtime would be connecting a
  module to improve a statistic, which is explicitly not the objective.
- **(D)** `bayes_numpyro` is the same model as `bayes_model` in NumPyro. `jaxlib` publishes no
  macOS x86_64 wheel (ADR-0103 amendment), so it cannot run on this machine. It is a duplicate
  held for CI, and its disposition is **OQ-74/OQ-75**, not engineering work.
- **`category_cascade` is NOT a duplicate of the connected `categorise`.** `categorise` (B14.3)
  derives merchant category rules from Joe's existing classification; `category_cascade`
  (B17 §B.3/B.4) is the rules→kNN→LLM cascade with a correction loop. Different capability.
- Several (A) modules are **mixed**: `workout_contract`, `render_pipeline`, `compliance` and
  `ontology_contract` each carry both a contract and a real runtime path. They are classified by
  the unconnected runtime half, because that is what determines remaining work.

The 28 are **not** 28 independent tasks. They cluster onto the open INTENT_COVERAGE scenarios,
which is how they will be connected — driven by a product scenario, never by reachability:

| Scenario | Engines it connects |
|---|---|
| R1 purchase vs consumption | cooccurrence, money_position, dedupe |
| R2 workout session | workout_contract, strength |
| R4 recurring service + outage | recurrence, usage_status, money_position |
| R8 useful clarification | vision_and_prompts, compliance |
| R11 discovery across history | preregistration, multiplicity, chains, regimes, trials, forecast_ledger |

## R2 IS MISSING IMPLEMENTATION, NOT PENDING OBSERVATION — THE PREVIOUS CHECKPOINT WAS WRONG

The 2026-09-10 checkpoint recorded R2 as *"Pending observation, not missing implementation."*
That claim was inspected and **it does not hold.** Corrected here rather than left standing.

Measured evidence:

- `_legacy_snapshot/data_capability_inventory_2026-09-09.json` `health_workout_types`:
  **32 workout sessions exist in the Health export** — 25 `TraditionalStrengthTraining`,
  4 `Running`, 2 `Walking`, 1 `Cycling`. This is ADR-0087's "25 sessions in four years".
- `tools/importers/apple_health.py:201` — a `<Workout>` element hits
  `c.bump("workout_deferred_to_B18")` and **is never yielded**. The importer counts them and
  drops them on the floor.
- Production, queried read-only at this revision: **zero** workout-session atoms.
  `core.metric_registry` carries `strength_load_lb`, `strength_reps`, `strength_rpe` and
  **no session key**. `core.atoms` kinds are activity_sample 18,845 / vital_sample 11,171 /
  heart_rate_variability 1,303 / environment_sample 1,294 / sleep 742 / self_report 3 / note 2.
- The two alternative workout sources are both **EMPTY**: `csv__workouts`
  ("empty file / parse error") and `supabase:public.workouts` (0 rows).
- `exercise_minutes` has **407 atoms** over 2026-07-01..08-21. That is Apple's exercise ring,
  which **corroborates** a session and is not a record of one.

So R2 splits into two halves that the old status merged into one wrong word:

| Half | Status | Why |
|---|---|---|
| A session **happened**, its type, start, end, duration | **Missing implementation.** 32 records available now | the importer discards them |
| Load, reps, volume, e1RM | **Genuinely unobserved** | no set has ever been logged; the Log Workout shortcut is not installed |

**Missing sets prohibit inventing load and reps. They do not prevent reconstructing that a
session occurred.**

## UNIT CLOSED: R2 IS STORED (`f65d863`, ADR-0138, migration 0070)

| status | evidence |
|---|---|
| **implemented** | `tools/importers/apple_health.py` yields workout atoms instead of discarding them; `migrations/0070` registers three `workout_*` measures and the `training_session` method; `tools/reconstruct_run.py` gained its gatherer and explicit per-method dispatch |
| **test evidence** | **19 tests** in `tests/test_workout_session_r2.py`. Deterministic **947 passed / 549 skipped / 0 errors** (was 937/540). Local SQL **546 passed** (was 527). Layout **43/43**. Chain clean from empty, **69 migrations / 575 statements** |
| **falsification** | every one of the 19 verified to FAIL against the unfixed tree — the importer tests against the old parse loop, all nine SQL tests against 0070 with the method registration stripped (RULE-13 refuses an unregistered method) |
| **real data** | against the actual export on a disposable PostgreSQL 17: 93 workout atoms through the importer's own `insert_atoms`, **30 training-session events from 32 sessions**, 2023-02-22..2026-08-21, **all DESCRIPTIVE**, **0** strength set atoms created, **0** `did_not_occur` rows. Rolled back |
| **integrated** | on `session-21-recovery-and-ask` |
| **deployed** | **NO.** 0070 extends the unapplied stack to **0055–0070** |
| **observed** | **NO.** Nothing has reached production |

Three things this unit is deliberately NOT claiming:

- **`tools/engines/strength.py` is still idle and still has no caller.** e1RM, volume and ACWR
  need per-set records; this produces none. Connecting it is not part of R2 and was not done.
- **Every session is DESCRIPTIVE and that is the correct answer**, not a defect to tune away. The
  same day's exercise minutes come out of the same export and share its `origin_group`, so
  REQ-REC-008 counts them once. A gym `place_visit` is a different capture path and does promote
  — tested — and this system has never captured one.
- **The reachability statistic barely moved**, because connecting engines was never the point.
  R2 connected no engine from the callerless 28; it added a capture path and a method.

### Two findings from this unit that outlive it

- **A counter recording a discard is not a deferral.** `workout_deferred_to_B18` reported a
  number nobody read while the code lost data permanently at import time. Worth checking the
  other `Counters.bump` reasons for the same shape.
- **`tools/import_drop.py` cannot be run against a disposable server.** `lib/db.connect()` builds
  a TLS connection to a host and has no unix-socket path, while `tools/test_local_sql.py`
  deliberately disables TCP. So the real import CLI can only be exercised against production.
  Verification here had to call `insert_atoms` directly, which is the same writer but not the
  same entry point. This is a genuine gap in the acceptance story and it belongs to Worker 1.

## NEXT UNIT: R4 — recurring service and usage with a logging outage

Chosen because its engines are already written and its defect is already visible.
`tools/engines/usage_status.py` and `recurrence.py` are complete, correct and callerless, and
`usage_status.from_evidence` has the exact bug R4 exists to prevent: it returns `unused` whenever
the newest evidence is older than `unused_after_days`, **with no concept of a logging outage.**
Given that the Watch stopped in five stages ending 2026-08-21 and the bank CSV export died
2026-05-13, that path will call things unused on the strength of a dead logger. R4's requirement
is precisely *"an outage is not proof of nonuse"*.

# Superseded checkpoint — 2026-09-10

## THE "685 OF 685" CLAIM WAS NOT SUPPORTED. IT IS WITHDRAWN.

An independent audit found the previous line — *"EVERY REQUIREMENT IS PROVEN: 685 of 685"* —
unsupported. I verified all four of its findings. Every one was correct, and one was worse than
reported.

| audit finding | verdict | what was actually true |
|---|---|---|
| `audit_requirements.py` counts IDs in test names without reading results | **CONFIRMED** | The file contains no `subprocess`, `pytest`, `passed`, `exit_code` or `run(`. It greps requirement IDs out of test function names. A test that fails, errors or skips counts exactly the same as one that passes. **A test that has never been executed anywhere counts too.** |
| REQ-REC-016's test checks a dictionary of labels | **CONFIRMED** | It built `{family: "passed"}` for seven families and asserted the dict had seven keys. It executed no reconstruction and would have passed with the engine deleted. |
| New helpers have no non-test callers | **CONFIRMED, AND WORSE** | Not two helpers — at the time of the audit, **30 of 33 engine modules had no non-test caller.** Only `tier_contract`, `finance_never` and `bayes_model` were wired to anything. |
| NumPyro tests can skip and CI does not install their dependencies | **CONFIRMED** | `tests.yml` installed neither `numpyro` nor `dateparser`. The NumPyro tests skipped everywhere and were counted as proving REQ-INF-520. |

## THE MEASURED NUMBER: 635 of 685 (92.7%)

From `tools/evidence_report.py`, which reads pytest **results** and counts a skip as unproven.
Regenerated at this revision from two runs: the deterministic suite (937 passed, 540 skipped,
**0 errors**) and the disposable-server SQL suite (527 passed). The evidence worker measured 636
at the previous revision with two independent implementations agreeing; the difference is churn
in which tests carry which IDs, not a regression.

- **The 50-requirement shortfall is entirely skips. Zero failures, zero errors.** They are the
  tests that need the live database — `REQ-LOC-*`, `REQ-ONT-001/002`, the spine invariants, the
  tier gates — plus `REQ-INF-520`, which needs NumPyro and now installs in CI.
- **313 fixture ERRORS became 0.** With neither the disposable socket nor `SUPABASE_DB_URL`,
  `tests/_sql_fixture.py` fell through to a connection attempt that raised, so pytest reported
  313 fixture errors. An error is indistinguishable from a broken test — which is exactly what
  made the audit's "38 errors against production" so hard to read. It now skips with a reason.
- A **caveat that belongs with the number**: a third run against the live database finished
  later with 38 errors (all `57014 canceling statement due to statement timeout`) and 1 failure.
  Merging it gives **666 / 685**. It started against a dirty tree and its errors are
  environmental. **635 is the reproducible figure at this revision; 666 is the better-covered one.** Neither is
  quoted without this sentence.
- **Nobody has evidence the live-database suite passes.** CI's `pytest` job takes that path and
  whether it survives depends on pooler latency.

**Two-thirds of "proven" still rests on code nothing outside `tests/` calls.** Of the 635: **223
scheduled** (up from 168 when the audit ran), 21 cli, **423 tests-only**, 18 unreachable. The
improvement came from wiring `reconstruct_run.py` into the nightly `analysis` workflow — one
scheduled step pulls its whole import closure into the reachable set, which is a fair measure of
how little it takes to move this number and how little "reachable" guarantees on its own.

That remains the real shape of the gap between "tested" and "works", and it is larger than the
coverage percentage suggests.

**Restoring 100% is not the objective** — a truthful number is, whatever it turns out to be.

### What "proven" has to mean from now on

1. A named test containing the requirement ID **ran** and **passed** — in a recorded run, not in
   principle.
2. A **skip is not a pass.** `tests/conftest.py` now distinguishes a skip caused by a missing
   *library* (a hole in the evidence — it fails in CI) from one caused by absent *data* (a true
   statement about the world; no package installs a row).
3. The test **body demonstrates the requirement.** Naming its ID is not evidence.

## WHAT WAS FIXED IN RESPONSE (measured, this session)

| check | result |
|---|---|
| reconstruction end to end | **18 tests**, source evidence → registered method → stored event → Ask response → evidence inspection → human correction → historical replay |
| REQ-REC-016 acceptance | **7 of 7 cases executed and passed** via `python3 tools/reconstruction_acceptance.py` — a runnable command, not an assertion |
| local SQL suite | **527 pass** (was 428 at session start) |
| deterministic suite | **937 pass, 540 skip, 0 errors** (was 937 pass, 227 skip, **313 errors**) |
| pending stack vs production | **20 of 20**, one transaction, rolled back — including 34 non-wear episodes reconstructed from real atoms, all DESCRIPTIVE, findable through `search_record`, every hit labelled inferred |
| production DDL in the CI pytest job | **closed** — `tests/test_status_sql.py` ran `CREATE SCHEMA` against production behind a rollback; the workflow comment claimed that job skipped it and nothing made that true |
| migration chain | clean from empty, **68 files / 573 statements** |
| layout | 43 / 43 |
| engines with an entry point | **18 of 55** (9 scheduled, 9 cli) — measured by `evidence_report.py`, where an entry point is a script named in a workflow or `RUN_TONIGHT.sh`, not merely a module with `__main__` |
| CI dependency holes | closed — `dateparser`, `jax`/`jaxlib` 0.4.30, `numpyro` installed; `PERSONAL_OS_REQUIRE_DEPS=1` turns a missing-library skip into a failure |

**37 of 55 engine modules still have no entry point.** That is the honest headline for finding
(c) — the brief said 30 of 33; measured across every engine it was 42 of 55, and wiring the
reconstruction runner into the nightly moved it to 37. It remains the largest gap between
"tested" and "works". Some are contract modules that exist to be asserted against; others are
real capabilities nothing calls. They have not been individually triaged.

**This is a statement about tests, not about production.** Four statuses stay apart:
implemented / tested / **deployed** / **observed**. Almost none of this is deployed.

## THE ONE THING BLOCKING DEPLOYMENT

Migrations **0055–0069** — fifteen of them — plus the transaction backfill and the
resolver/link/category population. **See OQ-77.** The frontier was reconciled against production
on 2026-09-10 by inspecting the objects each migration creates, since there is no ledger table:
it was NOT where this checkpoint previously said. 0055 is unapplied too, so
`public.get_reconstruction` does not exist in production and nothing can inspect a
reconstruction's evidence there.

`tools/verify_pending_stack.py` applies all fifteen in ONE transaction against the real
database, exercises the stack and rolls back: **STACK VERIFIED — 20 of 20**. Nothing has reached
production since the September import. **A rolled-back test is not a deployment.**

Everything else outstanding is a ruling or a credential: OQ-32, OQ-60, OQ-74, OQ-76,
`role='lever'` on at least one metric, the USDA api.data.gov key, Gmail OAuth, and installing
the Log Workout shortcut.

**OQ-75 is resolved** — by fact rather than by ruling. See ADR-0103's second amendment.

# Superseded checkpoint — 2026-09-09 (late)

Authoritative status. Reconciled against Git at `c3f3814`. Four statuses kept apart:
**implemented** (code exists) / **tested** (a named test with the requirement ID passes) /
**deployed** (applied to production) / **observed** (verified working against real data in
production). Passing tests and deployed tables are neither of the last two.

## OBSERVED IN PRODUCTION

- **Apple Health import** — 33,355 atoms, 25 metric keys, 2026-07-01..09-09, one capture row.
  `check_invariants --core core`: ALL PASS. Idempotence proven (a re-run preloaded 33,355
  dedupe keys and skipped every one).
- **Freshness detection** — 9 fresh / 17 stale / 11 never seen / 6 unmonitored. The capture
  loss is dated: the Watch stopped in five stages ending 2026-08-21; the iPhone never did.
- **Ask, refusing correctly** — "I do not track that" for an unknown metric, "I cannot compute
  that." for an uncomputable question shape.
- **Open Food Facts nutrition** — a real lookup through `lib/egress`: Nutella, 539 kcal/100g,
  logged to `ops.egress_log` (290 B out, 2,530 B in). The allowlist admits the host; REQ-NUT-010's
  User-Agent contract is enforced; the call was rolled back.

## ADVERSARIAL REVIEW — 19 findings, all repaired

The six pending migrations were reviewed adversarially before application. **Nineteen defects**,
most reproduced on a disposable server. None was live on 2026-09-10's data; every one would
have fired silently on the next import, the next check-in, or the first replay. The ten worst:

| what | consequence had it shipped |
|---|---|
| a composed metric served by two lanes | coverage could exceed 1.0 and pass the INSUFFICIENT floor on a doubled denominator; the median mixed a self-report with a device derivation (INV-5) |
| an unbounded interval NULLed a night | the NULL row was still counted as a day WITH data |
| device precedence skipped for the composition | two devices' sleep unioned and credited to one |
| `p_known_at` ignored by all 19 metric queries | the "true replay" claim held only for `spend` |
| `atoms_current` unbounded in `spend` | a corrected charge vanished from replay entirely |
| the RULE-10 precedence trigger never fired | Joe's correction and a fuzzy guess both "current" |
| `only_a_rule_or_a_human_is_certain` | admitted what its own comment forbade; could not fail |
| `distinct_prefixes` | stored the constraint's floor, not the measurement |
| baselines ignored the knowledge clock | a replay placed a value in a band built afterwards |
| the test helper was a dict comprehension | the first defect could not have failed any test |

Every regression test was verified to FAIL against the unfixed migration. Three attempts at
finding 13 each broke a test before disclosure beat redefinition.

## THREE REVIEW ROUNDS — 42 findings

| round | findings | caused by the previous round's repairs |
|---|---|---|
| first | 19 | — |
| second | 12 | **10** |
| third | 11 | 2 confirmed, plus 1 that was doubly dead |

**All three ran against a green suite.** Passing was never the signal.

The third round's worst finding was **pre-existing and untouched by both earlier rounds, which
had each edited the very loop it lived in**: the resolver hit a NOT NULL and a CHECK violation
on any ATM, transfer or fee descriptor, with the commit after the loop and no exception
handling — so one such descriptor rolled back every pattern, token and alias in the run. Joe's
data reaches that path routinely.

Three defects sat underneath a test written to catch them, because those tests **read the
source file as text and grepped it for string literals**:

- Two grepped `resolve_merchants.py`. A crash on ordinary bank input passed them for a round.
  Both also took a live-schema fixture and never used it, so they *skipped* in CI while looking
  like database tests.
- One grepped `build_catalogue.py`. The code it described was a no-op for **100%** of the rows
  it was written to protect, and called `json.dumps` in a module that does not import `json` —
  it would have raised `NameError` had it ever run. Two defects hiding each other.
- 0061 was applied by **no pytest at all**; its tests read the migration as text.

Those are now tests that run the code, each verified to fail against the old version. See
ADR-0101.

**What this round changed structurally** (not just repaired):

- `entity_aliases.canonical` is nullable for REQ-FIN-051 non-merchants only, paired with a
  required `non_merchant_kind`. OQ-72 is the consequence Joe must settle.
- An exclusion may not reach past its own device lane; `analysis.f_composed_exclusions` records
  the nights that are dropped, so an excluded night differs from a night with no data.
- `strength.py` reads `config.derivation_catalogue.parameters`, so RULE-13 is true rather than
  asserted.
- Joe's merchant confirmations now reach the resolver. They previously went into a table
  nothing queried — the review sheet with 157 names terminated in a write nobody read.

## AWAITING ONE AUTHORIZATION (all verified against production in rolled-back transactions)

| # | What | Proven by |
|---|---|---|
| 0056 | the panel reads `core.atoms` | "Your Steps was typically a four-figure daily step count over the last 30 days (30 of 30 days)" |
| 0057 | entities, merchant patterns, aliases | 93 merchant entities from 440 descriptors |
| 0058 | `ask` separates its two clocks | the same question INSUFFICIENT at one as_of, a four-figure total usd at another |
| 0059 | `spend` answers about a merchant, and discloses its capture sources | Hannaford a four-figure total across dozens of charges via `resolved_merchant` |
| 0060 | domain readiness says WHY a domain is empty | 2 resolved / 4 renamed / 4 unbuilt / 3 uncaptured / 1 no hero |
| 0061 | the strength measures and their specification | the catalogue and the engine cannot drift (tested) |
| — | transaction backfill | 1,052 legacy rows → 1,052 atoms, none dropped, none merged |
| — | resolver / link / category population | 616 `paid_to` links, 88 category rules |

The migration chain applies clean from empty at **60 files, 528 statements**.

**Verified 2026-09-10 after the third round:** 430 local SQL tests pass under both
America/New_York and UTC; layout 43/43; chain clean from empty.

## IMPLEMENTED AND TESTED, NOT DEPLOYED

- **B14 complete** — normalisation, the five-step cascade, entities, `paid_to` links, category
  rules. 59% of real spend resolves; 23% is ATM/transfer/fee and correctly not a merchant.
- **B14R steps 1-5** — source inventory, derivation catalogue, inferred-event schema, the
  deterministic evaluator, the lineage interface. The method registry is EMPTY, so the engine
  can conclude nothing; that is by design and it is not coverage.
- **B13 set extractor** — `tools/extract_workouts.py`. Runs clean and writes nothing, because
  no set has ever been logged.
- **The merchant review sheet** — `~/merchant_review.tsv`, outside the repo. 40 lines carry a
  plausible suggestion; 157 need a name.
- **B18 strength** — e1RM as an interval across the registered formulas, volume, ACWR on rates.
  Correct and idle: no set has ever been logged.
- **B20 narration** — the tier vocabulary linter. Zero breaches and zero moralising terms
  across the 13 live templates, after two false positives were fixed (the month of May; the
  preposition "on").
- **B21 sleep** — duration, window and midpoint as three distinct facts; `specs/11-sleep`
  authored (REQ-SLP-001..013 built and tested, 020..023 open).
- **Source continuity** — `tools/check_source_continuity.py`, which detects an instrument
  change masquerading as a change in Joe's life. It found the finance handover.

## WORKER OWNERSHIP AND INTEGRATION

Both worker branches are **integrated** at `bc61844`; neither touched a shared file.

| Worker | Branch | Owns | Delivered | Integrated |
|---|---|---|---|---|
| nutrition | `work/nutrition-parser` | `tools/engines/nutrition_off.py` + its tests | OFF parser, four failure types | `94c098c` |
| capture | `work/capture-scheduling` | `ops/capture_schedule.py`, new workflows + tests | launchd import schedule | `e8c149f` |

Integration notes: the capture worker's ADR-0091 was **renumbered 0094** (0091 was taken by the
two-clocks decision while it was in flight — parallel worktrees cannot reserve a number).
B12: the **cascade is now written and tested** (`tools/engines/nutrition_cascade.py`, 16 tests,
ADR-0106). `SOURCE_PRECEDENCE` had been declared as a constant and never used — `resolve_item`
did one cache lookup, so the ordering existed only as documentation. Each source is a callable
the caller supplies, so the ordering, the refusals and the brand rules are tested with **no API
key and no socket**. The USDA *legs* (the HTTP clients) remain blocked on Joe's api.data.gov
key.
The capture schedule is built but **not installed**, so it is not yet running.

I remain sole integration owner: entity resolution, reconstruction, migrations, shared
database/API contracts, `tools/import_drop.py`, shared fixtures, requirements, this checkpoint,
and deployment.

## ACTIVE UNIT

**B19 cross-lens discovery.** §G.4 (chains) is now **implemented and tested, not deployed**:
`tools/engines/chains.py`, migration **0062**, 25 tests, ADR-0102. The engine attenuates
multiplicatively, takes the weakest edge's tier, prunes to 20 by |effect|x confidence, refuses
an edge without all six REQ-INF-564 evidence fields, and reads `metric_registry.role` rather
than deciding what is actionable. Every invariant is enforced in the schema as well, because
the engine is not the only possible writer.

`analysis.chains` will be empty until hypotheses reach PROMOTED. That is correct and **it is
not coverage.**

**§D randomized micro-trials (B19.3) is now implemented and tested, not deployed:**
`tools/engines/trials.py`, migration **0063**, 29 tests, ADR-0104. It needed **no new
dependency** — the brief's dependency list described all of B19, and `statsmodels`/`scipy`/
`networkx` have been installed since B9. Treating that list as one gate would have held back a
unit that had no gate.

The arithmetic is sobering and is stated rather than hidden: **twelve blocks can only detect a
1.6 SD effect at 80% power; a 0.5 SD effect needs 126 blocks.** Most proposals will be refused,
and that is correct — an underpowered trial costs six weeks of Joe's compliance and returns a
null meaning "we could not have seen it" that reads as "it does not work".

**§G.3 regimes is now implemented and tested, not deployed:** `tools/engines/regimes.py`,
16 tests, ADR-0105. Validated against synthetic series with a KNOWN answer — both state means
recovered within 0.15 h / 200 steps, run-length median recovered as exactly the true 50-day
switching period, K=2 chosen by the pre-registered held-out criterion. REQ-INF-546's latent
level is included: ten days after a real step change it is out by **0.45** where a 28-day
rolling mean is out by **9.02**.

**ADR-0103 was amended after attempting the install, and two of its three assumptions were
wrong.** A dependency ADR written from package metadata is a PLAN to add a dependency, not
evidence it can be added:

- `jaxlib` ships **no macOS x86_64 wheel**. This machine is an Intel Mac, so `numpyro` fails to
  resolve at every version. CI would work; developing code that can never be run once where it
  is written would not.
- `dynamax` depends on **`tfp-nightly`** — a nightly build, unpinnable, contents change daily.
  That is a worse property than its size ever was and it is invisible in a wheel table. Rejected
  on that ground, and the HMM was written in numpy instead (~80 lines).

**Still unstarted: §G.2, the Bayesian effect layer** — the last piece of B19. Deferred, not
replaced: see **OQ-75**.

**B15 period/compare remains blocked on OQ-60's shape, not on its schedule.** Eight of fourteen
domain hero metrics do not resolve against the registry, and two (`hrv_sdnn`, `rhr`) are the
same measures the atom lane holds as `hrv_sdnn_ms` and `resting_hr`. A weekly report iterating
domains today would say "no data" for recovery and vitals while 1,333 observations sit in
`core.atoms`. Mapping them is a measurement definition and is Joe's (CLAUDE.md).

## THE UNPROVEN 460, CLASSIFIED

Measured 2026-09-10, not estimated: **445 of the 460 unproven requirements are code-only.** Only
~15 need Joe or hardware. The checkpoint's "blocked" framing was too generous — as with the
nutrition cascade (a constant nothing read) and REQ-CAP-093..099, much of what reads as blocked
is simply unwritten. `python3 tools/audit_requirements.py --open REQ-FIN` lists them.

Largest code-only blocks: REQ-FIN **36** (was 153), REQ-INF 100, REQ-CAP 83, REQ-NUT 30,
REQ-TIER 23, REQ-NAR 20.

REQ-FIN groups cleanly by spec section, and whole sections are unproven together — which is why
they fall in blocks rather than one at a time. §E (presentation restraint, 19) is now done.
Remaining whole-section blocks: D.2 evidence tiers 11, D.3 recommend-with-uncertainty 10, C.4 interventions 9, A.2 Gmail parsing 9 (needs Joe's OAuth),
D.1 the link object 7, C.1 necessity-is-a-tier 7.

## BLOCKED — needs Joe

| # | Decision | Unblocks |
|---|---|---|
| — | **Apply the six above** | every capability built since the import |
| OQ-60 | eight hero metrics: two renames to confirm, one to reject, five scope statements | B15 and every per-domain surface |
| OQ-55 | the Watch — worn / paired / permissions / storage | 17 stale metrics |
| OQ-57 | the 20 unruled Health types | what the next import takes |
| OQ-59 | two category vocabularies (`Food & Drink` vs `dining`) | category-level spend |
| OQ-61 | are `Online Transfer to/from CHK\|SAV` and `AUTOMATIC PAYMENT` all Joe's own accounts? | any income, savings-rate or net-spend measure. 94% of inbound money is internal; reading it as income overstates seventeen-fold |
| OQ-62 | should INSUFFICIENT copy have its own permitted vocabulary? | whether refusals are governed as tightly as claims |
| — | **the bank CSV export died 2026-05-13** | 38 empty days, then a source carrying a seventh of the value. Capture cannot be recovered later |
| — | the review sheet (40 ticks, 157 names) | 197 descriptors, ~19% of spend |
| — | install the Log Workout shortcut | strength — the stated primary objective |
| OQ-76 | `get_state.streaks` is live and the frontend brief forbids streaks on the same page | the frontend. Recommend renaming to `deviation_runs`; the data is fine, the word is the problem |
| — | **USDA api.data.gov key** | the two USDA legs of the nutrition cascade (the cascade itself is built) |
| — | **mark at least one metric `role='lever'`** | any micro-trial at all. The column defaults to `context` and nothing has been classified; defaulting it for Joe is what REQ-INF-565 forbids |
| OQ-74 | REQ-INF-540 names `dynamax`, which needs `tfp-nightly` and cannot run here | nothing is blocked; the behaviour is built and tested. This is whether the REQUIREMENT or the implementation gets corrected |
| OQ-75 | §G.2 Bayesian layer: CI-only, hand-rolled Gibbs, or defer? | the last unstarted piece of B19 |
| OQ-67 | private repo? **it now interacts with a second decision** | if private, Actions minutes are metered at 2,000/mo. The hourly `extract` job alone bills **720 of them — 59% of the budget — for a job whose measured median duration is 12 seconds**, because GitHub rounds per job to a whole minute. Halving its frequency recovers 360 minutes, six times what B19.1 costs |

## VERIFICATION AT THIS REVISION

361 local SQL tests under `America/New_York` and `UTC`; 104 pure-Python tests;
`validate_layout` 42/42; migration chain clean at 58; last full production suite
220 passed / 248 skipped / 1 failed, that failure fixed in `c38a6da`.

## FINDINGS THAT CHANGE WHAT THE NUMBERS MEAN

- **Both devices count the whole day.** Summing steps across them doubles them (measured, 1.98x).
- **The Watch stopped 2026-08-21**, in five stages. The phone never did.
- **The bank CSV export stopped 2026-05-13.** `chase_email` carries a third of the transactions
  and a seventh of the value, with 38 empty days between them.
- **94% of inbound money is internal transfer.** True merchant spending is the merchant-spend figure, not the
  the gross outflow of gross outflow.
- **Legacy `sleep_deep_min` is in HOURS** despite the `_min` suffix. Lanes are never blended.
- **A nap and a night share a subject day.** One night's 352-minute gap pushed sleep regularity
  from 87 to 208 minutes until sessions were split on the importer's own gap constant.

## DO NOT REPEAT

- "Capture stopped" is wrong. The **Watch** stopped; the phone did not.
- The five sleep concepts are not interchangeable and are never summed blind.
- Legacy `sleep_deep_min` is in HOURS despite the `_min` suffix. Lanes are never blended.
- Both devices count the whole day: summing steps across them doubles them (measured, 1.98x).
- A question's date is not its knowledge horizon. Two clocks, two parameters.
