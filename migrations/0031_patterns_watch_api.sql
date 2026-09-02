-- 0031_patterns_watch_api.sql — the EXPLORATORY surface + the Watch loop (ADR-0038)
--
-- get_patterns(): renders ONLY hypothesis_register status='CANDIDATE' rows
-- (REQ-TIER-053), joined to their scan statistics, packaged in the EXPLORATORY
-- vocabulary (REQ-TIER-052: "may", "exploratory, not a finding", "unverified" —
-- and no confirmed-tier verb anywhere in the payload). Includes the KEYSTONE
-- driver ranking (count of distinct outcome families a driver appears in) and
-- the run's null-calibration numbers (published honesty). Text/labels only by
-- contract (ADR-0032) — the client renders no chart from this.
--
-- register_watch(): Joe's "Watch this" — inserts a NEW pre-registered row
-- (never mutates the CANDIDATE): preregistered_at=now(), clock starts today,
-- status='INSUFFICIENT' (honest: window_too_short until ~30 post-registration
-- days; REQ-INF-107). The freeze trigger + confirmation_data_from CHECK make
-- the registration unfakeable. E11 (weekly) later resolves it.

CREATE OR REPLACE FUNCTION public.get_patterns()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    SELECT jsonb_build_object(
      'tier', 'EXPLORATORY',
      'disclaimer', 'Exploratory associations from a screened scan of your history. '
                    'Each MAY reflect a real pattern and is unverified — not a finding. '
                    'Watching one starts a pre-registered test on your future days only.',
      'calibration', (SELECT jsonb_build_object(
                        'run_date', run_date, 'pairs_tested', n_pairs_tested,
                        'observed_significant', observed_sig,
                        'shuffled_null_significant', null_sig)
                        FROM analysis.scan_calibration
                       ORDER BY run_date DESC LIMIT 1),
      'patterns', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'hypothesis_id', h.hypothesis_id,
            'label', 'EXPLORATORY',
            'driver', c.driver, 'outcome', c.outcome, 'lag_days', c.lag_days,
            'seeded', c.seeded,
            'sentence',
              'On your highest-' || c.driver || ' days, ' || c.outcome ||
              CASE WHEN c.lag_days > 0 THEN ' ' || c.lag_days || ' day(s) later' ELSE ' the same day' END ||
              ' ran ' || to_char(abs(c.delta), 'FM999999990.99') ||
              CASE WHEN c.delta >= 0 THEN ' higher' ELSE ' lower' END ||
              ' than after your lowest (vs seasonal+weekday baseline). ' ||
              'This may reflect a pattern; it is exploratory and unverified.',
            'n_hi', c.n_hi, 'n_lo', c.n_lo,
            'n_eff', jsonb_build_array(c.n_eff_hi, c.n_eff_lo),
            'q', round(c.q_fdr::numeric, 4),
            'watched', EXISTS (SELECT 1 FROM core.hypothesis_register w
                                WHERE w.hypothesis_id = 'watch:' || h.hypothesis_id),
            'watch_progress', (
                SELECT jsonb_build_object(
                    'registered_at', w.preregistered_at::date,
                    'days_elapsed', (current_date - w.preregistered_at::date),
                    'days_needed', 30, 'status', w.status)
                  FROM core.hypothesis_register w
                 WHERE w.hypothesis_id = 'watch:' || h.hypothesis_id))
          ORDER BY c.q_fdr), '[]'::jsonb)
          FROM core.hypothesis_register h
          JOIN analysis.contrasts c ON c.hypothesis_id = h.hypothesis_id
         WHERE h.status = 'CANDIDATE'
           AND c.run_date = (SELECT max(run_date) FROM analysis.contrasts)),
      'keystone', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                 'driver', driver, 'outcome_families', fams, 'patterns', pats)
               ORDER BY fams DESC, pats DESC), '[]'::jsonb)
          FROM (SELECT c.driver,
                       count(DISTINCT split_part(c.outcome,'.',1)) AS fams,
                       count(*) AS pats
                  FROM analysis.contrasts c
                  JOIN core.hypothesis_register h ON h.hypothesis_id = c.hypothesis_id
                 WHERE h.status = 'CANDIDATE'
                   AND c.run_date = (SELECT max(run_date) FROM analysis.contrasts)
                 GROUP BY c.driver
                HAVING count(*) >= 2
                 ORDER BY 2 DESC, 3 DESC LIMIT 5) k))
    INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_patterns() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_patterns() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_patterns() TO authenticated;

CREATE OR REPLACE FUNCTION public.register_watch(p_hypothesis_id text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE c record; wid text;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    SELECT h.*, ct.delta INTO c
      FROM core.hypothesis_register h
      JOIN analysis.contrasts ct ON ct.hypothesis_id = h.hypothesis_id
     WHERE h.hypothesis_id = p_hypothesis_id AND h.status = 'CANDIDATE'
     ORDER BY ct.run_date DESC LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such CANDIDATE';
    END IF;
    wid := 'watch:' || p_hypothesis_id;
    INSERT INTO core.hypothesis_register
        (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction,
         transformation, adjustment_set, test_statistic, preregistered_at,
         confirmation_data_from, resolution_rule, status, mined_from_preexisting)
    VALUES (wid, c.exposure_metric, c.outcome_metric, c.lag_days, c.direction,
            c.transformation, c.adjustment_set, c.test_statistic, now(), now(),
            c.resolution_rule, 'INSUFFICIENT', false)
    ON CONFLICT (hypothesis_id) DO NOTHING;
    RETURN jsonb_build_object('watching', wid, 'registered_at', now()::date,
                              'clock', 'counts only days from today forward');
END $fn$;
REVOKE ALL ON FUNCTION public.register_watch(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.register_watch(text) FROM anon;
GRANT EXECUTE ON FUNCTION public.register_watch(text) TO authenticated;
