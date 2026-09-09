# ADR-0083 — Execution and documentation authority

Date: 2026-09-09. Status: accepted workflow direction from Joe; independent review
completed. Findings and verification evidence are recorded below.

## Context and authority

Joe requested a clear action plan/architecture and cleanup of conflicting instructions,
with backend completion before frontend work. The running goal was only “finish the
project.” Stale phase instructions, missing historical work queues, repeated full tests
on compaction and mandatory-negative reviews created avoidable ambiguity.

## Decision

CLAUDE is the shared policy; AGENTS routes to it. NEXT_SESSION owns active state;
EXECUTION_PLAN owns scheduling/acceptance; BACKEND_ARCHITECTURE consolidates existing
component contracts. Specifications, accepted ADRs and numbered constitutional rules
retain authority over behavior. Historical documents retain content but lose scheduling
authority. Original rewritten instructions are preserved under docs/history.

Startup hooks restore policy/constitution/checkpoint. They do not trigger tests simply
because context compacted. Completion evidence is scope-aware; an unchanged feature
ledger or no migration is not a reason to invent a status transition or migration.
Reviews remain independent and adversarial, with clean outcomes permitted when covered.
The constitution's amendment-review wording and Definition of Done reflect this.

## Consequences

Enables bounded continuation, dependency-first execution, truthful maintenance evidence
and backend-first delivery without deleting history. Does not authorize production
writes, relax integrity rules, settle protected data semantics, delete requirements,
change runtime architecture, or claim that any backend feature is now complete.

Failure mode: agents may mislabel implementation as documentation or use old passing
results for changed code. Mitigation: explicit changed-file scope, tested revision and
behavioral acceptance cases, plus independent review of this policy change. The
backend release gate still requires full integration and real operating evidence.

Number 0083 follows the existing 0082 record, leaving reserved build-order numbers alone.
No migration is associated with this decision.

## Independent review and verification

The independent reviewer found two gaps: requirement IDs were no longer explicitly
required in test names, and integration boundaries were undefined. Restored naming
in CLAUDE/Definition of Done and defined boundaries as milestone closure, shared
schema/API/engine integration, and deployment preparation. Neither fix changes a
backend requirement or lowers a gate.

Validation: layout 41 passed; destructive-command guard 26 passed; both session
skills validate; maintained Markdown links resolve; settings permission lists and
PreToolUse guard are identical to the retained original; all numbered constitutional
rules are byte-identical. Review covered policy documents, not active Ask code or
production. Live terminal adoption is not verified; the owner must read the updated
entry instructions at a safe boundary.
