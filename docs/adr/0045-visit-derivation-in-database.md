# ADR-0045: Visit derivation runs in-database; thresholds are provisional

## Status
Accepted

## Date
2026-09-02

## Decision
Visits are derived from `restricted.location_fixes` by `restricted.derive_visits(p_from)`
(migration 0039), a `SECURITY DEFINER` SQL function with no grants to any app role, called
hourly by the extraction workflow through `tools/run_sql_scalar.py` — a generic one-statement
runner whose statement text lives in the workflow, so **no Python file names a location
table and no Python process ever holds a coordinate** (REQ-LOC-011/012). The algorithm is
greedy stay detection: a fix joins the current stay if it is within `stay_radius_m` of the
running centroid and within `max_gap_min` of the previous fix; a closed stay is a visit iff
its dwell is at least `min_dwell_min`; fixes worse than `max_accuracy_m` are ignored. A
visit resolves to a registered place only if the centroid is inside that place's radius,
else `place_id` is NULL — **never the nearest guess** (REQ-LOC-009). **A gap is not a stay**:
nothing is imputed between fixes (REQ-LOC-015). Human assignments (`assign_place`, RULE-10)
survive every rebuild by time-range overlap.

The only object outside `restricted` that sees visits is the view `analysis.visits_public`:
visit id, day, arrive/depart, dwell minutes, fix count, resolved place id, label, kind,
`is_home`, code version — **no coordinate column** (REQ-LOC-012; a test asserts it). The
panel build reads that view only and writes three daily metrics — `away_min`, `home_min`,
`places_distinct` — as `src='visits'`, with no row for a day with no visit.

**Thresholds are provisional (OQ-37):** `stay_radius_m 100`, `min_dwell_min 10`,
`max_gap_min 45`, `max_accuracy_m 150`, read from `restricted.visit_params`, never hardcoded
in the function; every mobility figure carries `provisional: true` (B5.3).

## Decisions taken inside B5.2's envelope (recorded)
1. **Re-entrant stash.** B5's `CREATE TEMP TABLE _human` fails on a second call in one
   transaction (the tests rebuild twice); it is `IF NOT EXISTS` + `DELETE` instead.
2. **The `places` domain's config rows self-register.** B5.2 said seed `away_min` (hero),
   `home_min`, `places_distinct` into `config.domain_metrics` now. That would violate B1's
   ratified rule and test (ADR-0040: every seeded metric exists in `analysis.panel`) until the
   first Overland week produces a visit. So `config.domains.hero_metric` is set now (harmless:
   the hero is absent until the panel has it) and `config.ensure_places_metrics()` inserts the
   three rows idempotently, called at the end of every panel build, the first night the panel
   carries `away_min`. No test was weakened; no config row exists ahead of its data.
3. **The lint scans the working tree, not just tracked files**, so the tripwire fires before a
   commit. Two exact allowlisted occurrences: the workflow's `derive_visits(` call and B3's test
   asserting the token's absence. The lat/lon word test is word-bounded (`late`, `clone` do not
   trip it); prose (`.md`) is excluded from the coordinate-line lint.

## Not built
Inferred places (only human-registered ones resolve); transit/commute metrics; radius of
gyration and location entropy as registry metrics (REQ-LOC-010 is Phase 5's
`derived_measures`); legacy backfill (OQ-43); battery impact unmeasured.
