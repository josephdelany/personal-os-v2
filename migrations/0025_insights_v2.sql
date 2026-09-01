-- 0025_insights_v2.sql — insight density (ADR-0038 v2)
--
-- v1 was 23 lifetime aggregates. v2 adds, all still deterministic DESCRIPTIVE:
--   auto:    a full stat block (n, median, p10, p90, min, max, last-30d median)
--            for EVERY signal stream with n>=20 — ~223 streams -> ~1,300 facts
--   rhythms: per-weekday medians for headline metrics, best/worst weekday named
--   deltas:  last-30d vs all-time medians, disclosed as descriptive comparison
--   lists:   top websites / merchants / categories / YouTube channels by count
-- Same guard path: get_insights_guarded (0024) wraps this; owner-only.

CREATE OR REPLACE FUNCTION public.get_insights()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $fn$
WITH
auto AS (
  SELECT source, metric, count(*) AS n,
         round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric,2) AS median,
         round(percentile_cont(0.1) WITHIN GROUP (ORDER BY value)::numeric,2) AS p10,
         round(percentile_cont(0.9) WITHIN GROUP (ORDER BY value)::numeric,2) AS p90,
         round(min(value)::numeric,2) AS min, round(max(value)::numeric,2) AS max,
         round((percentile_cont(0.5) WITHIN GROUP (ORDER BY value)
                FILTER (WHERE ts > now() - interval '30 days'))::numeric,2) AS last30_median
    FROM public.signals
   WHERE value IS NOT NULL
   GROUP BY source, metric
  HAVING count(*) >= 20
),
dow AS (
  SELECT metric_label, dow_name, med,
         rank() OVER (PARTITION BY metric_label ORDER BY med DESC) AS rank_best
  FROM (
    SELECT metric_label, to_char(ts,'Day') AS dow_name,
           round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric,0) AS med
    FROM (
      SELECT CASE WHEN source='apple_sleep' THEN 'sleep (min)'
                  WHEN metric='steps' THEN 'steps'
                  ELSE 'screen binge (min)' END AS metric_label, ts, value
        FROM public.signals
       WHERE (source='apple_sleep' AND metric='asleep_min' AND value>0)
          OR (source IN ('health_history','apple_watch') AND metric='steps' AND value>0)
          OR (source='attention' AND metric='binge_minutes' AND value>=0)
    ) base
    GROUP BY metric_label, to_char(ts,'Day'), extract(dow FROM ts)
  ) agg
),
lists AS (
  SELECT jsonb_build_object(
    'top_sites', (SELECT jsonb_agg(jsonb_build_object('site',d,'visits',c) ORDER BY c DESC)
        FROM (SELECT payload->>'domain' d, count(*) c FROM public.events
               WHERE kind='chrome_visit' AND coalesce(payload->>'domain','') NOT LIKE 'localhost%' AND payload->>'domain' <> '' GROUP BY 1 ORDER BY 2 DESC LIMIT 15) t),
    'top_channels', (SELECT jsonb_agg(jsonb_build_object('channel',ch,'videos',c) ORDER BY c DESC)
        FROM (SELECT payload->>'channel' ch, count(*) c FROM public.events
               WHERE kind='youtube_watch' AND payload->>'channel' IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC LIMIT 15) t),
    'top_merchants', (SELECT jsonb_agg(jsonb_build_object('merchant',m,'txns',c,'total',s) ORDER BY c DESC)
        FROM (SELECT merchant m, count(*) c, round(sum(abs(amount))::numeric,0) s
                FROM public.transactions GROUP BY 1 ORDER BY 2 DESC LIMIT 15) t),
    'top_categories', (SELECT jsonb_agg(jsonb_build_object('category',cat,'txns',c,'total',s) ORDER BY s DESC)
        FROM (SELECT category cat, count(*) c, round(sum(abs(amount))::numeric,0) s
                FROM public.transactions WHERE category IS NOT NULL
               GROUP BY 1 ORDER BY 3 DESC LIMIT 12) t)
  ) AS l
)
SELECT jsonb_build_object(
  'tier','DESCRIPTIVE',
  'disclaimer','Facts about the recorded data — deterministic queries, no causal claim, no judgment. last30 vs all-time is a descriptive comparison, not a trend claim.',
  'computed_at', now(),
  'rhythms', (SELECT jsonb_agg(jsonb_build_object(
       'metric',metric_label,'weekday',trim(dow_name),'median',med,
       'is_highest', rank_best=1)) FROM dow),
  'auto', (SELECT jsonb_agg(jsonb_build_object(
       'source',source,'metric',metric,'n',n,'median',median,'p10',p10,'p90',p90,
       'min',min,'max',max,'last30_median',last30_median)
       ORDER BY source, metric) FROM auto),
  'lists', (SELECT l FROM lists),
  'stream_count', (SELECT count(*) FROM auto),
  'fact_count', (SELECT count(*)*6 FROM auto)
);
$fn$;
