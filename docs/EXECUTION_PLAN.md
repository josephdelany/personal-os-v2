# Backend delivery plan

Active execution order, 2026-09-09. Joe directed completion of the backend before
frontend construction and consolidation of conflicting instructions. This plan
supersedes historical phase scheduling and the strict numeric order in build briefs.
It preserves requirements, acceptance gates, privacy, cost limits and reserved decisions.

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

## Milestones and dependency order

| Milestone | Build coverage | Acceptance evidence |
|---|---|---|
| M0: integration baseline | Current recovery/Ask branch | Preserve active work; every dependency of a claimed runnable commit tracked; checkpoint matches Git; current failures/gaps separated |
| M1: recover collection | B13, freshness, existing capture/locations | 0051 applied with permission; actual export reconciled; overlapping import idempotent; new device observation arrives unattended; withheld feed detected; deployed schedule verified |
| M2: deterministic Ask | B11.1 | All registered operations meet full contracts; required questions and adversarial cases pass; historical replay/provenance and executor permission separation proven |
| M3: shared services and capture | B12/B16 prerequisites, B11.2, then remaining B12/B16 | One egress/budget contract; validated planner and fallback; real planned question; real voice/photo path; reference-backed nutrition intervals |
| M4: complete domain processing | B14, B15, B17, B18 | Entity/correction precedence; linked meal-charge-place; period/compare contracts; finance reconciliation and complete scenarios; per-set workout progression |
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
