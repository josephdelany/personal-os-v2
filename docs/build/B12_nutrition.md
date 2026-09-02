# B12 — Nutrition resolution: "Big Mac" → interval-valued nutrients (migration 0050)

**What this is.** `specs/02-capture-nutrition/requirements.md` §D (food resolution) and
§E (interval-valued nutrition) and §D.6 (drink → ethanol), implemented as written. Today
a food capture becomes a `consume` atom with a label and no nutrients; after this, every
resolvable item carries kcal / protein / carbs / fat / ethanol as **intervals** with the
resolution method that produced them. Two sessions. Closes F-003, F-004, F-005.

**Requirement IDs satisfied:** REQ-NUT-001..068 (every ID in §D and §E; quote the full
list from the spec at session start), REQ-INF-566/RULE-29 (egress logged), INV-3/5.
**ADRs:** ADR-0055 (the egress module and its log), ADR-0056 (nutrition resolver
architecture: cache-first, two sources, rate limits, intervals by method).

## Architecture decisions (do not redesign)
- **`lib/egress.py` is created here** — the single network path the constitution
  reserves (validate_layout already allows imports only there). API:
  `get_json(url, purpose, *, params=None, headers=None, timeout=20) -> dict` which writes
  an `ops.egress_log` row (`purpose`, `request_bytes`, `response_bytes`, `run_id`,
  `detail:{host, status, ms}`) for every call, refuses any URL whose host is not in
  `config.egress_allowlist` (seed: `api.nal.usda.gov`, `world.openfoodfacts.org`,
  `api.cloudflare.com`, `*.workers.dev`), and never logs a request body.
- **Sources:** USDA FoodData Central (free API key; Joe creates it at
  api.data.gov — Joe action; stored as GitHub secret `USDA_API_KEY` and in
  `settings.local.json` env) and Open Food Facts (no key; User-Agent per REQ-NUT-010).
  Rate limits exactly per REQ-NUT-009/011/012.
- **Cache-first** per §D.1: `core.foods_cache` (canonical_name, source, source_id,
  nutrients_per_100g jsonb, serving_g, brand, fetched_at, raw jsonb) and
  `core.portions` (Joe's personal portion table, §D.4; `source='joe'` rows outrank all).
- **Intervals by method** per §E.2: the width table from the spec, verbatim, as
  `config.nutrition_interval_widths (method, rel_width)`; `estimate_method` on the atom
  ∈ {`labelled`, `usda_branded`, `usda_foundation`, `off_product`, `portion_table`, `joe`}.
- **Never guess** (§D.5): an item with no cache hit and no source match stays a `consume`
  atom with `presence='observed'`, `value_point NULL`, and a row in
  `core.unresolved_items` that THE DESK lists for Joe to resolve (Scenario 4 → learning
  writes a `foods_cache` row with `source='joe'` and a portion row).
- **Drinks** (§D.6): ABV × volume → ethanol grams → standard drinks (14 g), using the
  seeded `alcohol_*` metric keys (ADR-0033); interval from the serving-size uncertainty.

## Migration `migrations/0050_nutrition.sql`
Tables above + `metric_registry` seeds for `kcal`, `protein_g`, `carbs_g`, `fat_g`,
`fiber_g`, `sugar_g`, `sodium_mg` (family 'nutrition', state_class 'total', unit each,
plausible ranges per meal) + panel additions in `panel.py`: daily sums of each with
**interval propagation** (§E.3: sum of lows, sum of points, sum of highs → three panel
metrics per nutrient: `kcal`, `kcal_lo`, `kcal_hi`) — the app shows the interval.

## Job — `tools/resolve_nutrition.py`, hourly after extraction
For each `consume` atom without nutrient children: tokenise the label (§D.1 order:
Joe's table → cache → USDA Branded (brand tokens from the evidence span, REQ-NUT-013) →
USDA Foundation/SR → OFF), resolve quantity (§D.4, counts of branded items §D.4a),
write nutrient atoms (kind `consume`, metric_key per nutrient, low/point/high, method,
`supersedes` NULL, `raw_capture_id` = the food capture's) and a `core.links` row
`(subject_atom=nutrient, predicate='derived_from', object_atom=food)`. Log every
egress. Respect the rate limits with a persisted token bucket in `ops.rate_limits`.

## Tests — one per Gherkin scenario in §H plus the rules
```
test_SCENARIO_1_big_mac_spoken_happy_path_resolves_usda_branded_with_interval
test_SCENARIO_3_homemade_meal_no_branded_match_stays_unresolved_never_guessed
test_SCENARIO_4_joe_resolves_item_and_cache_learns_with_source_joe
test_SCENARIO_11_four_photo_meals_daily_interval_sums
test_REQ_NUT_002_cache_hit_issues_no_network_request       (monkeypatch egress to raise)
test_REQ_NUT_009_011_012_rate_limits_and_backoff
test_REQ_NUT_050_branded_per_serving_multiplication
test_REQ_NUT_066_068_drink_abv_to_ethanol_grams_and_standard_drinks
test_ADR_0055_egress_refuses_non_allowlisted_host_and_logs_every_call
test_INV_5_measured_and_estimated_never_share_a_column
```
Network tests run against recorded fixtures (`tests/fixtures/usda_bigmac.json`, saved
from one real call with the key redacted); one live smoke test marked `@pytest.mark.live`
runs only when `USDA_API_KEY` is set.

## Done when
Migration; resolver in the hourly workflow; one real capture ("big mac, large coke")
resolved end-to-end with the atoms and the egress_log rows pasted; the panel shows
`kcal`, `kcal_lo`, `kcal_hi` for that day; tests; ADR-0055/0056; PROGRESS + WHAT I DID
NOT DO (vision/photo path is B16; micronutrients beyond the seven not resolved).
