# ADR-0040: Domain configuration lives in a `config` schema, read through `get_domains()`

## Status
Accepted

## Date
2026-09-02

## Decision
Domain configuration — the fourteen SOURCES-index rows, their per-metric display
registry (unit, rounding, role), and the coverage vocabulary thresholds — lives in a
`config` schema: `config.domains`, `config.domain_metrics`,
`config.coverage_thresholds` (migration 0034). `THE_FILE.md`'s `domains.config` is
realised as `config.domains`. Config is **neither append-only nor derived**; it is
neither an atom nor a measure, so RULE-02/RULE-12 do not apply to it. It changes only
by migration. `anon` and `authenticated` have no access to the schema; the single read
path is `public.get_domains()`, owner-locked in the ADR-0036 pattern (`SECURITY DEFINER`,
`search_path=''`, JWT email check, `jsonb_strip_nulls`, `anon` revoked).

## Consequences
- One Universal Domain Module reads config; adding a domain is a seed row, not a screen.
- Every hero numeral carries its unit (REQ-NAR-014), its registered rounding
  (REQ-NAR-015), and a five-key trace into `analysis.panel` (INV-3).
- A domain with no panel data renders `coverage.status = never_captured` with **no**
  `hero`, no `days_with_data`, `density = none` — absence is absence (REQ-INF-505).
  The hero lookup is bounded at `as_of` (REQ-INF-109 / INV-4).

## Decisions taken inside B1's envelope (recorded, not silent)
1. **Seed honesty (B1 Step 0).** 12 `domain_metrics` rows were removed because their
   metric is absent from `analysis.panel` on 2026-09-02: `weight_lb`,
   `strength_volume`, `meals_logged`, `alcohol_standard_drinks`,
   `alcohol_ethanol_grams`, `screen_active_hours`, `checkin_night_mood`,
   `checkin_night_energy`, `checkin_night_stress`, `checkin_night_day_rating`,
   `checkin_morning_mood`, `checkin_morning_sleep_feel`. All 14 `config.domains` rows
   stay, with their `hero_metric` as written, so the index shows "never captured →
   capture action" until the panel gains the metric. No panel row was inserted (RULE-01).
   Consequence: `body`, `workouts`, `food`, `drink` have no `domain_metrics` at all today;
   `attention` and `mood` have `why` rows but no `hero` row.
2. **Empty-domain density fix.** B1's SQL keyed density and `days_with_data` on
   `s.days IS NULL`; `count(DISTINCT …)` over zero rows is `0`, so a never-captured
   domain would have rendered `density='weeks'` and `days_with_data=0`. Both are now
   keyed on `s.last_day IS NULL`. Minimal correction against live SQL semantics, per
   `docs/build/README.md` rule 12.
3. **Real apply used `--only 0034`.** README rule 4's literal real-apply command
   re-runs migrations 0001–0033 against live `core`/`ops`; those are forward-only and
   idempotent by construction but re-applying them for a config change is needless
   risk. The dry run applied the full chain (0001–0034) to a throwaway pair.
4. **Coverage thresholds are provisional.** `fresh ≤ 1 day`, `stale ≤ 30 days` have no
   evidence behind them (STANDING_RULINGS STOP-AND-ASK #8); recorded as OQ-40, to be set
   against real capture cadence.

## Alternatives considered
- Config as rows in `core.metric_registry`: rejected — the registry is the spine's
  measure vocabulary; display config (rounding, pillar, capture action) is not a
  measure and would pollute an append-only table with UI churn.
- Config in the front-end: rejected — RULE-14 (the render layer renders); a client that
  holds the domain list can invent a domain.
