-- 0030_state_api.sql — E2: yesterday-vs-you, week-vs-you, streaks, guardian (ADR-0038)
-- Owner-locked. All DESCRIPTIVE: ranks, deltas, run-lengths, concurrence counts —
-- no judgment words, no causal verbs. Sources: analysis.baselines (dual-z engine
-- output) + public.transactions (weekly money deltas).

CREATE OR REPLACE FUNCTION public.get_state(p_day date DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE d date; out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := coalesce(p_day,
                  (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1);
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'day', d,
      -- yesterday vs you: strongest personal deviations, |z_fast| ranked
      'deviations', (
        SELECT jsonb_agg(jsonb_build_object(
                 'metric', metric, 'value', round(value::numeric,2),
                 'z', round(z_fast::numeric,2),
                 'band', jsonb_build_array(round(band_lo::numeric,2), round(band_hi::numeric,2)))
               ORDER BY abs(z_fast) DESC)
          FROM (SELECT * FROM analysis.baselines
                 WHERE day = d AND z_fast IS NOT NULL AND abs(z_fast) >= 1.5
                 ORDER BY abs(z_fast) DESC LIMIT 8) t),
      -- streaks: consecutive days outside the personal band (with historical max)
      'streaks', (
        SELECT jsonb_agg(jsonb_build_object(
                 'metric', metric, 'run_days', run_days,
                 'direction', direction, 'historical_max_run', mx)
               ORDER BY run_days DESC)
          FROM (SELECT b.metric, abs(b.run_len) AS run_days,
                       CASE WHEN b.run_len > 0 THEN 'above' ELSE 'below' END AS direction,
                       h.mx
                  FROM analysis.baselines b
                  JOIN LATERAL (SELECT max(abs(run_len)) AS mx FROM analysis.baselines
                                 WHERE metric = b.metric) h ON true
                 WHERE b.day = d AND abs(b.run_len) >= 2
                 ORDER BY abs(b.run_len) DESC LIMIT 6) t),
      -- guardian: 2-of-N autonomic concurrence (descriptive pattern-match only;
      -- states the count and the historical frequency, never a diagnosis)
      'guardian', (
        WITH sig AS (
          SELECT count(*) FILTER (WHERE metric='rhr'          AND z_fast >=  1.0) +
                 count(*) FILTER (WHERE metric='hrv_sdnn'     AND z_fast <= -1.0) +
                 count(*) FILTER (WHERE metric='resp_night'   AND z_fast >=  1.0) +
                 count(*) FILTER (WHERE metric='wrist_temp_f' AND z_fast >=  1.0) AS k
            FROM analysis.baselines WHERE day = d),
        hist AS (
          SELECT count(*) AS fired_days FROM (
            SELECT day,
                   count(*) FILTER (WHERE metric='rhr'          AND z_fast >=  1.0) +
                   count(*) FILTER (WHERE metric='hrv_sdnn'     AND z_fast <= -1.0) +
                   count(*) FILTER (WHERE metric='resp_night'   AND z_fast >=  1.0) +
                   count(*) FILTER (WHERE metric='wrist_temp_f' AND z_fast >=  1.0) AS k
              FROM analysis.baselines GROUP BY day) g WHERE g.k >= 2)
        SELECT jsonb_build_object('signals_firing', sig.k, 'threshold', 2,
                                  'fires_historically', hist.fired_days)
          FROM sig, hist WHERE sig.k >= 2),
      -- this ISO-week money vs your trailing-26-week medians
      'week_money', (
        WITH wk AS (SELECT date_trunc('week', d::timestamptz) AS w0),
        this AS (
          SELECT coalesce(merchant,'?') AS name, 'merchant' AS grain,
                 round(sum(abs(amount))::numeric,2) AS amt
            FROM public.transactions, wk
           WHERE ts >= wk.w0 AND ts < wk.w0 + interval '7 days'
           GROUP BY 1
          UNION ALL
          SELECT coalesce(category,'?'), 'category', round(sum(abs(amount))::numeric,2)
            FROM public.transactions, wk
           WHERE ts >= wk.w0 AND ts < wk.w0 + interval '7 days'
           GROUP BY 1),
        hist AS (
          SELECT name, grain, percentile_cont(0.5) WITHIN GROUP (ORDER BY wk_amt) AS med
            FROM (SELECT coalesce(merchant,'?') AS name, 'merchant' AS grain,
                         date_trunc('week', ts) AS w, sum(abs(amount)) AS wk_amt
                    FROM public.transactions, wk
                   WHERE ts >= wk.w0 - interval '182 days' AND ts < wk.w0
                   GROUP BY 1, 3
                  UNION ALL
                  SELECT coalesce(category,'?'), 'category', date_trunc('week', ts),
                         sum(abs(amount))
                    FROM public.transactions, wk
                   WHERE ts >= wk.w0 - interval '182 days' AND ts < wk.w0
                   GROUP BY 1, 3) h
           GROUP BY 1, 2)
        SELECT jsonb_agg(jsonb_build_object(
                 'name', t.name, 'grain', t.grain, 'this_week', t.amt,
                 'typical_week', round(coalesce(h.med,0)::numeric,2),
                 'delta', round((t.amt - coalesce(h.med,0))::numeric,2))
               ORDER BY abs(t.amt - coalesce(h.med,0)) DESC)
          FROM (SELECT * FROM this ORDER BY amt DESC LIMIT 40) t
          LEFT JOIN hist h USING (name, grain)
         WHERE abs(t.amt - coalesce(h.med,0)) >= 20)
    )) INTO out;
    RETURN out;
END $fn$;

REVOKE ALL ON FUNCTION public.get_state(date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_state(date) FROM anon;
GRANT EXECUTE ON FUNCTION public.get_state(date) TO authenticated;
