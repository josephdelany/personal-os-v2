# Release evidence — handover

Worker: `work/release-evidence` at `/Users/default/PERSONAL_OS_V2_release_evidence`.
Tested revision: **`dc6bfbb`** (source tree clean). Evidence artifacts committed after it.

This document is the worker's report. It does not amend `docs/NEXT_SESSION.md`, which the main
session owns.

## The figure

**673 of 685 requirements have a named test that ran and passed**, measured by
`tools/evidence_report.py` from two runs at this revision, **neither of which touched the
production database**.

| suite | result |
|---|---|
| deterministic (`pytest tests/`) | 964 passed, 541 skipped, **0 failures, 0 errors** |
| disposable SQL (`tools/test_local_sql.py`) | 647 passed, 1 skipped |
| layout gate | 43 passed, 1 pre-existing warning |

The session checkpoint recorded **635** as the reproducible figure and **666** as the
better-covered one, where 666 required a live run against production that returned 38 setup
errors and 1 failure. 673 is both the higher number and the reproducible one — because the
tests that were timing out against production were never production's business.

**The remaining 12 are all skips.** No failures, no errors, no vacuous tests, nothing
uncollected.

## What OQ-78 actually was

The 38 `57014 canceling statement due to statement timeout` errors were **environmental in
symptom and a design defect in cause**. Eight test modules applied the migration chain — 68
files, 573 statements — to twin schemas **inside the production database** on every CI run,
because they were gated on `SUPABASE_DB_URL` rather than on the disposable server. Hundreds of
DDL round trips through the pooler is what timed out. A timeout is not a defect in the test, and
re-running it is not evidence.

Making them run somewhere revealed the twins were never wholly twins. The rewrite covered the
`__CORE__`/`__OPS__` placeholders and five `analysis` view names. Of the 68 numbered
migrations, **30 name `core.<table>` outright and 36 name `core`, `ops` or `analysis`
outright** — and every one of those references resolved to the REAL schema.
Contained by a rollback, but it was production core being read and written, contrary to the
fixture's own docstring and to RULE-01's "never core, never public".

All eight are now disposable-server-only, and **the guard is structural**: `apply_chain()` and
`migration_function()` raise without `PERSONAL_OS_TEST_SOCKET`, so a module that forgets the
mark cannot reintroduce production DDL. A lint in `tests/test_release_acceptance.py` fails if a
ninth module is written that builds schema without declaring it needs the disposable server —
verified by planting an offending module, which turned it red.

**OQ-78 can be closed on option (a)**, which was its own recommendation.

## The 12 unproven requirements, by cause

| cause | requirements | status |
|---|---|---|
| **Live-database reads** (10) | REQ-ASK-003, REQ-ASK-011, REQ-INF-109, REQ-INF-505, REQ-LOC-005, REQ-NAR-014, REQ-TIER-005, REQ-TIER-035, REQ-TIER-050, REQ-TIER-053 | Legitimate skips here. They read production data; they run in CI's `pytest` job. **Nobody has yet seen them pass.** |
| **Missing dependency** (1) | REQ-INF-520 | Skips on this machine only — Python 3.14 has no macOS x86_64 `jaxlib` wheel. CI installs NumPyro and sets `PERSONAL_OS_REQUIRE_DEPS=1`, so it runs there or fails loudly. |
| **Explicit production check** (1) | REQ-LOC-012 | Deliberate. Split out of a disposable test that was silently comparing against the empty set locally and reading production under the live job. Opt-in, read-only. |

The ten live-database requirements are the only ones whose evidence still depends on
production, and they are **data reads, not schema builds** — so the pooler timeouts that made
the live job unreadable should no longer apply to them.

## Release gates still open

1. **The live-database suite has never been proven green.** Ten requirements depend on it. The
   schema-building load is off it now, but that is a prediction until a run happens. *(Owner:
   main session — it owns production verification.)*
2. **REQ-INF-520 has never run in CI.** It is installed and gated now; no CI run has been
   observed since.
3. **REQ-LOC-012's live-view check has not been run.** Read-only, opt-in, not invoked here —
   this worker has no production authorization.
4. **Migrations 0055–0069, the backfill and the population are unapplied (OQ-77).** Unchanged by
   this work and untouched by it. Nothing here is a deployment.
5. **423 of 673 passing requirements have no reachability better than `tests-only`.** See below.

## Exact commands for the main session

Production verification. **Not run here.** Each needs `SUPABASE_DB_URL` in the environment; the
value must never be echoed, and these are read paths, not migrations.

```bash
cd /Users/default/PERSONAL_OS_V2            # or the release worktree

# 1. The live suite, with the dependency gate on and a result file that survives.
PYTHONPATH=. PERSONAL_OS_REQUIRE_DEPS=1 \
  python3 -m pytest tests/ -q -o xfail_strict=true --junitxml=/tmp/live_junit.xml

# 2. The one explicit production check (read-only; information_schema column names only).
PYTHONPATH=. PERSONAL_OS_PRODUCTION_CHECKS=1 \
  python3 -m pytest tests/test_derive_visits.py -q \
    -k REQ_LOC_012_live_visits_public_matches_the_twin_shape

# 3. Record the run, then merge all three result files into the report.
PYTHONPATH=. python3 tools/evidence_manifest.py --report /tmp/live_junit.xml --suite live
PYTHONPATH=. python3 tools/evidence_report.py \
  --report /tmp/deterministic.xml --report /tmp/local_sql_junit.xml --report /tmp/live_junit.xml
```

**Prerequisite and hazard.** `SUPABASE_DB_URL` is exported into the shell every agent session
inherits (OQ-80). Every command this worker ran stripped it (`env -u SUPABASE_DB_URL`), and
`tools/test_local_sql.py` pops it too. Anyone running the suite *intending* the disposable
server must do the same, or they are testing production by accident.

## What is now supported, and what is not

**Supported at `dc6bfbb`:**
- The two non-production suites pass, reproducibly, with results and provenance persisted.
- No test can build schema against production; this is enforced structurally and by lint.
- The nine scheduled engines are wired to entry points that start and load their whole import
  closure — verified by mutation, not assertion.
- The disposable server is pinned to UTC, so results no longer depend on the developer's
  timezone.

**Not supported:**
- That the live-database suite passes. Ten requirements rest on it.
- That anything here is **deployed** or **observed**. Both suites stop at the database boundary
  by construction. `ops/evidence/*.json` states this in a `stages` block rather than leaving it
  to the reader.
- That a passing named test demonstrates its requirement's whole sentence. That is the test
  body's meaning, and this worker checked it only where a test failed.

## For review with the main session: the 37 unconnected engines

`tools/engines/` holds 55 modules: **9 scheduled, 9 cli, 37 reachable only from `tests/`**. The
checkpoint noted these had never been individually triaged. Two facts from this revision:

**None of the 37 is entry-point-shaped.** Not one defines `run()` or carries a `__main__` block.
They are libraries, so "wire it up" is not a small change for any of them — each needs a caller
that does not exist.

**Five clusters are unreachable together**, because the only non-test importer of one
unreachable engine is another unreachable engine: `bayes_model`←`bayes_numpyro`;
`calibration`←`forecast_ledger`; `finance_never`←`finance_insights`;
`narration`←`finance_presentation`, `render_pipeline`; `tier_contract`←`forecast_ledger`,
`interrupted_series`, `multiplicity`. Connecting a cluster's root would move several at once.

Ranked by how many passing requirements reach them, the largest are `tier_contract` (65),
`narration` (54), `capture_budget` (38), `finance_never` (38), `finance_presentation` (35),
`recurrence` (30), `generator_gate` (28). *(This counts requirements whose test closure touches
the engine at all; the authoritative "no better than tests-only" figure is **423**, in
`docs/EVIDENCE_REPORT.md` column two. They are different questions and the two numbers should
not be merged.)*

**The distinction the main session should draw** is between modules that exist to be asserted
against and modules that are capabilities with no caller. The four named `*_contract`
(`tier_contract`, `ontology_contract`, `narration_contract`, `workout_contract`) are the
plausible first category — a contract module nothing calls is not obviously a defect. The rest
are not self-evidently either, and this worker did not guess: naming them requires knowing what
Joe intends each to do, which is not in the code.

## Required integration changes

1. **`tools/run_analysis.py` ignores `argv` entirely** and goes straight to `db.connect()`, so
   `--help` raises rather than printing usage. Recorded, not corrected — this worker does not
   own the runtime scripts. It is the only scheduled entry point that cannot be introspected
   without a database.
2. **`tests/_location_fixture.py` now owns the general whole-chain twin builder** and is
   imported by the spine and keepalive tests. The name is wrong. A rename touches every
   consumer, so it was left rather than done narrowly.
3. **Nothing else.** No runtime engine, migration or requirement was modified by this worker.

## Commits

| commit | what |
|---|---|
| `01ce5ca` | the location family stopped running the migration chain against production |
| `2cab2e8` | evidence manifest, dependency gate, acceptance checks |
| `92661e9` | the spine tests had the same defect; REQ-NFR-008 could run nowhere |
| `ef2dd76` | the last two production schema-builders, and a lint against a ninth |
| `f2e2115` | one meaning for "dirty", and a path slice that ate a character |
| `dc6bfbb` | evidence at a clean source tree |

Nothing was pushed. No other worktree was touched. No agent was spawned.

## Coordination: one expected conflict, and it is trivial

At the time of writing, `/Users/default/PERSONAL_OS_V2` (`session-21-recovery-and-ask`, HEAD
`7993c5a`, 7 uncommitted entries) has **also edited `tools/test_local_sql.py`**. Both sessions
appended to the tail of the same `TESTS` tuple, so merging will conflict textually there and
nowhere else.

**The resolution is the union of both lists**, not a choice between them:

- this branch adds ten: `test_confirmation_gate`, `test_movements_api`, `test_resolve_watches`,
  `test_derive_visits`, `test_restricted_location`, `test_recommendations`,
  `test_spine_invariants`, `test_spine_insert_paths`, `test_capture_schedule`, `test_keepalive`
- main adds two: `test_workout_session_r2` (already on main, not on this branch) and
  `test_service_usage_r4`

This branch's base, `48745d9`, is an ancestor of `7993c5a`, so a rebase is otherwise clean.

**A second, more interesting overlap.** Main's new `tools/service_usage.py` is described in its
own comment as "the first caller `recurrence.py` and `usage_status.py` have ever had". Those are
two of the 37 engines this report lists as reachable only from `tests/` — so that count becomes
35 once main lands, and `recurrence` (30 requirements) is among the heavier entries in the
triage table above. The table was measured at `dc6bfbb` and does not include main's uncommitted
work.

If `tools/service_usage.py` ends up started by a workflow rather than by hand, it belongs in
`REQUIRED_SCHEDULED_ENGINES` in `tests/test_release_acceptance.py`, so that its wiring is
defended the way the other nine are. That is a judgement about intent, so it is left to the main
session rather than guessed here.
