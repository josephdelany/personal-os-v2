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

## AWAITING ONE AUTHORIZATION (all verified against production in rolled-back transactions)

| # | What | Proven by |
|---|---|---|
| 0056 | the panel reads `core.atoms` | "Your Steps was typically 2206 count over the last 30 days (30 of 30 days)" |
| 0057 | entities, merchant patterns, aliases | 93 merchant entities from 440 descriptors |
| 0058 | `ask` separates its two clocks | the same question INSUFFICIENT at one as_of, 1262.14 usd at another |
| 0059 | `spend` answers about a merchant, and discloses its capture sources | Hannaford 1262.14 across 30 charges via `resolved_merchant` |
| 0060 | domain readiness says WHY a domain is empty | 2 resolved / 4 renamed / 4 unbuilt / 3 uncaptured / 1 no hero |
| 0061 | the strength measures and their specification | the catalogue and the engine cannot drift (tested) |
| — | transaction backfill | 1,052 legacy rows → 1,052 atoms, none dropped, none merged |
| — | resolver / link / category population | 616 `paid_to` links, 88 category rules |

The migration chain applies clean from empty at **61 files**.

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

**B19 cross-lens discovery.** The last unstarted M5 unit. B9 already built the promotion and
confirmation gates (migrations 0044/0046); B19 is the registry-driven exploration that feeds
them.

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

## VERIFICATION AT THIS REVISION

361 local SQL tests under `America/New_York` and `UTC`; 104 pure-Python tests;
`validate_layout` 42/42; migration chain clean at 58; last full production suite
220 passed / 248 skipped / 1 failed, that failure fixed in `c38a6da`.

## FINDINGS THAT CHANGE WHAT THE NUMBERS MEAN

- **Both devices count the whole day.** Summing steps across them doubles them (measured, 1.98x).
- **The Watch stopped 2026-08-21**, in five stages. The phone never did.
- **The bank CSV export stopped 2026-05-13.** `chase_email` carries a third of the transactions
  and a seventh of the value, with 38 empty days between them.
- **94% of inbound money is internal transfer.** True merchant spending is $23,508, not the
  $32,105 of gross outflow.
- **Legacy `sleep_deep_min` is in HOURS** despite the `_min` suffix. Lanes are never blended.
- **A nap and a night share a subject day.** One night's 352-minute gap pushed sleep regularity
  from 87 to 208 minutes until sessions were split on the importer's own gap constant.

## DO NOT REPEAT

- "Capture stopped" is wrong. The **Watch** stopped; the phone did not.
- The five sleep concepts are not interchangeable and are never summed blind.
- Legacy `sleep_deep_min` is in HOURS despite the `_min` suffix. Lanes are never blended.
- Both devices count the whole day: summing steps across them doubles them (measured, 1.98x).
- A question's date is not its knowledge horizon. Two clocks, two parameters.
