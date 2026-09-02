-- 0045_consistency.sql — B8: OQ-44 rulings (ADR-0049). Surfaces agree on `watching` (RULE-12) through one
-- predicate, `public._watching_rows()`; the v2 rule template for NEW registrations (`rule_version`; v1 rows keep
-- v1 semantics forever — REQ-INF-103, the frozen columns are untouched, `rule_version` is not one of them);
-- REQ-TIER-018's closed `insufficiency_reason` vocabulary on the ledger; `analysis.watch_progress`, the clock the
-- resolver writes nightly so no surface renders calendar days as paired days (RULE-14 / INV-3).

-- (i) rule_version: 'v1' for every row registered before this migration; register_watch writes 'v2' from now on.
ALTER TABLE __CORE__.hypothesis_register ADD COLUMN IF NOT EXISTS rule_version TEXT NOT NULL DEFAULT 'v1';
COMMENT ON COLUMN __CORE__.hypothesis_register.rule_version IS
  'ADR-0049: which resolution-rule semantics the resolver applies to this row. Not a frozen column; set at insert; never changed.';

-- (c) REQ-TIER-018 vocabulary alongside the resolver''s own reason; (i) v2 reasons; (j) low coverage.
ALTER TABLE __CORE__.hypothesis_resolutions
    ADD COLUMN IF NOT EXISTS insufficiency_reason TEXT CHECK (insufficiency_reason IN
        ('low_coverage','low_n_eff','informative_missingness','no_adjustment_set','sign_unstable','metric_absent','window_too_short')),
    ADD COLUMN IF NOT EXISTS coverage NUMERIC,
    ADD COLUMN IF NOT EXISTS look_day DATE;          -- the panel day the look was taken at (resolved_at is wall clock)
ALTER TABLE __CORE__.hypothesis_resolutions DROP CONSTRAINT IF EXISTS hypothesis_resolutions_reason_check;
ALTER TABLE __CORE__.hypothesis_resolutions ADD CONSTRAINT hypothesis_resolutions_reason_check CHECK (reason IN (
    'promoted_same_sign_q_lt_0_10', 'refuted_opposite_sign_q_lt_0_10',              -- v1
    'promoted_same_sign_p_lt_0_05', 'refuted_opposite_sign_p_lt_0_10',              -- v2
    'kept_promoted_same_sign_p_lt_0_10', 'demoted_sign_unstable',                    -- v2 look 2
    'insufficient_window_too_short', 'insufficient_low_n_eff', 'insufficient_sign_unstable',
    'insufficient_low_coverage', 'expired_no_decision_120d'));

-- (f) the clock, written by the resolver every night for every open watch
CREATE TABLE IF NOT EXISTS analysis.watch_progress (
    hypothesis_id  TEXT PRIMARY KEY,
    post_days      INTEGER,
    calendar_days  INTEGER,
    coverage       NUMERIC,
    n_eff          NUMERIC,
    n_hi           INTEGER,
    n_lo           INTEGER,
    next_look      DATE,                -- a PROJECTION (one paired day per calendar day), labelled so on every surface
    look_done      INTEGER,
    code_version   TEXT,
    computed_at    TIMESTAMPTZ DEFAULT now()
);
REVOKE ALL ON analysis.watch_progress FROM anon, authenticated;

-- (f) ONE predicate for "watching" (RULE-12). No client EXECUTE: the three surfaces call it.
CREATE OR REPLACE FUNCTION public._watching_rows()
RETURNS TABLE (hypothesis_id text, exposure_metric text, outcome_metric text, lag_days int, direction text,
               preregistered_at timestamptz, confirmation_data_from timestamptz, resolution_rule text,
               status text, rule_version text, post_days int, calendar_days int, coverage numeric, n_eff numeric,
               next_look date, looks_done int, last_look_reason text, days_needed int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT h.hypothesis_id, h.exposure_metric, h.outcome_metric, h.lag_days, h.direction,
           h.preregistered_at, h.confirmation_data_from, h.resolution_rule, h.status, h.rule_version,
           wp.post_days, wp.calendar_days, wp.coverage, wp.n_eff, wp.next_look,
           coalesce(lk.looks_done, 0) AS looks_done, lk.last_reason,
           CASE WHEN coalesce(lk.looks_done, 0) = 0 THEN 30 ELSE 120 END AS days_needed
      FROM __CORE__.hypothesis_register h
      LEFT JOIN analysis.watch_progress wp ON wp.hypothesis_id = h.hypothesis_id
      LEFT JOIN LATERAL (
            SELECT max(r.look) AS looks_done,
                   (SELECT r2.reason FROM __CORE__.hypothesis_resolutions r2
                     WHERE r2.hypothesis_id = h.hypothesis_id
                     ORDER BY r2.resolved_at DESC, r2.resolution_id LIMIT 1) AS last_reason
              FROM __CORE__.hypothesis_resolutions r
             WHERE r.hypothesis_id = h.hypothesis_id) lk ON true
     WHERE h.hypothesis_id LIKE 'watch:%'
       AND h.status IN ('INSUFFICIENT','PROMOTED')
       AND NOT EXISTS (SELECT 1 FROM __CORE__.hypothesis_resolutions r
                        WHERE r.hypothesis_id = h.hypothesis_id
                          AND (r.status_to = 'REFUTED' OR r.reason = 'expired_no_decision_120d'))
$fn$;
REVOKE ALL ON FUNCTION public._watching_rows() FROM PUBLIC;
REVOKE ALL ON FUNCTION public._watching_rows() FROM anon;
REVOKE ALL ON FUNCTION public._watching_rows() FROM authenticated;

-- (i) register_watch: every line as 0031 except the v2 rule text and rule_version
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
      FROM __CORE__.hypothesis_register h
      JOIN analysis.contrasts ct ON ct.hypothesis_id = h.hypothesis_id
     WHERE h.hypothesis_id = p_hypothesis_id AND h.status = 'CANDIDATE'
     ORDER BY ct.run_date DESC LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such CANDIDATE';
    END IF;
    wid := 'watch:' || p_hypothesis_id;
    INSERT INTO __CORE__.hypothesis_register
        (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction,
         transformation, adjustment_set, test_statistic, preregistered_at,
         confirmation_data_from, resolution_rule, status, mined_from_preexisting, rule_version)
    VALUES (wid, c.exposure_metric, c.outcome_metric, c.lag_days, c.direction,
            c.transformation, c.adjustment_set, c.test_statistic, now(), now(),
            'Look 1 at the first night with >=30 paired post-registration days: promote if same sign as registered '
            'and p<0.05 with n_eff>=20; refute if opposite sign and p<0.10. Look 2 at day 120: keep PROMOTED only if '
            'same sign and p<0.10, else demote to INSUFFICIENT(sign_unstable); refute if opposite sign and p<0.10.',
            'INSUFFICIENT', false, 'v2')
    ON CONFLICT (hypothesis_id) DO NOTHING;
    RETURN jsonb_build_object('watching', wid, 'registered_at', now()::date,
                              'clock', 'counts only paired days from today forward', 'rule_version', 'v2');
END $fn$;
REVOKE ALL ON FUNCTION public.register_watch(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.register_watch(text) FROM anon;
GRANT EXECUTE ON FUNCTION public.register_watch(text) TO authenticated;

-- get_today: only the `watching` block changes — same predicate, paired-day clock, projected next look
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
          FROM __CORE__.hypothesis_register h
          JOIN analysis.contrasts c ON c.hypothesis_id = h.hypothesis_id
         WHERE h.status = 'CANDIDATE'
           AND c.run_date = (SELECT max(run_date) FROM analysis.contrasts)
        HAVING count(*) > 0),
      'watching', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis', replace(w.hypothesis_id,'watch:scan:',''),
                 'hypothesis_id', w.hypothesis_id,
                 'registered', w.preregistered_at::date,
                 'day', w.post_days, 'of', w.days_needed,
                 'next_look', w.next_look,
                 'text', CASE WHEN w.post_days IS NULL THEN 'clock not yet computed'
                              ELSE 'day ' || w.post_days || ' of ' || w.days_needed ||
                                   coalesce(' · next look ~' || w.next_look, '') END,
                 'status', w.status, 'rule_version', w.rule_version) ORDER BY w.preregistered_at)
          FROM public._watching_rows() w),
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
          FROM __CORE__.predictions
         WHERE model_version LIKE 'forecast-%' AND outcome_bool IS NOT NULL
        HAVING count(*) > 0)
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_today() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_today() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_today() TO authenticated;

-- get_trust: the `watching` count reads the same predicate
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
          FROM __CORE__.predictions WHERE model_version LIKE 'forecast-%'),
      'hypotheses', (
        SELECT jsonb_build_object(
            'candidates', count(*) FILTER (WHERE status='CANDIDATE'),
            'watching',   (SELECT count(*) FROM public._watching_rows()),
            'confirmed',  count(*) FILTER (WHERE status='CONFIRMED_OBSERVATIONAL'),
            'refuted',    count(*) FILTER (WHERE status='REFUTED'))
          FROM __CORE__.hypothesis_register),
      'job_heartbeats', (
        SELECT jsonb_agg(jsonb_build_object('job', job_name, 'last', max_t, 'status', st)
               ORDER BY job_name)
          FROM (SELECT job_name, max(started_at) AS max_t,
                       (array_agg(status ORDER BY started_at DESC))[1] AS st
                  FROM __OPS__.runs GROUP BY job_name) j),
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

-- get_findings: `watching` and `counts.watching` from the shared predicate; history carries the vocabulary reason
CREATE OR REPLACE FUNCTION public.get_findings()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'as_of', current_date,
      'watching', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', w.hypothesis_id, 'tier', 'WATCHING',
                 'source', replace(w.hypothesis_id, 'watch:', ''),
                 'exposure', w.exposure_metric, 'outcome', w.outcome_metric, 'lag_days', w.lag_days,
                 'direction', w.direction, 'registered_at', w.preregistered_at::date,
                 'data_from', w.confirmation_data_from::date,
                 'days_elapsed', current_date - w.preregistered_at::date,     -- calendar days (kept, B6 contract)
                 'post_days', w.post_days, 'days_needed', w.days_needed,        -- the clock: PAIRED days (ADR-0049 f)
                 'coverage', w.coverage, 'n_eff', w.n_eff, 'next_look', w.next_look,
                 'looks_done', w.looks_done,
                 'insufficiency_reason', CASE WHEN w.looks_done = 0 AND w.status = 'INSUFFICIENT' THEN 'window_too_short' END,
                 'last_look_reason', w.last_look_reason,
                 'resolution_rule', w.resolution_rule, 'rule_version', w.rule_version, 'status', w.status,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',w.hypothesis_id))
               ORDER BY w.preregistered_at DESC)
          FROM public._watching_rows() w),
      'promoted', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'PROMOTED',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'direction', h.direction, 'adjustment_set', h.adjustment_set,
                 'registered_at', h.preregistered_at::date,
                 'promoted_at', (SELECT r.resolved_at::date FROM __CORE__.hypothesis_resolutions r
                                  WHERE r.hypothesis_id = h.hypothesis_id AND r.status_to = 'PROMOTED'
                                  ORDER BY r.resolved_at DESC LIMIT 1),
                 'note', 'pre-registered contrast survived on post-registration data; not a causal claim (REQ-TIER-013 gate unbuilt)',
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h WHERE h.status = 'PROMOTED'),
      'confirmed', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'CONFIRMED',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'direction', h.direction, 'adjustment_set', h.adjustment_set,
                 'e_value', NULL, 'negative_control', NULL,        -- not computed yet: absent, and the UI says so
                 'registered_at', h.preregistered_at::date,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h WHERE h.status = 'CONFIRMED_OBSERVATIONAL'),
      'refuted', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'REFUTED',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'registered_at', h.preregistered_at::date,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h WHERE h.status = 'REFUTED'),
      'insufficient', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'INSUFFICIENT',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'registered_at', h.preregistered_at::date,
                 'reason', (SELECT r.reason FROM __CORE__.hypothesis_resolutions r
                             WHERE r.hypothesis_id = h.hypothesis_id
                             ORDER BY r.resolved_at DESC, r.resolution_id LIMIT 1),
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h
         WHERE h.status = 'INSUFFICIENT'
           AND (h.hypothesis_id NOT LIKE 'watch:%'
                OR EXISTS (SELECT 1 FROM __CORE__.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id
                              AND r.reason = 'expired_no_decision_120d'))),
      'history', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', r.hypothesis_id, 'tier', r.status_to,
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'direction', h.direction,                      -- the previous claim, named (REQ-TIER-043)
                 'resolved_at', r.resolved_at, 'status_from', r.status_from, 'status_to', r.status_to,
                 'reason', r.reason, 'insufficiency_reason', r.insufficiency_reason, 'look', r.look, 'look_day', r.look_day,
                 'post_days', r.post_days, 'coverage', r.coverage,
                 'status_changed', r.status_from IS DISTINCT FROM r.status_to,   -- a look record vs a status change
                 'n_eff', r.n_eff, 'family_m', r.family_m,
                 'delta', round(r.delta, 4), 'q_fdr', round(r.q_fdr, 4),
                 'trace', jsonb_build_object('table','core.hypothesis_resolutions','resolution_id',r.resolution_id))
               ORDER BY r.resolved_at DESC, r.resolution_id)
          FROM (SELECT * FROM __CORE__.hypothesis_resolutions ORDER BY resolved_at DESC, resolution_id LIMIT 50) r
          JOIN __CORE__.hypothesis_register h ON h.hypothesis_id = r.hypothesis_id),
      'counts', (
        SELECT jsonb_build_object(
            'candidates', count(*) FILTER (WHERE status='CANDIDATE'),
            'watching',   (SELECT count(*) FROM public._watching_rows()),
            'confirmed',  count(*) FILTER (WHERE status='CONFIRMED_OBSERVATIONAL'),
            'refuted',    count(*) FILTER (WHERE status='REFUTED'))
          FROM __CORE__.hypothesis_register h),
      'predictions_pending', (
        SELECT jsonb_agg(jsonb_build_object('claim', left(p.claim_text,160), 'tier', p.evidence_tier,
                 'resolves_at', p.resolves_at::date, 'hypothesis_id', p.hypothesis_id,
                 'trace', jsonb_build_object('table','core.predictions','prediction_id',p.prediction_id))
               ORDER BY p.resolves_at)
          FROM __CORE__.predictions p
         WHERE p.outcome_bool IS NULL AND p.model_version NOT LIKE 'forecast-%')
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_findings() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_findings() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_findings() TO authenticated;
