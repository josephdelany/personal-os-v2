# Backend and frontend build catalogue

[EXECUTION_PLAN](../EXECUTION_PLAN.md) owns dependency order, acceptance and release.
[BACKEND_ARCHITECTURE](../BACKEND_ARCHITECTURE.md) owns component boundaries.
Use the individual briefs below for implementation detail; check the current schema,
requirements and accepted ADRs before copying SQL. Historical migration allocations
and session estimates are not current reservations or delivery forecasts.

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
| B14R | `B14R_reconstruction.md` | Historical coverage and evidence reconstruction, REQ-REC-001..016 | allocated at implementation | acceptance-driven |
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

## Applying a brief

1. Read the active checkpoint and relevant requirements/ADRs. State the bounded
   outcome and acceptance cases before implementation.
2. Inspect the actual schema and deployed migration state. Preserve the existing
   owner-lock, schema qualification and grants patterns; never copy a stale signature.
3. Coordinate migration filenames with the integration owner; dry-run before any
   authorized production apply. A build brief does not grant production permission.
4. Exercise full behavior, negative cases, missingness and provenance through the
   public contract. Fixtures use disposable schemas and rollback; never real tables.
5. Run the checks appropriate to the unit and close it under the constitution's
   Definition of Done. The sanctioned writer alone updates the feature ledger.
6. Keep response fields compatible: add rather than silently rename. Missing values
   remain absent and each number retains its trace, unit and evidence lane.

Frontend briefs are retained for API contract planning. Execute L0-L8 only after the
backend release decision. Enabling exploratory output still requires the proven tier
label surface. The full pre-cleanup catalogue and paste instructions are retained in
`docs/history/2026-09-09-instruction-cleanup/docs/build/README.md` for audit only.
