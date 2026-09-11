# Checkpoint — 2026-09-11

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
session occurred.** R2 is implementable at this revision and is queued as the next unit.

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
