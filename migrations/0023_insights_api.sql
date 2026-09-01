-- 0023_insights_api.sql — the descriptive insight engine (ADR-0038)
--
-- One RPC computes a battery of DESCRIPTIVE facts over the whole corpus — the
-- legacy tables (2 years: signals/intraday-era events/transactions/checkins) and
-- the new spine (core.atoms). Every insight is: deterministic SQL, tier
-- DESCRIPTIVE, shipped with its n and window, computed at read time (no stored
-- copy to go stale, no fabrication surface). NO causal claims, NO judgments, NO
-- scores — RULE-16/23/24: these are facts about the data, not verdicts about Joe.
-- authenticated-only, same posture as get_day (ADR-0036).

CREATE OR REPLACE FUNCTION public.get_insights()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $fn$
WITH ins AS (

-- ============ SLEEP (apple_sleep signals, minutes) ============
SELECT 'sleep' AS domain, 'Median nightly sleep' AS title,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric,0) AS value,
       'min' AS unit, count(*) AS n, 'all time' AS win, 10 AS ord
  FROM public.signals WHERE source='apple_sleep' AND metric='asleep_min' AND value>0
UNION ALL
SELECT 'sleep','Shortest night on record',
       round(min(value)::numeric,0),'min',count(*),'all time',11
  FROM public.signals WHERE source='apple_sleep' AND metric='asleep_min' AND value>60
UNION ALL
SELECT 'sleep','Longest night on record',
       round(max(value)::numeric,0),'min',count(*),'all time',12
  FROM public.signals WHERE source='apple_sleep' AND metric='asleep_min' AND value>0
UNION ALL
SELECT 'sleep','Nights under 6 hours',
       count(*) FILTER (WHERE value < 360),'nights',count(*),'all time',13
  FROM public.signals WHERE source='apple_sleep' AND metric='asleep_min' AND value>0

-- ============ HEART (hrv / resting hr) ============
UNION ALL
SELECT 'heart','Median HRV (SDNN)',
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric,1),
       'ms',count(*),'all time',20
  FROM public.signals WHERE source='apple_hrv' AND metric='sdnn' AND value>0
UNION ALL
SELECT 'heart','Best HRV day',
       round(max(value)::numeric,1),'ms',count(*),'all time',21
  FROM public.signals WHERE source='apple_hrv' AND metric='sdnn' AND value>0
UNION ALL
SELECT 'heart','Median resting HR',
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric,0),
       'bpm',count(*),'all time',22
  FROM public.signals WHERE ((source='apple_vitals' AND metric='rhr_night') OR (source='health_history' AND metric='rhr')) AND value BETWEEN 30 AND 120

-- ============ SCREEN & ATTENTION ============
UNION ALL
SELECT 'screen','Days of screen life recorded',
       count(DISTINCT ts::date),'days',count(*),'all time',30
  FROM public.signals WHERE source='attention'
UNION ALL
SELECT 'screen','Median daily active screen hours',
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric,1),
       'h',count(*),'all time',31
  FROM public.signals WHERE source='attention' AND metric='active_hours' AND value BETWEEN 0 AND 24
UNION ALL
SELECT 'screen','YouTube videos watched',
       count(*),'videos',count(*),'all time',32
  FROM public.events WHERE kind='youtube_watch'
UNION ALL
SELECT 'screen','Distinct websites visited',
       count(DISTINCT payload->>'domain'),'sites',count(*),'all time',33
  FROM public.events WHERE kind='chrome_visit'
UNION ALL
SELECT 'screen','Most-visited hour of day (web)',
       (SELECT extract(hour FROM ts AT TIME ZONE 'America/New_York')::int
          FROM public.events WHERE kind='chrome_visit'
         GROUP BY 1 ORDER BY count(*) DESC LIMIT 1),
       'h (ET)',count(*),'all time',34
  FROM public.events WHERE kind='chrome_visit'

-- ============ MONEY ============
UNION ALL
SELECT 'money','Transactions captured',
       count(*),'txns',count(*),'all time',40
  FROM public.transactions
UNION ALL
SELECT 'money','Distinct merchants seen',
       count(DISTINCT merchant),'merchants',count(*),'all time',41
  FROM public.transactions
UNION ALL
SELECT 'money','Median transaction',
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(amount))::numeric,2),
       'USD',count(*),'all time',42
  FROM public.transactions WHERE amount IS NOT NULL

-- ============ MOVEMENT ============
UNION ALL
SELECT 'movement','Median daily steps',
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric,0),
       'steps',count(*),'all time',50
  FROM public.signals WHERE source IN ('health_history','apple_watch') AND metric='steps' AND value BETWEEN 0 AND 100000
UNION ALL
SELECT 'movement','Biggest step day',
       round(max(value)::numeric,0),'steps',count(*),'all time',51
  FROM public.signals WHERE source IN ('health_history','apple_watch') AND metric='steps' AND value BETWEEN 0 AND 100000
UNION ALL
SELECT 'movement','Places visited (labeled)',
       count(*),'places',count(*),'all time',52
  FROM public.place_book

-- ============ ENVIRONMENT / CONTEXT ============
UNION ALL
SELECT 'context','Weather observations logged',
       count(*),'obs',count(*),'all time',60
  FROM public.signals WHERE source='weather'
UNION ALL
SELECT 'context','Calendar events tracked',
       count(*),'events',count(*),'all time',61
  FROM public.events WHERE kind='calendar'
UNION ALL
SELECT 'context','GitHub commits captured',
       count(*),'commits',count(*),'all time',62
  FROM public.events WHERE kind='github_commit'

-- ============ THE NEW SPINE (trustworthy layer) ============
UNION ALL
SELECT 'spine','Immutable captures in the new system',
       count(*),'captures',count(*),'all time',70
  FROM core.raw_captures
UNION ALL
SELECT 'spine','Traceable facts (atoms)',
       count(*),'atoms',count(*),'all time',71
  FROM core.atoms
UNION ALL
SELECT 'spine','Metrics registered',
       count(*),'metrics',count(*),'now',72
  FROM core.metric_registry
)
SELECT jsonb_build_object(
  'tier','DESCRIPTIVE',
  'disclaimer','Facts about the recorded data. Descriptive only — no causal claim, no judgment. Each carries its n.',
  'computed_at', now(),
  'insights', jsonb_agg(jsonb_build_object(
     'domain',domain,'title',title,'value',value,'unit',unit,'n',n,'window',win)
     ORDER BY ord))
FROM ins WHERE value IS NOT NULL;
$fn$;

REVOKE ALL ON FUNCTION public.get_insights() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_insights() FROM anon;
GRANT  EXECUTE ON FUNCTION public.get_insights() TO authenticated;

COMMENT ON FUNCTION public.get_insights() IS
  'ADR-0038: deterministic DESCRIPTIVE battery over the whole corpus, computed at '
  'read time. Tier + n on every fact; never causal, never a judgment. Owner-only.';
