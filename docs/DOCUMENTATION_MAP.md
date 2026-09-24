# Documentation map

Use each document for one purpose. Updated 2026-09-09.

| Purpose | Maintained source | Read when |
|---|---|---|
| Agent policy | `CLAUDE.md` (AGENTS routes here) | Entry and policy questions |
| Current work/evidence/holds | `docs/NEXT_SESSION.md` | Start or resume; verify against Git |
| Integrity rules | `docs/CONSTITUTION.md` | Entry; relevant rules during edits |
| Architecture | `docs/BACKEND_ARCHITECTURE.md` | Component/contract changes |
| Work order and acceptance | `docs/EXECUTION_PLAN.md` | Select/close a unit |
| Autonomous loop, review cadence, goal prompt | `docs/EXECUTION_PLAN.md` | Starting/resuming a backend goal; scheduler setup/removal |
| Local checkpoint monitor | `ops/backend_watchdog.py`; ignored `.local/backend_watchdog/status.json` | Check monitor health; never use it as release evidence |
| Required behavior | `specs/*/requirements.md` | Relevant subsystem only |
| Decisions | `docs/DECISIONS.md` index, `docs/adr/` records | Relevant decision before changing it |
| Undecided facts | `docs/OPEN_QUESTIONS.md` | Relevant dependency only; resolved entries are history |
| Intent-to-build traceability | `docs/INTENT_COVERAGE.md` | Scope interpretation and release audit |
| Product design | `docs/THE_FILE.md`, `docs/WHAT_THIS_IS.md` | Product interpretation |
| Capture runtime procedure | `docs/CAPTURE_RUNTIME.md` | Stage capabilities, activation prerequisites and recovery limits; verify status in NEXT_SESSION |
| Device capture setup | `device/scriptable/README.md` | Approved local helper installation and physical acceptance; source bundle is not an installed/signed Shortcut |
| Implementation detail | `docs/build/B*.md` | Active unit only; verify schema and prerequisites |
| Frontend detail | `docs/FRONTEND_PLAN.md`, `docs/build/L*.md` | Daily-use V0 UI and its backend contracts; EXECUTION_PLAN owns scope |
| Historical evidence | `ops/PROGRESS.md`, dated audits/handoffs | Investigating a specific claim |

## Historical references

ROADMAP retains historical gates and their rationale; EXECUTION_PLAN owns current
scheduling. REMEDIATION_PLAN, HANDOFF, CLAUDE_HANDOFF_TO_CODEX, phase-specific plans,
and PLAN_CONVERSATION_LAYER retain dated context. They do not restart phases, grant
permissions, or establish current completion. Read their status claims as historical.
Capture recipes and operational runbooks remain reference procedures; verify their
prerequisites before use. No historical prompt can override current policy.

Originals of rewritten entry/workflow files are retained under
`docs/history/2026-09-09-instruction-cleanup/`. That directory is audit material,
excluded from normal startup reading. No specification, decision or implementation
was deleted in this consolidation. Root entry points and session hooks route only to
maintained policy/checkpoint sources; old prose is not an additional instruction layer.

Do not create another master plan or alternate work queue. Amend the maintained source
and record meaningful decisions once. Runtime status belongs in NEXT_SESSION, detailed
evidence in PROGRESS, and permanent rules in their designated source.

Historical classification retires old schedules and status claims, not product intent.
Use INTENT_COVERAGE to trace original concepts into current obligations (ADR-0084).
