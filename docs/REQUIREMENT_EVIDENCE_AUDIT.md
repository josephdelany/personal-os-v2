# Requirement evidence audit

Produced by `tools/audit_requirements.py`. This document replaces the claim that every
requirement is *proven*, because the tool that produced that claim never ran a test.

## What the old report said, and why it could not be true

`docs/NEXT_SESSION.md` opens with **"EVERY REQUIREMENT IS PROVEN: 685 of 685"**, and the old
`tools/audit_requirements.py` prints, verbatim:

```
  685 of 685 requirements (100%) are proven by a test carrying their ID.
```

The tool computed that by globbing `tests/**/test_*.py`, matching `def test_...` with a regex,
and extracting requirement IDs from the **function names**. It read no result file. It could not
distinguish a green test from a skipped one, a failing one, or one that was never collected,
because it never asked. A requirement was "proven" as soon as somebody typed its ID into a
function name.

That is not a small over-count. It is a category error: the output is a percentage, and a
percentage is the one form of evidence nobody re-derives.

## What is actually known

Generated 2026-09-10T18:39:28+00:00 against `f1f7249` on `work/evidence-audit`.

Reproduce with:

```
python3 tools/audit_requirements.py --junit junit_worktree.xml --junit junit_auditonly.xml
```

- Results read, two files merged:
  `junit_worktree.xml` — 1413 testcases, 1286 passed, 127 skipped;
  `junit_auditonly.xml` — 31 testcases, 31 passed
- Produced by `pytest tests/ -q -o xfail_strict=true --junitxml=...` with `SUPABASE_DB_URL`
  **unset**, against a disposable PostgreSQL 17 server (ADR-0082) on port 55434. **No
  production test was run and no production data was written.**
- Auditing interpreter: python 3.14.3 / darwin. Not importable in it: `jax`, `numpyro`
- Of the 127 skips: **125** carry a `SUPABASE_DB_URL not set` message and **2** carry
  `NumPyro not importable`. Every skip in this run is an environment condition, not a failure.
- Evidence file `ops/requirement_evidence.json`: **does not exist**, so levels 4-6 are UNKNOWN
  for every requirement

| family | declared | mapped | tests passed | integrated | deployed | observed | orphan |
|---|---:|---:|---:|---:|---:|---:|---:|
| 02-capture-nutrition | 162 | 162 | 162 | 0 | 0 | 0 | 0 |
| 03-finance | 174 | 174 | 174 | 0 | 0 | 0 | 0 |
| 04-reasoning | 236 | 236 | 211 | 0 | 0 | 0 | 0 |
| 05-ontology | 16 | 16 | 14 | 0 | 0 | 0 | 0 |
| 06-nfr | 14 | 14 | 12 | 0 | 0 | 0 | 0 |
| 07-workout | 22 | 22 | 22 | 0 | 0 | 0 | 0 |
| 08-location | 18 | 18 | 6 | 0 | 0 | 0 | 0 |
| 09-action | 12 | 12 | 4 | 0 | 0 | 0 | 0 |
| 10-reconstruction | 16 | 16 | 16 | 0 | 0 | 0 | 0 |
| 11-sleep | 15 | 15 | 15 | 0 | 0 | 0 | 0 |
| **TOTAL** | 685 | 685 | 636 | 0 | 0 | 0 | 0 |

Columns are cumulative and the ladder is monotonic, so no column can exceed the one to its
left. Read across the bottom row: **685 declared, 685 with a named test, 636 whose named tests
all actually passed in a real run, and nothing at all known about integration, deployment or
observation.**

The three zeros are the correction. They are not a claim that nothing is integrated — several
things demonstrably are. They are the statement that **no integration, deployment or
observation has been written down in a form this report can cite**, and the tool refuses to
infer one from a passing test or a source import, because that inference is what produced the
claims now under review.

## The six levels, and why they are not substitutes

| level | means | source |
|---|---|---|
| 1 DECLARED | the ID exists in `specs/*/requirements.md` | the specs |
| 2 MAPPED | ≥1 test **function name** carries the ID | AST parse of `tests/` |
| 3 TESTS_PASSED | every mapped test was collected **and** passed | JUnit XML |
| 4 INTEGRATED | a real application path exercises it | declared reference only |
| 5 DEPLOYED | applied to production | declared reference only |
| 6 OBSERVED | verified against real data | declared reference only |

Level 3 is called `TESTS_PASSED` and never `PROVEN` or `COMPLETE`. A passing mapped test is
evidence about the assertions inside that test. A requirement declaring a five-step cascade is
not covered by a test of one branch of step two, and the tool does not pretend otherwise — it
prints the mapped tests by name so a reader can judge for themselves.

### What cannot produce a pass

Locked by tests in `tests/test_audit_requirements.py`:

- a **skipped** mapped test — `test_a_skipped_mapped_test_never_reaches_TESTS_PASSED`
- a **failed or errored** one — `test_a_failed_or_errored_mapped_test_never_reaches_TESTS_PASSED`
- one that was **never collected** — `test_a_mapped_test_that_was_never_COLLECTED_never_reaches_TESTS_PASSED`
- **no result file at all** — `test_with_NO_result_file_level_3_is_unknown_and_never_passed`
- one passing test beside skipped siblings — `test_the_worst_outcome_wins_across_several_mapped_tests`
- a single skipped parametrised case — `test_one_skipped_parametrised_case_prevents_TESTS_PASSED`
- **all mapped tests passing** does not produce integration —
  `test_all_mapped_tests_passing_does_NOT_produce_integration_evidence`
- declared deployment evidence cannot skip a rung —
  `test_the_ladder_is_monotonic_so_deployment_evidence_cannot_skip_a_rung`

### Two result files, not one

This repository's CI runs the suite **twice** and each job skips the other's tests by design.
Of the 127 skips in the audited run, 125 carry a `SUPABASE_DB_URL not set` message. So the
tool accepts `--junit` repeatedly and merges, under a deliberately asymmetric rule: **a failure
in any run makes a test failed; a pass requires a named run that produced it; two skips stay
skipped.** Reading one file alone would report the disposable-server requirements as untested,
which is an under-count — the same defect pointing the other way.

**The merge cannot be performed today**: neither CI job persists a JUnit report. See
*Workflow changes needed* below.

## The 49 requirements whose named tests did not all pass

All 49 are `skipped`, none failed. Every one is skipped for an **environment** reason, not a
correctness one, which is why they must be reported separately rather than counted either way:

| family | requirements | why skipped |
|---|---|---|
| REQ-LOC | 001, 002, 004, 005, 006, 008, 009, 012, 015, 016, 017, 018 | need the live PG engine |
| REQ-TIER | 005, 012, 013, 014, 017, 018, 028, 035, 040, 041, 042, 043, 047, 048, 049, 050, 053 | need the live database |
| REQ-ACT | 001, 002, 003, 005, 006, 009, 011, 012 | need the live database |
| REQ-INF | 103, 107, 109, 505, 520 | live database; 520 needs NumPyro |
| REQ-ASK | 003, 011 | need the live database |
| REQ-ONT | 001, 002 | need the live PG 17 engine |
| REQ-NFR | 003, 004 | need the live PG engine |
| REQ-NAR | 014 | needs the live database |

Full list with per-test outcomes: `--prefix REQ-LOC`, `--requirement REQ-LOC-005`, etc.

## The four disputed closure claims

### REQ-INF-520 — NumPyro: the dependency is not installed where the tests run

**Status: MAPPED. Not TESTS_PASSED.**

The requirement (`specs/04-reasoning/requirements.md:710`): *"The reasoning layer SHALL use
NumPyro as its sole probabilistic programming language."*

Three tests name it. Their actual outcomes in the audited run:

```
[ skipped]  tests.test_bayes_model::test_REQ_INF_520_numpyro_..._and_it_RUNS
[ skipped]  tests.test_bayes_model::test_REQ_INF_520_the_two_implementations_agree_...
[  passed]  tests.test_bayes_model::test_REQ_INF_520_the_numpyro_path_reports_through_the_SAME_reporting_layer
```

The two that execute NUTS skip. The one that passes asserts on source text:

```python
src = inspect.getsource(bayes_numpyro)
assert "bayes_model" in src
assert "summarise" not in src.replace("`summarise`", "")
```

That is a lint, not an execution. The old tool reported REQ-INF-520 as proven regardless,
because it never looked at any of the three.

**The load-bearing defect is in CI, not in the tests.**
`tests/test_bayes_model.py:236` says the executing test *"is not skipped in CI, where python is
3.12"*. That is **false**. `.github/workflows/tests.yml:28` installs:

```
pg8000, pytest, numpy, scipy, statsmodels, networkx, pyyaml, ofxtools
```

No `jax`, no `jaxlib`, no `numpyro`. `bayes_numpyro.available()` therefore returns `False` in
the `pytest` job, and both executing tests skip there exactly as they do locally. The
`local-sql` job (`tests.yml:67`) installs even less. NumPyro appears in **one** workflow —
`.github/workflows/analysis.yml:44` — which does not run the test suite.

So REQ-INF-520's executing evidence has never run in CI. The only place it has run is a local
venv recorded in a docstring and in ADR-0103, which the audit cannot cite because nothing
persisted from it.

### REQ-REC-016 — executing acceptance cases vs. formatting status labels

**Status: TESTS_PASSED at level 3, and no integration evidence.**

The requirement: *"Before release, the backend SHALL **execute acceptance cases** covering
multiple event families, contradictory and duplicated evidence, unknown presence, historical
corrections, model unavailability and inferred-input propagation, recording each as passed or
explicitly open…"*

What the named test (`tests/test_surface_contract.py:186`) actually does:

```python
cases = {f: "passed" for f in EVENT_FAMILIES_REQUIRED}
cases["model_unavailable"] = "open"
out = acceptance_report(cases)
assert out["aggregate_verdict"] is None
assert out["open"] == ("model_unavailable",)
```

The word `"passed"` is a **literal written by the test**. No acceptance case is executed. What
is verified is that `acceptance_report` rejects a dict missing a family key and returns
per-family labels rather than one verdict — a status-label formatter validating its input.

The requirement asks for seven executed scenarios. The test asks for seven dictionary keys.

**And `acceptance_report` has no caller.** `grep -rn acceptance_report --include=*.py` returns
its definition in `tools/engines/surface_contract.py:280` and its use in that one test. Nothing
in the backend calls it, so no acceptance report has ever been produced.

### REQ-REC-013 — downstream dependence handling vs. attaching metadata

**Status: TESTS_PASSED at level 3, and no integration evidence. Applicability UNKNOWN.**

The requirement: *"**Every analysis consuming inferred events** SHALL record their uncertainty
and source lineage and SHALL NOT treat those inputs as measured values or independent evidence
for the same claim that generated them."*

`inferred_input` (`tools/engines/surface_contract.py:239`) attaches
`treated_as_measured: False`, `independent: False`, and a `shared_lineage_groups` tuple. The
test (`tests/test_surface_contract.py:161`) passes three literal dicts and asserts those keys
come back. It is metadata attachment, and the metadata is correct.

What is **not** shown anywhere:

- that any analysis calls `inferred_input` — it has **zero callers** outside that test;
- that any downstream statistic de-weights, clusters or otherwise *acts on*
  `shared_lineage_groups`. The flag is attached; nothing reads it.

**The subject of the requirement does not yet exist.** `core.inferred_events` is read by
exactly one thing: `public.get_reconstruction` in `migrations/0055_get_reconstruction.sql`,
which is a retrieval function. No analysis — `forecast.py`, `recommend.py`, `confirm.py`,
`panel.py`, `ask` — consumes inferred events at all.

So REQ-REC-013 is currently **vacuous**: there are no analyses for it to govern. That is not
the same as satisfied and not the same as violated, and it must not be recorded as either.
Both `0054` and `0055` are also unapplied, per `docs/NEXT_SESSION.md` — not independently
verified here, because this audit issued no production query.

### Nutrition cascade — no runtime caller

**Status: REQ-NUT-001 is TESTS_PASSED at level 3, and there is no application path at all.**

REQ-NUT-001 declares a five-step cascade: (1) `food_aliases` exact match, (2) barcode lookup
against Open Food Facts, (3) USDA FDC Foundation/FNDDS, (4) USDA FDC Branded, (5) Open Food
Facts text search, (6) unresolved.

Two tests name REQ-NUT-001, both mine, both passing:

```
tests.test_nutrition_off::test_REQ_NUT_001_REQ_NUT_006_a_search_reads_one_page_and_never_bulk_imports
tests.test_nutrition_off::test_REQ_NUT_001_REQ_NUT_024_an_unknown_barcode_is_not_found_and_is_settled
```

Between them they cover one branch of step 2 and one of step 5, through an injected transport.
Against that:

- **Steps 1, 3 and 4 do not exist.** `food_aliases` appears in no migration and no code
  (`grep -rn food_aliases migrations/ tools/ lib/` → nothing), and there is no USDA parser.
- **There is no runtime caller.** `tools/resolve_nutrition.py` — the hourly job named in
  `docs/build/B12_nutrition.md` — does not exist. `resolve_item`, `resolve_drink`,
  `lookup_by_barcode` and `lookup_by_name` are called only from tests.
- **Migration 0050 is unapplied**, so `core.foods_cache`, `core.portions` and
  `config.egress_allowlist` do not exist in production. The Open Food Facts host is therefore
  not allowlisted at runtime, and every lookup would be refused by `lib/egress.get_json`.

**A concrete unsupported closure this produced.** `ops/features.json` F-003 — *"Transcript
resolves to food names only, no quantities invented"* (REQ-NUT-001) — is now marked
`"status": "passing"` with

```
"proving_test": "tests.test_nutrition_off::test_REQ_NUT_001_REQ_NUT_024_an_unknown_barcode_is_not_found_and_is_settled"
```

That test asserts that an unknown barcode raises `OffNotFound`. It says nothing about
transcripts, nothing about quantities, and nothing about the cascade. One named passing test
authored in a worktree flipped a product-level feature claim, through
`tools/update_features.py`, for a requirement that is roughly 40% unimplemented and has no
caller. `update_features.py` behaved exactly as designed; the design trusts the test **name**
to describe the test's subject, and a name is not an assertion.

## Other findings

**`ops/features.json` covers 15 of 685 requirements** (5 passing, 10 failing). It is a
product-feature ledger, not a requirement ledger, and is not a substitute for one.

**F-006 / REQ-ONT-001** is `passing` on `test_REQ_ONT_001_kind_taxonomy_enforced`, which
**skipped** in the audited run (it needs the live PG engine). It presumably passed in the CI
`pytest` job, but nothing persisted from that job, so the claim cannot be re-derived from any
artifact. This is the case the two-file merge exists for.

**Zero orphans.** All 685 IDs named by tests are declared in a spec. The old tool agreed, and
this is the one number that survives unchanged.

**A spurious mapping removed, and it is the over-count in miniature.** The old
`tests/test_audit_requirements.py` contained
`test_REQ_NFR_005_a_proven_requirement_names_the_test_that_proves_it` — a test that the *audit
tool* could point at its own evidence. REQ-NFR-005 is about something else entirely: *"The
freshness checker SHALL derive each registered metric's staleness limit from the registry"*
(`specs/06-nfr/requirements.md:70`). A test of the reporting tool was counted as coverage of the
freshness checker, purely because the ID appeared in its name. The rewrite drops that name;
REQ-NFR-005 keeps its two genuine tests in `tests/test_freshness.py` and
`tests/test_atom_panel.py`, so real coverage is unchanged and one false claim is gone. This is
the whole failure mode at the smallest possible scale, and it was inside the audit's own tests.

**A defect found in this tool's own predecessor pattern.** The regex `^\s*def\s+(test_\w+)`
matches `def` lines **inside** docstrings and triple-quoted fixture strings, because such lines
genuinely start with `def`. The first version of this rewrite reported its own fixture IDs
(`REQ-XYZ-001`…) as real mapped tests and then as orphans of the real specs. Mapping is now
done by `ast.parse`, walking module-level and class-level `test_*` definitions only — which is
also what pytest collects. A tool that miscounts its own test suite cannot be trusted to count
anything else.

## Workflow changes needed (main session owns these files)

None of the below are edited here.

1. **`.github/workflows/tests.yml:28`** — add the probabilistic stack to the `pytest` job, or
   REQ-INF-520's executing tests never run in CI:
   ```
   'jax>=0.4.30,<0.5' 'jaxlib>=0.4.30,<0.5' 'numpyro>=0.19,<0.21'
   ```
   These pins are already proven in `analysis.yml:44` on python 3.12, so this adds no new
   dependency decision — it installs an approved one where the tests are.

2. **Persist a JUnit report from both jobs.** Level 3 cannot be audited from a report that is
   written to `/tmp` and discarded.
   - `pytest` job: `tools/update_features.py` already writes `/tmp/features_junit.xml`; upload
     it with `actions/upload-artifact` (`if: always()`).
   - `local-sql` job: `tools/test_local_sql.py` runs pytest with no `--junitxml` at all, so
     that job currently produces **no machine-readable result**. Add one and upload it.

3. **`tools/test_local_sql.py`** — its `TESTS` tuple is a hardcoded `argparse` `choices` list,
   so a new SQL-backed test file cannot be run through the sanctioned harness without editing
   it. `tests/test_nutrition_off.py` and `tests/test_audit_requirements.py` are not in it.

4. **Create `ops/requirement_evidence.json`** so levels 4-6 can ever be non-zero. Schema, one
   object per requirement, `ref` and `how` both mandatory:
   ```json
   {
     "REQ-NUT-001": {
       "integration": {"ref": "tools/resolve_nutrition.py::main",
                       "verified_at": "2026-09-10",
                       "how": "job run against a disposable spine; 12 nutrient atoms written"},
       "deployment":  {"ref": "migration 0050 applied",
                       "verified_at": "2026-09-11",
                       "how": "core.foods_cache present in production"},
       "observation": {"ref": "ops.runs resolve_nutrition 2026-09-11",
                       "how": "38 real food captures resolved, 4 unresolved_items rows"}
     }
   }
   ```
   The tool **refuses** an entry missing either `ref` or `how`: a reference with no statement of
   what was verified would still print as INTEGRATED, which is the failure being corrected
   re-entering through the file meant to fix it. Nothing in the tool ever writes this file.

5. **Correct two documents** (both main-session-owned, untouched here):
   - `docs/NEXT_SESSION.md:3` — the heading *"EVERY REQUIREMENT IS PROVEN: 685 of 685"* and the
     table row *"requirements proven | 685 / 685"*. The supportable statement is: 685 declared,
     685 with a named test, 636 whose tests all passed in a named run, 0 with integration,
     deployment or observation evidence on file.
   - `docs/BACKEND_COMPLETION.md:16` — the sentence *"A requirement counts as PROVEN only when
     a test whose NAME carries its ID passes"* describes behaviour the old tool did not have:
     it checked the name and never the pass.

## Scope of this audit

**This audits the reporting, not the backend.** What is established is that the ladder is
computed from the specs, an AST parse of `tests/`, and named result files, and that it cannot be
talked upward — 27 tests lock that. The four disputed cases above were each read by hand.

The other 681 requirements have **not** been individually reviewed for whether their passing
tests actually cover their sentences. That review is the remaining work, and levels 4-6 sitting
at zero is the honest summary of it: nobody has yet written down what is integrated, and until
someone does, this report will keep saying so.
