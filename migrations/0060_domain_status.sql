-- 0060_domain_status.sql — what each domain can actually say, and why not when it cannot.
-- REQ-ASK-021, REQ-TIER-018, RULE-06, RULE-07, RULE-18; ADR-0095. Depends on 0056.
--
-- WHY THIS EXISTS BEFORE THE WEEKLY REPORT. Every per-domain surface iterates
-- `config.domains.hero_metric`. Eight of the fourteen name a measure `core.metric_registry`
-- does not contain, and two of those — `hrv_sdnn`, `rhr` — are the same measures the atom lane
-- holds as `hrv_sdnn_ms` and `resting_hr` (OQ-60). A report that iterated domains today would
-- print "no data" for recovery and vitals while 1,333 observations sat in `core.atoms` under
-- the other spelling.
--
-- "No data" and "no data UNDER THIS NAME" are different statements and only one of them is
-- true. This function distinguishes them, so the gap is a queryable fact rather than a silent
-- zero that reads as an absence of life. RULE-18: an honest unresolved state is a result.
--
-- It deliberately does NOT map a name onto a similar one. A string-similarity search proposes
-- `sleep_awake_min` for `away_min` — time AWAKE IN BED offered as time AWAY FROM HOME. The
-- tooling cannot tell a rename from a coincidence, which is why CLAUDE.md reserves data
-- definitions for Joe.

CREATE OR REPLACE FUNCTION analysis.f_domain_status(p_as_of date,
                                                    p_known_at timestamptz DEFAULT now())
RETURNS TABLE (domain_key text, display_name text, hero_metric text,
               resolution text, last_day date, days_with_data integer,
               latest_value numeric, band_lo numeric, band_hi numeric,
               band_position text, capture_action text, value_is_stale boolean)
LANGUAGE sql STABLE AS $fn$
WITH d AS (
    SELECT dm.domain_key, dm.display_name, dm.hero_metric, dm.capture_action
      FROM config.domains dm WHERE dm.enabled
), panel AS (
    -- count(DISTINCT day), not count(*): the column is DAYS with data, and a metric served by
    -- more than one lane would have counted the same day twice (review finding 1). Counting
    -- rows where the name says days is the shape of that error, not just its consequence.
    SELECT p.metric, max(p.day) AS last_day, count(DISTINCT p.day)::int AS days_with_data
      FROM analysis.f_daily_panel(p_as_of, p_known_at) p GROUP BY p.metric
), latest AS (
    SELECT DISTINCT ON (p.metric) p.metric, p.value, p.day
      FROM analysis.f_daily_panel(p_as_of, p_known_at) p ORDER BY p.metric, p.day DESC
)
SELECT d.domain_key, d.display_name, d.hero_metric,
       CASE
         WHEN d.hero_metric IS NULL                       THEN 'no_hero_metric'
         -- The distinction that matters (OQ-60): a name the registry does not know is not the
         -- same as a measure with no observations, and calling both "no data" hides a rename.
         WHEN r.metric_key IS NULL AND pn.metric IS NOT NULL THEN 'unregistered_but_has_data'
         WHEN r.metric_key IS NULL                        THEN 'unregistered_and_unbuilt'
         WHEN pn.metric IS NULL                           THEN 'registered_no_observations'
         ELSE 'resolved'
       END,
       pn.last_day, coalesce(pn.days_with_data, 0), l.value, b.band_lo, b.band_hi,
       -- RULE-07: three-valued. Outside a band is a fact; no band is not "inside".
       CASE WHEN b.band_lo IS NULL OR l.value IS NULL THEN NULL
            WHEN l.value < b.band_lo THEN 'below'
            WHEN l.value > b.band_hi THEN 'above'
            ELSE 'in_band' END,
       d.capture_action,
       CASE WHEN pn.last_day IS NULL OR r.max_staleness_days IS NULL THEN NULL
            ELSE (p_as_of - pn.last_day) > r.max_staleness_days END
  FROM d
  LEFT JOIN __CORE__.metric_registry r ON r.metric_key = d.hero_metric
  LEFT JOIN panel  pn ON pn.metric = d.hero_metric
  LEFT JOIN latest l  ON l.metric  = d.hero_metric
  LEFT JOIN LATERAL (
      -- The band is bounded on BOTH clocks. `analysis.baselines.computed_at` exists, so a
      -- replay must not be given a band recomputed after the knowledge time — otherwise
      -- `band_position` reports where a value sits inside a band that did not exist when the
      -- question was asked (INV-4). This was accepted as a parameter and never applied.
      SELECT bl.band_lo, bl.band_hi FROM analysis.baselines bl
       WHERE bl.metric = d.hero_metric AND bl.day <= p_as_of
         AND bl.computed_at <= p_known_at
       ORDER BY bl.day DESC, bl.computed_at DESC LIMIT 1) b ON true
 ORDER BY d.domain_key
$fn$;
COMMENT ON FUNCTION analysis.f_domain_status(date, timestamptz) IS
  'REQ-ASK-021 / RULE-18. Per-domain readiness. `unregistered_but_has_data` is the OQ-60 case: '
  'the hero metric names something the registry does not know while rows exist under that name '
  '— a rename nobody has confirmed, never to be guessed at query time.';
REVOKE ALL ON FUNCTION analysis.f_domain_status(date, timestamptz) FROM anon, authenticated;
