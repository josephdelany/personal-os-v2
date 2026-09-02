-- 0033_review_fixes.sql — conversation-layer review findings (session-16 reviewer)
--
-- M1: contrasts persist their FDR family (REQ-INF-003: family id + size m).
-- M6: calibration stores a null DISTRIBUTION summary (median + p95 over
--     replicate shuffled runs), not a single-draw count (REQ-INF-410 posture).
-- M4: get_today no longer PUSHES exploratory content (REQ-INF-402 — generator
--     output only on the dedicated PULLED surface): the connection slot becomes
--     a pull invitation (a count and a pointer, no pattern content).
-- N8: timeline pre-formats sleep as text server-side (RULE-14: no client
--     arithmetic beyond formatting).

ALTER TABLE analysis.contrasts
    ADD COLUMN IF NOT EXISTS family_id TEXT,
    ADD COLUMN IF NOT EXISTS family_m  INTEGER;
ALTER TABLE analysis.scan_calibration
    ADD COLUMN IF NOT EXISTS null_p95  INTEGER,
    ADD COLUMN IF NOT EXISTS null_reps INTEGER;
COMMENT ON COLUMN analysis.scan_calibration.null_sig IS
  'MEDIAN discovery count across null_reps replicate circular-shift runs (v2).';

-- M4: replace the connection slot with a pull invitation
CREATE OR REPLACE FUNCTION public.get_today()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb; d date;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1;
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'for_day', d + 1, 'based_on', d,
      'state', public.get_state(d),
      'patterns_waiting', (      -- a COUNT is not generator content (REQ-INF-402)
        SELECT jsonb_build_object('count', count(*),
                 'note', 'exploratory patterns await on the Patterns tab (pull to read)')
          FROM core.hypothesis_register h
          JOIN analysis.contrasts c ON c.hypothesis_id = h.hypothesis_id
         WHERE h.status = 'CANDIDATE'
           AND c.run_date = (SELECT max(run_date) FROM analysis.contrasts)
        HAVING count(*) > 0),
      'watching', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis', replace(w.hypothesis_id,'watch:scan:',''),
                 'registered', w.preregistered_at::date,
                 'day', (current_date - w.preregistered_at::date), 'of', 30,
                 'status', w.status) ORDER BY w.preregistered_at)
          FROM core.hypothesis_register w
         WHERE w.hypothesis_id LIKE 'watch:%'),
      'forecast', (
        SELECT jsonb_agg(jsonb_build_object(
                 'metric', metric, 'lo', lo, 'point', point, 'hi', hi))
          FROM analysis.forecasts WHERE day_target = d + 1),
      'forecast_track_record', (
        SELECT jsonb_build_object(
            'resolved', count(*),
            'inside_band', count(*) FILTER (WHERE outcome_bool),
            'claimed_coverage', 0.90,
            'achieved_coverage', round(avg(outcome_bool::int)::numeric, 2))
          FROM core.predictions
         WHERE model_version LIKE 'forecast-%' AND outcome_bool IS NOT NULL
        HAVING count(*) > 0)
    )) INTO out;
    RETURN out;
END $fn$;

-- N8: server-side sleep formatting for the timeline
CREATE OR REPLACE FUNCTION public.get_timeline(p_day date)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE t0 timestamptz; t1 timestamptz; out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    t0 := (p_day::timestamptz + interval '4 hours');
    t1 := t0 + interval '24 hours';
    WITH entries AS (
        SELECT ts, 'web' AS kind,
               coalesce(payload->>'title','') || ' — ' || coalesce(payload->>'domain','') AS text,
               'chrome' AS src, id::text AS row_id
          FROM public.events WHERE kind='chrome_visit' AND ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'video',
               coalesce(payload->>'title','') || ' — ' || coalesce(payload->>'channel',''),
               'youtube', id::text
          FROM public.events WHERE kind='youtube_watch' AND ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'calendar', coalesce(payload->>'summary', payload->>'title', 'event'),
               'calendar', id::text
          FROM public.events WHERE kind='calendar' AND ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'money',
               coalesce(merchant,'?') || ' · $' || round(abs(amount)::numeric,2)::text
               || coalesce(' ('||category||')',''),
               'transactions', id::text
          FROM public.transactions WHERE ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'checkin',
               type || ' check-in' || coalesce(': "'||left(note,80)||'"',''),
               'checkins', id::text
          FROM public.checkins WHERE ts >= t0 AND ts < t1
        UNION ALL
        SELECT a.occurred_at, a.kind,
               coalesce(a.evidence_span,'') ||
               CASE WHEN a.value_point IS NOT NULL
                    THEN ' ('||a.value_point||coalesce(' '||a.unit,'')||')' ELSE '' END,
               'atoms', a.id::text
          FROM core.atoms_current a
         WHERE a.occurred_at >= t0 AND a.occurred_at < t1
           AND a.kind IN ('consume','note','workout','self_report')
    )
    SELECT jsonb_build_object(
        'day', p_day,
        'sleep_text', (SELECT 'slept ' || floor(value/60)::int || 'h'
                              || lpad((round(value)::int % 60)::text, 2, '0') || 'm'
                         FROM analysis.panel
                        WHERE day = p_day AND metric='sleep_asleep_min'),
        'n', (SELECT count(*) FROM entries),
        'entries', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                        'at', to_char(ts AT TIME ZONE 'America/New_York', 'HH24:MI'),
                        'kind', kind, 'text', left(text, 160),
                        'src', src, 'row_id', row_id) ORDER BY ts), '[]'::jsonb)
                      FROM entries))
    INTO out;
    RETURN out;
END $fn$;

-- refresh get_trust to publish the null p95
CREATE OR REPLACE FUNCTION public.get_trust()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'scan_calibration', (
        SELECT jsonb_agg(jsonb_build_object('run', run_date, 'tested', n_pairs_tested,
                 'observed_sig', observed_sig, 'shuffled_null_sig', null_sig,
                 'null_p95', null_p95, 'null_reps', null_reps)
               ORDER BY run_date DESC)
          FROM analysis.scan_calibration),
      'forecasts', (
        SELECT jsonb_build_object('resolved', count(*) FILTER (WHERE outcome_bool IS NOT NULL),
                 'inside_band', count(*) FILTER (WHERE outcome_bool),
                 'achieved_coverage', round(avg(outcome_bool::int) FILTER
                     (WHERE outcome_bool IS NOT NULL)::numeric, 2),
                 'claimed_coverage', 0.90,
                 'mean_brier', round(avg(brier)::numeric, 3),
                 'pending', count(*) FILTER (WHERE outcome_bool IS NULL))
          FROM core.predictions WHERE model_version LIKE 'forecast-%'),
      'hypotheses', (
        SELECT jsonb_build_object(
            'candidates', count(*) FILTER (WHERE status='CANDIDATE'),
            'watching',   count(*) FILTER (WHERE hypothesis_id LIKE 'watch:%' AND status='INSUFFICIENT'),
            'confirmed',  count(*) FILTER (WHERE status='CONFIRMED_OBSERVATIONAL'),
            'refuted',    count(*) FILTER (WHERE status='REFUTED'))
          FROM core.hypothesis_register),
      'job_heartbeats', (
        SELECT jsonb_agg(jsonb_build_object('job', job_name, 'last', max_t, 'status', st)
               ORDER BY job_name)
          FROM (SELECT job_name, max(started_at) AS max_t,
                       (array_agg(status ORDER BY started_at DESC))[1] AS st
                  FROM ops.runs GROUP BY job_name) j),
      'coverage_blindspots', (
        SELECT jsonb_agg(jsonb_build_object('metric', metric, 'last_day', mx) ORDER BY mx)
          FROM (SELECT metric, max(day) AS mx FROM analysis.panel
                 WHERE metric IN ('sleep_asleep_min','hrv_sdnn','rhr','steps',
                                  'screen_active_hours','spend.monetary_7d')
                 GROUP BY metric
                HAVING max(day) < current_date - 3) b)
    )) INTO out;
    RETURN out;
END $fn$;
