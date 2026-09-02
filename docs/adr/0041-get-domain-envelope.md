# ADR-0041: `get_domain` is the Universal Domain Module envelope

## Status
Accepted

## Date
2026-09-02

## Decision
`public.get_domain(p_domain, p_window)` (migration 0035) returns everything the SOURCES
page renders for one domain in nine modules — hero, why, history, rhythm, notables,
driven_by / drives, forecast, entities, capture — keyed off `config.domains` (ADR-0040).
**Module presence is data-driven:** a module is absent when its source has no rows
(`jsonb_strip_nulls`), never `0`, `[]` or a sample (REQ-INF-505). **The opening sentence
is composed from a closed set of seven templates in SQL** (RULE-15: no model needed;
RULE-14: no client arithmetic). **Rhythm always uses the trailing 365 days; history uses
`p_window`** (`7d 30d 90d 1y all`, default 90d) — the window is a fixed parameter the
client picks from a closed list, never a model choice (RULE-13). **Changepoints are not
computed in v1.** An unknown or disabled key returns the REQ-ASK-003 refusal string
verbatim plus up to three trigram-nearest tracked keys, and nothing else.

Tier vocabulary on this envelope is exactly `EXPLORATORY WATCHING CONFIRMED REFUTED
INSUFFICIENT`; claims (modules 6a/6b) are text and labels only (REQ-TIER-050) and come
only from `analysis.contrasts` joined to `core.hypothesis_register` (REQ-TIER-053).

## The two DISCOVER-dependent lines, as actually written
- **`__METRIC_MATCH__`** (forecast track record ↔ metric). `core.predictions` holds zero
  `forecast-%` rows today and `tools/engines/forecast.py` writes them with a NULL
  `hypothesis_id` and `claim_text = metric || ' on ' || day_target || ' within [lo, hi]'`.
  So the match is on the claim text's leading token:
  `pr.claim_text LIKE hm.metric || ' on %'`.
- **`__EXERCISE_EXPR__`** (module 8, `atoms_workout_exercise`). Zero workout atoms exist
  today; `tools/extract_checkins.py` (OQ-33 ruling (a)) writes **one atom per attribute**
  (`strength_load_lb`, `strength_reps`, `strength_rpe`) per set, all sharing the set's
  `raw_capture_id`, with the exercise name **verbatim in `evidence_span`**. So:
  `evidence_span AS name, count(DISTINCT raw_capture_id) AS n` — B2's `count(*)` would
  have counted each set three times.

## Live-schema findings, fixed minimally (README rule 12)
1. **`analysis.forecasts` did not exist on the live database.** Migration 0032 declares
   it, `get_today()` and the nightly `analysis_refresh` read it, and both were failing
   live with `42P01` (two `error` rows in `ops.runs` on 2026-09-02). 0035 re-declares the
   table verbatim from 0032 with `IF NOT EXISTS` — forward-only, idempotent, and it
   repairs `get_today()` and the nightly job as a side effect. Why it was missing is not
   established (0032 was applied with `--only`; nothing in the repo drops it) — recorded
   as OQ-42.
2. **`count()` over zero rows is 0, not NULL** (same defect as ADR-0040 §2): B2 keyed
   `density` on `cov_days IS NULL` and emitted `days_with_data` / `days_in_window`
   unconditionally. Now keyed on `cov_last IS NULL` / `hm.metric IS NULL`, so an empty
   domain emits neither.
3. **`pg_trgm` was not installed.** Created in schema `extensions`; `similarity()` is
   called schema-qualified because the function runs with `search_path = ''`.

## Known-wrong-but-unreachable
`_domain_claims` renders every tier with the 0031 sentence template, which ends
"exploratory and unverified" — wrong for a CONFIRMED row. There are zero non-CANDIDATE
rows today (34 CANDIDATE). Tier-specific templates are OQ-41; not built now.

## Not built in v1
Changepoints; hour-of-day rhythm; per-domain coverage thresholds (OQ-40).
