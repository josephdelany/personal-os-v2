# B23 — The "done" instrument: requirement coverage ledger, Gherkin runner, the final audit (migration 0065)

**What this is.** "Finished" must be a number nobody has to argue about. This build
makes it one: every one of the ~700 requirement IDs (after B21) is either **proven**
(a passing test carries its ID), **deferred** (a ruling in `docs/DEFERRED.md` with a
reason and an owner), or **open** — and the count of open is the distance to done,
published nightly on RELIABILITY. It also runs the 36+ Gherkin scenarios as tests and
performs the final adversarial audit. One session, then it runs forever.

**ADR:** ADR-0081 (definition of done for the backend: `open = 0`).

## `tools/req_coverage.py`
1. Parse every `specs/*/requirements.md` for `**REQ-[A-Z]+-\d{3}**` → the universe.
2. Parse the JUnit XML from the last full test run (B0's `update_features.py` already
   produces it; reuse) → the set of IDs named by **passing** tests (underscore form
   normalised).
3. Parse `docs/DEFERRED.md` (a table: `| REQ-ID | reason | ruling ref | revisit trigger |`)
   → the deferred set. A deferred ID must cite an ADR or a PROGRESS ruling; the script
   fails if the citation does not exist.
4. Emit `docs/REQ_COVERAGE.md` (per prefix: total / proven / deferred / open, and the
   list of open IDs) and write `analysis.req_coverage (as_of, prefix, total, proven,
   deferred, open)` (the RPC `get_trust` gains `requirements:{total, proven, deferred,
   open, by_prefix}` — RELIABILITY shows it as the file's own honesty number).
5. Exit non-zero if any ID is in *both* proven and deferred (a test exists for a deferred
   requirement means the deferral is stale — remove it).
Runs in `tests.yml` nightly after the suite; commits `docs/REQ_COVERAGE.md` if changed.

## Gherkin scenarios as tests
`tools/gherkin_to_tests.py` reads every `### Scenario N — title` block with its
Given/When/Then lines and generates a pytest stub `tests/scenarios/test_<file>_scenario_<n>.py`
if one does not exist (never overwrites), marked `xfail(strict=True, reason='unimplemented
scenario')` until a human implements it. The coverage ledger counts an xfail scenario
as **open**. Session task: implement every scenario the earlier B-files named (B12,
B16, B17 list theirs) and every one whose mechanism now exists; leave the rest xfail with
the reason.

## `docs/DEFERRED.md`
Seed it in this session with the honest deferrals and their reasons, each citing its
ADR: net worth/investments (ADR-0031); blinding for behavioural exposures (REQ-INF-204,
impossibility stated per 205); micronutrients beyond the seven; Plaid/aggregator
(RULE-28); API-tier bank adapters (§A.3 optional); anything else the audit finds. A
deferral is a decision, not a hiding place: the ADR must say why it is acceptable.

## The final audit (same session, after the ledger exists)
Run the adversarial reviewer (`.claude/agents/reviewer.md`) over: the constitution vs
the code (every RULE with tier TEST has a test; every LINT rule has a lint in
`validate_layout.py`; every REVIEW rule is named in this audit's checklist); the
envelope contracts vs the Lovable pastes (`docs/build/L*.md`) — every field a paste
binds exists in an RPC; the privacy boundary (no coordinate, no secret, no personal data
in git; `restricted` grants zero; every egress in `ops.egress_log`); the $0 constraint
(every external service named in ADRs is on a free tier with its limit stated in the
runbook). Findings pasted verbatim; each fixed or deferred with a ruling.

## Tests
```
test_ADR_0081_every_requirement_is_proven_deferred_or_open_exactly_once
test_ADR_0081_deferred_ids_cite_existing_adr
test_ADR_0081_coverage_ledger_written_and_in_get_trust
test_ADR_0081_gherkin_stubs_generated_for_every_scenario
test_CONSTITUTION_every_TEST_tier_rule_has_a_named_test
test_CONSTITUTION_every_LINT_tier_rule_has_a_lint
```

## Done when
`docs/REQ_COVERAGE.md` exists with the real numbers pasted (expect a large `open`
count the first night — that is the point; it must be true); `get_trust.requirements`
pasted; `DEFERRED.md` seeded; the audit findings and dispositions in PROGRESS;
ADR-0081; `RUNBOOK_NO_CLAUDE.md` §3 gains "open requirements rising" as a symptom.
From here, "finish the backend" means: work the open list to zero, prefix by prefix,
each session picking the highest-count prefix — a loop any model can run.
