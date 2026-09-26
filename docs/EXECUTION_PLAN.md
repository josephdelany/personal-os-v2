# Backend delivery plan

Active execution order, 2026-09-09. Joe directed completion of the backend before
frontend construction and consolidation of conflicting instructions. This plan
supersedes historical phase scheduling and the strict numeric order in build briefs.
It preserves requirements, acceptance gates, privacy, cost limits and reserved decisions.

## Current goal — usable daily V0 (Joe, 2026-09-24; ADR0165)

Joe replaced complete-backend-first delivery with a limited program he can use
while the larger project continues. This section supersedes the M0–M6 stopping
condition and historical backend-first prompts below. Integrity, privacy, access
control and explicit production authorization remain binding. Finish the current
correction change, then work exclusively on this daily-use path. Do not expand
capture corrections or advanced analysis merely to close the eventual backend.

Latest sequencing: Joe’s new goal is a usable **V0 backend first**, then its
frontend, then the remaining project. Implement and verify the backend contracts
for the screens below before frontend construction. The real-phone/day bar remains
the complete V0 release criterion; do not claim it from backend tests alone.

### Product and flow scope

Three screens, mobile first, with calm, attractive design and everyday actions easy
to reach. Usability and aesthetics are release requirements, not later polish.

| Screen | Required behavior |
|---|---|
| Today | Morning check-in, latest health/activity, recent spending, meals, evening check-in; explicit last-received timestamps |
| Add | One-tap access to meal photo/text, check-in and workout entry; durable-save acknowledgement separate from processing |
| History | Browse a previous day, inspect entries and correct them |

| Flow | V0 scope |
|---|---|
| Location | Collect and show recent visits, no behavioral interpretation |
| Credit cards | Import an actual supported export, deduplicate, show spending; bank connection deferred |
| Biometrics | Available imported measurements, units and freshness |
| Movement | Steps, activity and recorded workouts; no coaching |
| Morning | Sleep quality and energy, each integer1–10, optional note; approved by Joe |
| Meals | Save photo/text and show history; pending nutrition distinguished from verified results |
| Evening | Mood and energy, each integer1–10, optional reflection; approved by Joe |

Joe explicitly approved the proposed check-in fields with 1–10 scales. Store
ratings as subjective reports; do not derive clinical meaning or combine scales.
Existing capture-device restrictions remain; expose the approved capture helper
clearly, or prepare an explicit requirement decision if direct browser capture is
needed. Do not silently bypass existing capture policy.

New 1–10 check-ins require distinct versioned measurement definitions; historical
0–10 observations must not be relabeled or silently combined with them.

### V0 backend handoff checklist

The current goal closes the backend handoff, not the later phone-interface release.
For each row, require an executable caller, owner access checks, saved/read-back
behavior, failure/retry evidence and an activation procedure. Existing file names
are starting points, not completion claims. Exclude advanced M0–M6 requirements
unless the daily path actually depends on them.

| Contract | Existing starting point | Remaining V0 acceptance |
|---|---|---|
| Morning/evening | 0091 save_v0_checkin/get_v0_checkins; integrated65796bd, local acceptance passed | Activation and real-account caller; daily read locally integrated |
| Meals | 0092 save_v0_meal/get_v0_meals; integrated92d2e08, local acceptance passed | Activation, real-account text/photo save and private Storage delivery; daily read locally integrated |
| Workouts | 0093 save_v0_workout/get_v0_workouts; full local acceptance passed | Activation and real-account caller; daily read locally integrated |
| Health/activity | 0094 get_v0_day, local acceptance passed; import_drop/apple_health | Real-account import/read, actual registered aggregate configuration and source freshness |
| Spending | 0095 owner card activity/review and private import_v0_card CLI; actual Chase credit format validated, local acceptance passed | Activation/actual-account import; day composition locally verified in0096; unresolved overlaps require owner review, canonical finance remains deferred |
| Visits | 0096 retry-safe Overland receipt, get_v0_visits and hourly refresh; local acceptance passed | Activation, real-device collection and owner readback; no interpretation |
| Day history | 0094 get_v0_day composes current V0 IDs and health, local acceptance passed | Spending/visits composed in0096 and locally verified; activation and real-account read/correction |
| Owner access/operations | Authenticated RPCs; app/v0_client.mjs and V0_OWNER_CALLER; read-only preflight and V0_BACKEND_ACTIVATION packet | Caller integration gates; live auth/access checks; exact deployment list after inventory; real-account backend smoke |

After these backend contracts are usable, begin frontend work. Keep the complete
real-phone day checklist below for frontend/release acceptance; neither gate proves
the advanced project complete. Preserve the explicit production authorization gate.

### Work order and release bar

1. Finish the in-flight correction regression and preserve its evidence. ADR0164
   is integrated at5c47bfb; name-replacement regression is the final in-flight check.
2. Trace each daily flow through existing UI, authenticated API, storage and real
   data. Implement the minimum missing connections needed by these flows; keep one
   active unit in NEXT_SESSION. Reuse working infrastructure and paused UI assets.
3. Build the three-screen daily experience with loading, empty, stale, saved,
   processing and recoverable-error states. Verify phone-sized journeys and review
   visual hierarchy as part of implementation.
4. Prepare exact activation/publication changes, obtain required authorization,
   and verify on Joe's actual account/device/data. Local fixtures are not release proof.

V0 is releasable only when all of these outcomes are observed:

- Joe signs in on his phone without agent help.
- Every entry saves visibly or gives a recoverable error.
- Retrying never creates duplicate entries.
- Missing data never appears as zero.
- Yesterday can be reviewed and an entry corrected.
- One complete day works with Joe's real account and data.

Defer advanced inference, recommendations, correlations, elaborate dashboards and
perfect automation. Full M0–M6 remains the later project backlog, not a prerequisite
for this release. V0 completion must not be reported as full backend completion.

## Goal contract

A `/goal` to finish the project executes this plan. It does not select a new scope on
each turn. The implementation owner maintains ONE active unit in NEXT_SESSION with:

- Outcome and exact requirement IDs; applicable B-file and accepted ADRs.
- Required positive, negative and missing-data acceptance cases.
- Files owned, dependencies, external holds and next executable action.
- Last test command/result and revision; implemented/tested/deployed/observed separately.

Resume that unit after compaction. Close it or record a specific dependency before
switching. A new bug in the active contract belongs in its acceptance list. Unrelated
work goes to the relevant later milestone. No fabricated time estimate or completion
percentage; report completed outcomes and remaining acceptance cases.

## Autonomous loop (Joe's direction, 2026-09-22; ADR-0142)

The active objective and stopping condition are the **daily-use V0 contract above**.
M0–M6 below remains the later backend backlog. `/goal` is the execution
driver; a cron is not a coding agent. Start the goal only when Joe submits it.

### Resume and select

1. Read NEXT_SESSION's current control block and active-unit section, then CLAUDE,
   CONSTITUTION, this plan, architecture and the relevant contracts. Inspect Git
   status/worktrees before editing. Preserve other workers' changes and confirm
   ownership; a historical worker assignment does not prove a live worker exists.
2. Resume the active unit unless it is complete, newly blocked or displaced by
   imminent data loss/an integrity defect. Select the earliest actionable milestone
   dependency. Capture recovery has priority when actionable; otherwise continue
   independent M2–M5 work. Do not restart completed inventory or planning because
   a historical paragraph says "next".
3. Write ONE bounded acceptance contract at the top of NEXT_SESSION: outcome,
   requirements/ADRs, positive/negative/missing-data cases, owned files, dependency,
   test commands and next action. Keep implementation/test/integration/deployment/
   observation as separate states. Milestone tables below define the entire scope;
   this active unit is one step, not a reduced definition of done.

### Build, test, challenge, repair

4. Reproduce the gap through the actual consumer when possible. Implement the
   smallest coherent unit; add behavioral regression tests, including the failure
   path. Use disposable databases and the sanctioned fixtures. A helper returning
   the expected dictionary is insufficient proof of storage, hosting or delivery.
5. Run targeted checks, then review with all eight quality lenses below. Try the
   cases that would falsify the completion claim. Fix findings within the unit and
   repeat affected checks. After two failed repair attempts on one case, stop
   speculative changes, reread the contract and diagnose the cause. Record a clean
   review's coverage and limits without inventing defects.
6. At integration boundaries run the required full suite, disposable SQL, migration
   chain when relevant, invariant and layout checks, and the sanctioned feature
   ledger writer. Remove production credentials from local test environments;
   never use bare pytest with a production URL. Keep JUnit artifacts and their
   tested revision/dirty state, reconcile skips, and generate requirement evidence.
   A green suite plus missing runtime connections is still partial work.
7. Close the unit under the constitution's Definition of Done, use scoped commits
   when permitted, update NEXT_SESSION and PROGRESS, and **continue immediately to
   the next actionable unit**. Do not ask "shall I continue?" or stop merely because
   one milestone, review, test run or context window ended.

### Adaptive instruction sheet

NEXT_SESSION is the living instruction sheet. Its single `backend-control` JSON
block is a small scheduling header, not a second requirement ledger. Update it and
the adjacent active-unit prose together after each unit, failed attempt, changed
dependency, user steering, or before context handoff. During long work checkpoint
at a safe boundary approximately every 30 minutes, identifying the running check
and its log rather than launching it again.

- `status`: `ready` before Joe starts; `running` while actionable work remains;
  `held` only when all useful authorized work is externally blocked;
  `release_declared` only after the release decision is evidenced.
- `updated_at`: actual UTC checkpoint time. `last_progress_at`: actual time of the
  last implemented change, completed verification, or concrete new diagnosis.
  Updating prose or rerunning unchanged checks alone is not progress.
- `unit` and `next_action`: the current bounded unit and exact next operation.
  Record requirement IDs, acceptance cases, ownership, last command/result,
  evidence references, open findings and holds in the adjacent prose.
- Each hold names the missing fact/action, owner, affected requirements, evidence,
  recommendation, and recheck trigger. Queue ordinary engineering gaps in the
  relevant milestone; only reserved decisions belong in OPEN_QUESTIONS.
- Adapt task order and methods to new evidence, never silently change scope,
  measurement definitions, constitutional rules, acceptance thresholds or approved
  architecture. An internal dependency is work, not an authorized deferral.

### Scheduled checks and anti-stall loop

| Trigger | Action | Meaning and limits |
|---|---|---|
| Each goal continuation / context restoration | Restore active unit; inspect latest checkpoint and watchdog snapshot | Continue work without redoing unchanged tests |
| Every completed unit | Update evidence, holds, active unit and next action | Goal owner writes the instruction sheet; scheduler never rewrites it |
| After two failed repairs of one case | Reproduce, inspect contract and diagnose | No test weakening or repeated blind patching |
| Every 15 minutes, local launchd | `python3 ops/backend_watchdog.py --write-status` | Local snapshot only; advisory alert after 90 minutes without checkpoint/progress; no models, DB or production writes |
| Each integration boundary | Full quality/release checks appropriate to the change | Publish evidence locally; no repeated full suite on every timer |
| Once per UTC day while the goal runs, and before deployment | Read actual workflow/default-branch state and available source freshness; reconcile holds | Check only with available credentials; do not run a status command that writes production without authorization |
| At M6 closure | Review every milestone/requirement/scenario and observed deployment, then disable the temporary watchdog | A fresh heartbeat or passing test count cannot authorize completion |

The watchdog is macOS launchd (the local cron equivalent), label
`com.personalos.backend-watchdog`. Its bounded snapshot is
`.local/backend_watchdog/status.json` (gitignored). A recent `checked_at` proves the
monitor ran; `checkpoint_recent` describes timestamps, not semantic progress.
Missing/malformed/future-dated control is unhealthy. `release_verified` is always
false: only the release review can certify the backend. A held state is reported
without treating elapsed time as approval. Read the snapshot on each continuation;
if stale, inspect ongoing work, diagnose and choose a useful next action.

Local scheduling requires the Mac's user session; sleep/offline/app interruption
is not solved by instructions. The watchdog cannot wake/restart a stopped `/goal`,
does not invoke a model, and cannot send a chat notification. No scheduler-management
tool for recurring agent sessions is exposed in the setup session. If the goal
stops externally, resume it from NEXT_SESSION. Do not start a second writer to
simulate continuity. Native scheduled-task availability is described in the
[official documentation](https://learn.chatgpt.com/docs/automations).

Existing production cron jobs are separate: capture import, freshness, tests and
analysis require deployment/activation evidence. Their configuration is not proof
they run. This setup authorizes the local monitor, not an implicit production
cutover or publication of unreviewed backend code.

Install/verify the monitor after tests pass (generated plist contains no secrets):

```sh
mkdir -p .local/backend_watchdog
python3 ops/backend_watchdog.py --emit-launchd > .local/backend_watchdog/com.personalos.backend-watchdog.plist
plutil -lint .local/backend_watchdog/com.personalos.backend-watchdog.plist
mkdir -p ~/Library/LaunchAgents
cp .local/backend_watchdog/com.personalos.backend-watchdog.plist ~/Library/LaunchAgents/
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.personalos.backend-watchdog.plist
launchctl print "gui/$(id -u)/com.personalos.backend-watchdog"
cat .local/backend_watchdog/status.json
```

If already registered, inspect it rather than blindly bootstrapping again. At
completion, `launchctl bootout "gui/$(id -u)/com.personalos.backend-watchdog"` stops
the job; remove only its installed plist to prevent restart next login. Record
removal. Keep production monitoring intact.

### Holds and the actual stopping condition

Prepare exact reviewable production actions before requesting the authorization
required by CLAUDE. Ask for missing decisions once with recommendations, then work
independently while waiting. OQ-48/OQ-51 and other reserved measurement decisions
remain Joe's. OQ-82's fixture exception is not granted by this automation request.
Do not poll an unchanged external hold every turn or manufacture an implementation
substitute for a missing observation.

If every remaining unit is externally held, record the exact unblock list and
follow the goal runtime's blocked-state rules. In this environment, mark a goal
blocked only after the same impasse recurs for three consecutive goal turns with
no meaningful independent progress; resumed goals start a fresh audit. Never mark
complete to stop the loop. Mark the active V0 complete only when its real-account
release bar above passes; this does not close the complete-backend backlog. Report
what is implemented, deployed and observed, and any permitted activation hold.

### Historical full-backend prompt — superseded by V0

```text
/goal Finish the complete Personal OS backend through M6 in docs/EXECUTION_PLAN.md.
Follow its autonomous loop and eight quality checklists. Use docs/NEXT_SESSION.md
as the living instruction sheet and update it after every unit and handoff.
Start by preserving/reconciling current work, then repair and connect capture,
prioritizing actionable recovery. Continue through all remaining backend milestones,
not just capture. Build, test, challenge, repair, record evidence, and take the next
action without asking whether to continue. Respect file ownership, reserved decisions,
production authorization and all integrity rules. Work independent tasks around holds.
Do not begin frontend construction or call the backend done until the release gate passes.
```

## Milestones and dependency order

| Milestone | Build coverage | Acceptance evidence |
|---|---|---|
| M0: integration baseline | Current recovery/Ask branch | Preserve active work; every dependency of a claimed runnable commit tracked; checkpoint matches Git; current failures/gaps separated |
| M1: recover collection | B13, freshness, existing capture/locations | 0051 applied with permission; actual export reconciled; overlapping import idempotent; new device observation arrives unattended; withheld feed detected; deployed schedule verified |
| M2: deterministic Ask | B11.1 | All registered operations meet full contracts; required questions and adversarial cases pass; historical replay/provenance and executor permission separation proven |
| M3: shared services and capture | B12/B16 prerequisites, B11.2, then remaining B12/B16 | One egress/budget contract; validated planner and fallback; real planned question; real voice/photo path; reference-backed nutrition intervals |
| M4: complete domain processing | B14, B14R, B15, B17, B18 | Entity/correction precedence; reconstruction-local cases R1-R8/R10/R12; linked meal-charge-place; period/compare contracts; finance reconciliation and complete scenarios; per-set workout progression |
| M5: remaining analysis | B19, B20, B21 | Required inference, scoring/calibration/trials, narration/ontology, body/sleep/context specifications and implementations; temporal and uncertainty checks |
| M6: backend release | B22/B23 and full integration | Requirement/scenario audit; deployed API and schedule evidence; replacement capture before authorized cutover; runbook; no unexplained open requirement |
| M7: frontend | L0-L8 | Begins after backend release; actual screens validated against stable responses; tier-label prerequisite before enabling exploratory presentation |

M1 is highest priority when actionable. External holds there do not stop M2-M5.
Finish the current bounded Ask piece before a routine switch; imminent data loss or
an integrity failure takes priority. Pull shared prerequisites forward explicitly;
do not wait for B12 to finish before building the component B11.2 needs.

Read the matching [build brief](build/README.md) and actual schema before each unit.
B0-B10 existing components require integration evidence, not wholesale rebuilding.
Bookkeeping numbers in old briefs are not safe migration reservations: inspect the
current branch and coordinate the next filename with the integration owner.

## M2 acceptance checklist

- Describe, rhythm, last and counts: correct windows, units, missingness and denominators.
- Trend: both requested-period behavior and promised rolling-28-day output.
- Compare: outcome X conditioned on distinct Y, correct lag and group counts, delta,
  missing condition observations excluded, both inputs' coverage disclosed.
- Contrast/effect: exact driver direction and lag, compatible window or explicit
  disclosure/refusal, historical finding status, no causal vocabulary above tier.
- Spend: agreed merchant/category semantics, currencies, deduplication, refunds and
  transfers per finance requirements, totals/counts/typical-week/top-merchant contract.
  A descriptor-only partial implementation cannot close the full contract.
- Search/entity: actual records and entity responses, not only a count wrapper.
- All paths: result persisted before rendering; source trace; registered rounding;
  low/absent coverage; unsupported operation refusal; historical replay after later
  data/corrections; required read/write/network separation.
- B11.2 remains separately open until validated planning, iteration cap, budget,
  deterministic fallback, deployment and a real question are verified.

Each item closes with behavioral evidence, not a test name alone. The current
checkpoint identifies completed subcases; do not redo them without new evidence.

## Verification and review

An integration boundary occurs when a backend milestone closes, shared schema/API/
engine changes are integrated, or a deployment is prepared. Complete required full
checks before declaring any of those boundaries passed. Small unit checkpoints do
not reset or postpone the milestone gate. Record the tested revision and environment;
reuse unchanged evidence only when its applicability is explicitly established.

Implementation test names contain their requirement IDs for the evidence tooling.

Use targeted tests during edits. Run required full suite, invariant and layout checks
at integration boundaries; repeat for relevant changes/failures, not compaction alone.
A documentation-only unit needs document/configuration checks, not a production test
run. Preserve all integrity requirements and name existing deferrals explicitly.

If the same case fails after two repair attempts, inspect the authoritative contract,
reproduce the cause and repair coherently before further patches. This is a diagnostic
trigger, not permission to ignore a failure. Review concrete changed behavior and
integration risks. Clean reviews with recorded coverage are valid. Re-review fixes
and affected paths; never require invented findings or accept unverified closure.

Run `tools/update_features.py --strict` at backend integration checkpoints through
its sanctioned writer. Its narrow ledger is not a full completion scoreboard. B23's
requirement ledger must include passing behavioral evidence and authorized deferrals;
matching an ID to a passing test is an index, not proof of full requirement fidelity.
Do not mass-defer requirements to obtain zero open items.

## Quality review at backend boundaries

Joe requested multiple independent checklists on 2026-09-22 because implementation
is being directed without routine personal code review. The implementation owner
must supply the evidence and explain the remaining risk in plain language. Apply
these review lenses within the existing verification and release gates; they do
not replace requirements or authorize new deferrals:

- **Contract fidelity:** read the requirement, exercise its behavior, and inspect
  the assertions. A passing test name alone does not prove the full contract.
- **Complete user paths:** enter through the actual CLI/API/job, persist the
  result, read it back, and check provenance, units, uncertainty and refusal.
- **Failure behavior:** missing configuration, invalid input, duplicates and
  concurrent retries, partial writes, downstream outage, budget exhaustion and
  recovery. Test interacting components, not only their separate helpers.
- **Data integrity:** append-only facts, correction precedence, historical replay,
  event/knowledge time, missingness and measured/inferred separation.
- **Access and privacy:** absent credentials must fail closed; verify actual role
  permissions and permitted egress, including the log and shared budget.
- **Runtime and deployment:** distinguish import reachability, an exercised entry
  point, the deployed revision and an observed scheduled outcome. Verify the
  remote default branch and workflow runs rather than local YAML alone.
- **Operations and recovery:** observation freshness separate from job success,
  withheld-feed detection, retries, applicable storage/cost bounds, recovery and
  cutover evidence, and a runbook matching the deployed system.
- **Evidence and reproducibility:** exact revision plus dirty-tree status,
  environment and commands; explain skips, pending invariants and unavailable
  checks. Record failures and verification limits without turning them green.

Use PASS only for the stated scope actually verified; otherwise record FAIL,
PARTIAL or NOT VERIFIED with the missing acceptance case. Keep findings in
COMPLETION_AUDIT and the next bounded unit in NEXT_SESSION. Do not turn these
review lenses into a second work queue or a completion percentage.

## Integration ownership and parallel work

One owner manages shared contracts, migration allocation, integration and deployment.
Additional workers, when authorized, use separate worktrees and disposable databases,
with disjoint file ownership and an explicit acceptance contract. No shared production
migration execution, branch switching, bulk staging or database fixtures.

Close coherent units with scoped commits. Before calling a branch reproducible, check
that its tests, fixtures and runtime dependencies are tracked and runnable from a clean
checkout. A partial commit is a checkpoint, not a release. Record blocked commit/push
steps accurately and continue permitted independent work.

## External dependencies

NEXT_SESSION carries the current held-action list with action, reason and dependent
capability. OQ-48/49/50/51/53 and deployment questions remain explicit. Joe provides
exports, device configuration and reserved definitions; agents prepare concrete options.
Production authorization must be applicable to the exact action. Do not bypass refusals.

## Release decision

Backend release requires all in-scope behaviors proven or explicitly deferred by a
cited authorized ruling, real-data and deployment checks complete, and operations
verified. Findings awaiting future observations are pending evidence, not missing code.
A frontend tier-label prerequisite can remain a documented activation hold; do not
claim live exploration operational until that prerequisite is met. Other failed gates
remain failed. Frontend construction begins only after this backend decision.

## Intent coverage is part of completion (ADR-0084)

Read [INTENT_COVERAGE](INTENT_COVERAGE.md) when interpreting product scope. Historical
plans retain product ideas even when their schedules/status are superseded. The original
vision is not satisfied by a fixed list of links and metric queries.

Next independent scope task: perform REQ-REC-001..004 source-to-capability inventory
through [B14R](build/B14R_reconstruction.md), using counts/metadata and marking missing
old-workspace assets unverified. Do not interrupt active integrity repairs or real-data
recovery to restart planning. Complete inventory before M4 closure; map every omission
to an implementation owner. M4 implements REC event reconstruction; M5 integrates its
uncertainty with existing cross-domain discovery and closes cross-consumer R9/R11; M2 gains registered reconstruction
queries through that dependency. M6 includes REC coverage and R1-R12 evidence.

An internal dependency remains OPEN until its consuming requirement is satisfied.
Recording it does not authorize deferral. Historical trait/medical language conflicting
with current rules stays prohibited; original concepts are reconciled, not blindly copied.
