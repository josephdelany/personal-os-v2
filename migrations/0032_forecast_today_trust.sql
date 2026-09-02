-- 0032_forecast_today_trust.sql — E5 storage + E9 Today compositor + Trust tab (ADR-0038)

CREATE TABLE IF NOT EXISTS analysis.forecasts (
    day_target   DATE NOT NULL,
    metric       TEXT NOT NULL,
    lo           NUMERIC NOT NULL,
    point        NUMERIC NOT NULL,
    hi           NUMERIC NOT NULL,
    code_version TEXT NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day_target, metric)
);

-- ---------- get_today(): the 7-slot brief in one envelope ----------
-- STATE + deviations/streaks/guardian (reuses get_state) · CONNECTION (top
-- unseen-recently pattern, EXPLORATORY-labeled) · WEEK money · KEYSTONE ·
-- WATCHING (registrations + clocks) · FORECAST (bands + rolling coverage).
-- Deterministic composition; renders template-only without any model (RULE-15).
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
      'connection', (
        SELECT jsonb_build_object('label','EXPLORATORY','sentence',
            'On your highest-' || c.driver || ' days, ' || c.outcome ||
            CASE WHEN c.lag_days > 0 THEN ' ' || c.lag_days || ' day(s) later' ELSE ' the same day' END ||
            ' ran ' || to_char(abs(c.delta),'FM999999990.99') ||
            CASE WHEN c.delta >= 0 THEN ' higher' ELSE ' lower' END ||
            ' than after your lowest. Exploratory, unverified.',
            'q', round(c.q_fdr::numeric,4), 'n', c.n_hi + c.n_lo)
          FROM analysis.contrasts c
          JOIN core.hypothesis_register h ON h.hypothesis_id = c.hypothesis_id
         WHERE h.status = 'CANDIDATE'
           AND c.run_date = (SELECT max(run_date) FROM analysis.contrasts)
         ORDER BY md5(c.contrast_id || d::text)     -- deterministic daily rotation (novelty)
         LIMIT 1),
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
REVOKE ALL ON FUNCTION public.get_today() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_today() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_today() TO authenticated;

-- ---------- get_trust(): the system's own report card ----------
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
                 'observed_sig', observed_sig, 'shuffled_null_sig', null_sig)
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
REVOKE ALL ON FUNCTION public.get_trust() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_trust() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_trust() TO authenticated;
