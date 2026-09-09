# docs/build — executable build orders for Claude Code

*Written 2026-09-02 from `docs/THE_FILE.md` Part III. One file = one Claude Code
session = one migration (or one tool). Nothing in here is a design discussion; every
file is a checklist with the exact SQL, the exact envelope, the exact test names, and
the exact commands whose output proves it done. Where the SQL depends on something only
the live database can tell you, the file says DISCOVER and gives the query.*

## How Joe uses this

Open a terminal in `~/PERSONAL_OS_V2`, start `claude`, and paste **one line**:

```
Read docs/build/README.md, then execute docs/build/B1_domains_config.md exactly as written. Do not redesign anything in it. Where it says DISCOVER, run the query and paste the output into ops/PROGRESS.md before continuing. Where it says DECISION, stop and ask me. Finish with the Definition of Done from docs/CONSTITUTION.md, including WHAT I DID NOT DO.
```

Next session, the same line with the next file. `/session-end` at the end of each.

## The order (do not reorder)

| # | File | Builds | Migration | Sessions |
|---|---|---|---|---|
| B0 | `B0_update_features.md` | `tools/update_features.py` — `ops/features.json` finally reflects reality | — | 0.5 |
| B1 | `B1_domains_config.md` | `config.domains` + `config.domain_metrics` + `get_domains()` — the SOURCES index | 0034 | 0.5 |
| B2 | `B2_get_domain.md` | `get_domain(p_domain, p_window)` — the nine-module envelope | 0035 | 1–2 |
| B3 | `B3_search_record.md` | `search_record(p_q, p_limit)` — full-text over the record | 0036 | 0.5 |
| B4 | `B4_get_entity.md` | `get_entity(p_type, p_key)` — merchants, categories, sites, channels, exercises | 0037 | 0.5 |
| B5 | `B5_movements.md` | restricted location store, ingress, in-DB place resolution, `get_movements` / `get_place` / `get_places` | 0038–0040 | 2–3 |
| B6 | `B6_get_findings.md` | `get_findings()` — the WATCHING / CONFIRMED / REFUTED / INSUFFICIENT lists | 0041 | 0.5 |
| B7 | `B7_resolve_watches.md` | the nightly resolver that turns a 30-day watch into PROMOTED / REFUTED | 0042–0044 | done |
| B8 | `B8_consistency_and_rulings.md` | OQ-44 rulings; surfaces agree on `watching`; pytest in CI; v2 rule template | 0045 | 0.5 |
| B9 | `B9_confirmation_gate.md` | REQ-TIER-012/013 to spec: spec curve + tree FDR at promotion; DAG, HAC, E-value, negative controls, DoWhy at confirmation | 0046 | 2 |
| B10 | `B10_recommendations.md` | RULE-25 as built: `core.recommendations`, standing orders, the daily instruction, auto-demotion; OQ-30 ruled; REQ-ACT numbered | 0047 | 1 |
| B11 | `B11_ask.md` | REQ-ASK: operation registry, computations, deterministic parser, templates, Workers AI planner | 0048–0049 | 2 |
| B12 | `B12_nutrition.md` | REQ-NUT §D/§E: `lib/egress.py`, USDA + OFF, cache-first, interval nutrients, drinks→ethanol | 0050 | 2 |
| B13 | `B13_importers.md` | Apple Health / bank CSV-QFX / Takeout → captures; finance §A.1/A.4 | 0051 | 2 |
| B14 | `B14_entities_and_links.md` | finance §B merchant cascade, REQ-ONT entity types, the link object; meal↔charge↔place | 0052 | 1 |
| B15 | `B15_period_and_compare.md` | `get_period(week)`, `get_compare(metric, condition)` | 0053 | 1 |
| B16 | `B16_voice_photo_capture.md` | REQ-CAP §B/§C/§F: Storage + Workers AI transcription, extractive extraction with verifier, neuron budget, prompting | 0054 | 2 |
| B17 | `B17_finance.md` | finance §A.2 Gmail (Apps Script), §C recurrence/necessity, §G income/balances/budgets/forecast/reconciliation, §E restraint | 0055–0057 | 3 |
| B18 | `B18_workouts.md` | REQ-WKT: exercise entity, e1RM interval, volume, ACWR, rest-day presence; `analysis.derived_measures` | 0058 | 1 |
| B19 | `B19_inference_remainder.md` | REQ-INF: regimes (dynamax HMM), Bayesian layer (NumPyro), chains, calibration ledger, on-demand scans, micro-trials | 0059–0061 | 3 |
| B20 | `B20_narration_and_ontology.md` | REQ-NAR render pipeline + vocabulary linter (Python and SQL, one source); REQ-ONT closed taxonomies | 0062 | 1 |
| B21 | `B21_body_sleep_context_specs.md` | REQ-BOD / REQ-SLP / REQ-CTX authored and built (Kalman weight, TDEE, sleep debt/regularity, content diet, weather) | 0063 | 2 |
| B22 | `B22_retire_old_stack.md` | cutover, old jobs unscheduled, tables archived and dropped (Joe's per-table yes), legacy atoms loaded, storage reclaimed | 0064 | 1 |
| B23 | `B23_done_instrument.md` | requirement coverage ledger (proven / deferred / open), Gherkin runner, DEFERRED.md, the final audit; **done = open 0** | 0065 | 1 |
| L0 | `L0_lovable_round0.md` | Lovable Round 0: kill + rewire + seven-section shell | — | after B1 |
| L1 | `L1_lovable_round1.md` | Round 1: the SOURCES page on `get_domain` | — | after B2 |
| L2 | `L2_lovable_round2.md` | Round 2: the index finished + the entity page | — | after B4 |
| L3 | `L3_lovable_round3.md` | Round 3: FINDINGS lifecycle lists + RELIABILITY audit page | — | after B6 |
| L4 | `L4_lovable_round4.md` | Round 4: ASSESSMENT complete + RECORD search | — | after B3 |
| L5 | `L5_lovable_round5.md` | Round 5: MOVEMENTS (day, places, place page) | — | after B5 |
| L6 | `L6_lovable_round6.md` | Round 6: THE DESK capture/correct forms | — | after L5 |
| L7 | `L7_lovable_round7.md` | Round 7: polish; skippable if credits are short | — | after L6 |
| L8 | `L8_lovable_round8.md` | Round 8: Ask, recommendations, trials, weekly, compare, the new modules, the honesty number | — | after B23 |
| — | `RUNBOOK_NO_CLAUDE.md` | How the system runs, and is kept running, with no model at all | — | read once |

**L0 can be pasted as soon as B1 is live.** Everything else it reads is already live
(`get_today` `get_timeline` `get_day` `get_patterns` `register_watch` `get_trust`
`get_insights_guarded` `ingest_capture`). Each later round names its precondition.
The Lovable rounds need no Claude at all — they can be pasted after the subscription
ends, one per credit window.

**Definition of done for the backend (ADR-0081, built by B23):** every requirement ID
in `specs/` is proven by a named passing test or deferred by a cited ruling, and the
nightly ledger `docs/REQ_COVERAGE.md` reports `open = 0`. Until B23 exists, "done" is
"B8–B23 committed with their Definitions of Done"; after it, the number decides.

**The chained paste for B8 onward:** see the bottom of this file.

## Rules that apply to every file here

1. **Owner-lock pattern is copied, not reinvented.** Every read RPC begins with the exact
   preamble in `migrations/0032_forecast_today_trust.sql` (`LANGUAGE plpgsql STABLE
   SECURITY DEFINER SET search_path = ''`, the `auth.jwt()->>'email'` check,
   `jsonb_strip_nulls`) and ends with the `REVOKE/REVOKE/GRANT` lines. `anon` never
   gets EXECUTE on a read RPC.
2. **Schema tokens.** Inside a migration, core tables are `__CORE__.x` and ops tables
   `__OPS__.x` (the runner substitutes). `analysis.*`, `public.*`, `config.*`,
   `restricted.*` are written literally.
3. **Migration numbering** continues from `0033` (there is no `0028`; leave it).
4. **Dry run first, always:**
   `python3 tools/run_migration.py --core core_dryrun --ops ops_dryrun` then
   `python3 tools/run_migration.py --core core --ops ops --commit`.
5. **Tests** go in `tests/` and are named exactly as each file lists them (the REQ/ADR
   ID is in the name — DoD item 1/3). They connect with `lib.db.connect()`, run inside
   one transaction, set the owner JWT with
   `select set_config('request.jwt.claims','{"email":"joseph.delany21@gmail.com"}',true)`
   (see `tools/_probe_state.py` lines 46–48), and **roll back**. They read live data;
   they never leave a row behind.
6. **No coordinate literal, no home identifier, ever, in any file in git** (REQ-LOC-005).
7. **The envelope is the contract.** Fields are added, never renamed. A field that cannot
   be populated is **absent** (`jsonb_strip_nulls`), never `0`, `""`, or a sample (REQ-INF-505).
8. **Every numeral has a trace** (INV-3, REQ-ASK-009/011). No trace, no numeral.
9. **`search_path = ''` means every function call is schema-qualified** — including
   extension functions (`extensions.similarity`, `extensions.gin_trgm_ops`). Check with
   `SELECT extnamespace::regnamespace FROM pg_extension WHERE extname='pg_trgm'`.
10. **Do not touch `ops/features.json` by hand** (write-locked); B0 builds the only path
    that may move an entry, and every later session runs it.
11. Commit message: `B<N>: <what> (<REQ-IDs>)`, ending with the `Co-Authored-By` line
    this repo already uses.
12. If anything in a file is wrong against the live schema, **stop and say what**
    (push_back stance in CLAUDE.md). Do not silently substitute.

## The chained paste (B8 → B23, no stops)

```
Read docs/build/README.md and ops/PROGRESS.md. Execute, in order and without stopping between them, docs/build/B8_consistency_and_rulings.md through B23_done_instrument.md (B8, B9, B10, B11, B12, B13, B14, B15, B16, B17, B18, B19, B20, B21, B22, B23). Rules: quote the requirement IDs at the start of each file; run every DISCOVER and paste its output into ops/PROGRESS.md; the rulings written inside B8 and B10 are Joe's rulings — record them in the ADRs named and continue; at every other DECISION take the recommended option, record it, and continue. Where a step needs Joe (an API key, a login, a per-table "yes" in B22, a Shortcut installed), do everything up to that point, print exactly what Joe must do in one numbered list, mark the step HELD in PROGRESS, and continue with the next file — never block the chain. Commit after each file with the Definition of Done including WHAT I DID NOT DO; run python3 tools/update_features.py and python3 tools/validate_layout.py before every commit; push after every file. Never weaken a gate, test, or threshold to pass. If a file is wrong against the live schema or a library is unavailable on the runner, say exactly what, fix it minimally, and record it. If you run out of context, the next session continues from the first unfinished B-file per ops/PROGRESS.md and re-reads the HELD list.
```

Restart line: `Read docs/build/README.md and ops/PROGRESS.md; continue the B8→B23 chain from the first B-file not marked complete, same rules; re-read the HELD list first and finish any HELD step whose Joe-action is now done.`
