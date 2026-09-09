# Personal OS — agent instructions

Single-user system for Joe. Deliver the complete backend, then the frontend.
Joe verifies outcomes through runnable examples and independent review, not code reading.

## Authority and navigation

Current user instructions govern scope and authorization. Preserve the integrity
rules in [CONSTITUTION](docs/CONSTITUTION.md); report a conflict rather than bypassing them.
Accepted ADRs and `specs/*/requirements.md` define behavior. Read the relevant ones
before changing that behavior. Workflow and dependency order are maintained in
[EXECUTION_PLAN](docs/EXECUTION_PLAN.md). Architecture is in
[BACKEND_ARCHITECTURE](docs/BACKEND_ARCHITECTURE.md).

Read [NEXT_SESSION](docs/NEXT_SESSION.md) first, then this file and the constitution.
Inspect Git before trusting recorded state. After compaction restore the checkpoint;
do not repeat unchanged verification. Consult the relevant open questions and ADRs,
not the complete project history, unless evidence requires it.

`docs/build/B*.md` are implementation briefs, not an independent authority on order,
permissions, current schema or completion. Historical plans are reference material; their product intent remains relevant.
Use [INTENT_COVERAGE](docs/INTENT_COVERAGE.md) to prevent a narrower build checklist
from replacing Joe's cross-source and historical intelligence objective.
See [DOCUMENTATION_MAP](docs/DOCUMENTATION_MAP.md) for the maintained entry points.

## Execution

- Follow one bounded unit from EXECUTION_PLAN at a time. State its outcome,
  requirement IDs, acceptance cases and affected files before implementation.
  Implementation test names must contain the requirement IDs they cover.
- Continue authorized work autonomously. Capture recovery takes priority when its
  prerequisites are available; otherwise complete independent backend work.
- Keep NEXT_SESSION current at unit boundaries. Record evidence with the revision
  tested. Never collapse implemented, tested, deployed and observed into one status.
- Run targeted tests while editing and the required full checks at integration
  boundaries. Repeated failure calls for diagnosis, not more speculative patches.
- Finish the unit using the constitution's Definition of Done and session-end
  procedure. Make scoped commits under existing authorization; do not stage another
  worker's files. Do not declare a branch deployable while dependencies are untracked.
- Record architectural, measurement, scope and permission decisions in an ADR.
  Routine implementation choices within an accepted contract need no new policy.
- Batch genuinely missing Joe decisions with a recommendation and consequences.
  Keep dependent work held and continue independent tasks. Never infer approval
  from elapsed time. Existing explicit authorization persists.

## Integrity

- INV-1: derived rows trace to raw captures. INV-2: captures and atoms are append-only.
- INV-3: rendered numbers trace to stored computations. INV-4: no future knowledge
  enters a closed analysis window. INV-5: measured and inferred values stay separate.
- INV-6 / RULE-00: never weaken tests, thresholds or gates to make them pass.
- No fabricated personal data or placeholder success. Fixtures follow RULE-01's
  disposable-schema, rollback-only exception; never production/core/public tables.
- Execute arithmetic and statistics. Models plan and narrate; they do not compute
  or choose temporal specifications. Human corrections permanently outrank guesses.
- Disclose coverage, uncertainty, base rates and missingness. Missing is not zero.
  Recommendations obey evidence tiers; never diagnose or prescribe medically.
- Read before making claims. Raise concrete defects and tradeoffs candidly.

## Permissions, privacy and cost

Local reversible work and SELECT queries are permitted. Production writes,
destructive changes, force pushes and external disclosures require applicable
explicit authorization; prepare the exact action before requesting it. Respect
sandbox and hook refusals; never work around them. This cleanup grants none of these.

$0 recurring. Before dependencies are added, document limits, projected usage and
failure at the limit in an ADR; billing on overage is disallowed. Personal data may
leave only to Supabase, Cloudflare Workers AI and originating APIs under RULE-29.
Keep coordinate/home restrictions and read/egress process separation (ADR-0020).
Log every outbound model call. Credentials come from environment or repository
secrets, never chat, source files or logs. Public Git contains code, not personal data.
