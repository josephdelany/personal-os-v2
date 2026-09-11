# Worker 1 — release evidence and the verification run

Worktree `/Users/default/PERSONAL_OS_V2_release_evidence`, branch `work/release-evidence`,
created from `48745d9` (clean). Integration owner: Session 1 (main). Read `AGENTS.md`,
`CLAUDE.md`, `docs/CONSTITUTION.md` and `docs/NEXT_SESSION.md` first.

## You own these files. Nobody else edits them.

- `tools/evidence_report.py`, `tools/audit_requirements.py`, `tools/update_features.py`
- `tests/conftest.py`, `tests/_sql_fixture.py` and the shared fixture helpers
- `.github/workflows/tests.yml`
- `docs/EVIDENCE_REPORT.md`, `docs/REQUIREMENT_EVIDENCE_AUDIT.md`
- Tests named `tests/test_evidence*.py`, `tests/test_audit*.py`

## You do NOT own

`.github/workflows/analysis.yml` (main owns it — propose the exact edit, do not make it),
migrations, `lib/`, `tools/engines/*`, `tools/reconstruct*`. Capture workflows are Worker 3's.

## The objective

**A verification run whose number is reproducible, and which nobody has to caveat.**

The current figure is **635 of 685**, and it currently ships with a mandatory sentence: a
third run against the live database finished with 38 errors (all `57014 statement timeout`)
and 1 failure, which would give 666/685. That caveat is the deliverable to remove — not by
dropping the sentence, but by making one of the two numbers defensible on its own.

1. **Find out whether the live-database suite passes.** Nobody has that evidence. CI's `pytest`
   job takes that path and its survival depends on pooler latency. Diagnose the 38 timeouts:
   they are environmental, but "environmental" is a claim that needs a cause, and the run
   started against a dirty tree. Establish whether a clean-tree run reproduces them.
2. **Coordinate the final verification run** and record: revision, environment, both suites,
   layout, migration chain. You are the only worker who runs the full database-heavy suite;
   Worker 2 and Worker 3 use disposable databases so they do not compete with you.
3. Keep `evidence_report.py --check` honest. It regenerates and exits 1 on drift; that property
   is the reason the number cannot be edited, so do not weaken it (INV-6 / RULE-00).

## Constraints

- **Never weaken a test, threshold or gate to make it pass.** A skip is not a pass.
- A missing-*library* skip must fail CI (`PERSONAL_OS_REQUIRE_DEPS=1`); a missing-*data* skip is
  a true statement about the world and must not.
- SELECT against production is permitted. Writes, DDL and destructive changes are not — not even
  behind a rollback. `tests/test_status_sql.py` once ran `CREATE SCHEMA` against production
  behind a rollback and that was closed; do not reopen it.
- Do not stage or commit another worker's files. Scoped commits only.

## Handoff

Finish with: what you measured, at which revision, in which environment; what is still
unproven and why; the exact remaining acceptance gates. Joe relays it to main.
