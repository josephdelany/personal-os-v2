# Checkpoint — 2026-09-09 (late)

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
B12 is explicitly **not** complete: the USDA legs and the five-step cascade are unwritten.
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

**Still unstarted: B19.1** (§G.2 Bayesian effect layer, §G.3 regimes). ADR-0103 measured its
cost: only `jax`+`jaxlib`+`numpyro`+`dynamax` are new, `jaxlib` is 88 MB of the 92, all are
BSD/Apache with no service and no runtime network call. It fits the minutes budget even if the
repo goes private. **The finding that matters there is not jax** — see below.

**B15 period/compare remains blocked on OQ-60's shape, not on its schedule.** Eight of fourteen
domain hero metrics do not resolve against the registry, and two (`hrv_sdnn`, `rhr`) are the
same measures the atom lane holds as `hrv_sdnn_ms` and `resting_hr`. A weekly report iterating
domains today would say "no data" for recovery and vitals while 1,333 observations sit in
`core.atoms`. Mapping them is a measurement definition and is Joe's (CLAUDE.md).

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
| — | **mark at least one metric `role='lever'`** | any micro-trial at all. The column defaults to `context` and nothing has been classified; defaulting it for Joe is what REQ-INF-565 forbids |
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
