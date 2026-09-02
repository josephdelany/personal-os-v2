-- 0046_confirmation_gate.sql — B9: promotion to REQ-TIER-012 and the REQ-TIER-013 confirmation gate.
-- ADR-0050 (specification curve + promotion gate), ADR-0051 (registered DAG + confirmation gate).
--
-- REQ-TIER-012: promotion requires hierarchical-FDR rejection at every level of its branch, a specification
-- curve over >=50 defensible specifications, and a circular-shift null whose median significant-share the
-- observed share exceeds. REQ-TIER-013: CONFIRMED_OBSERVATIONAL requires post-registration data only, a
-- minimal sufficient adjustment set from the DAG, Newey-West HAC errors, an E-value at the point estimate AND
-- at the interval limit nearest the null, all negative controls passed and all refutation tests passed.
-- REQ-TIER-014: any negative-control or refutation failure -> REFUTED + a DESCRIPTIVE statement to Joe.
-- REQ-TIER-040: promotion may not skip a step (enforced by trigger, below). REQ-TIER-042: every demotion
-- records the job id that performed it (`run_id`).

-- ---------------------------------------------------------------- the registered DAG (ADR-0051)
CREATE TABLE IF NOT EXISTS config.dag_edges (
    src   TEXT NOT NULL,
    dst   TEXT NOT NULL,                 -- '*' on dst means "every metric" (the exogenous clocks)
    basis TEXT NOT NULL CHECK (basis IN ('exogenous_clock','physiology','behaviour','joe')),
    PRIMARY KEY (src, dst)
);
COMMENT ON TABLE config.dag_edges IS
  'ADR-0051. The registered causal DAG used ONLY to compute minimal sufficient adjustment sets. An edge that '
  'is not in this table does not exist for adjustment purposes. The seed is a FLOOR, not a claim about the '
  'world: it asserts only relationships the ontology already assumes. Joe extends it by migration.';
REVOKE ALL ON config.dag_edges FROM anon, authenticated;

INSERT INTO config.dag_edges (src, dst, basis) VALUES
 ('day_of_week','*','exogenous_clock'), ('season','*','exogenous_clock'),
 ('alcohol_standard_drinks','sleep_asleep_min','physiology'), ('alcohol_standard_drinks','hrv_sdnn','physiology'),
 ('alcohol_standard_drinks','rhr','physiology'), ('alcohol_standard_drinks','sleep_efficiency','physiology'),
 ('sleep_asleep_min','hrv_sdnn','physiology'), ('sleep_asleep_min','rhr','physiology'),
 ('sleep_asleep_min','checkin_morning_energy','physiology'), ('sleep_asleep_min','checkin_morning_mood','physiology'),
 ('sleep_asleep_min','checkin_night_mood','physiology'), ('sleep_asleep_min','checkin_night_energy','physiology'),
 ('steps','sleep_asleep_min','behaviour'), ('exercise_min','sleep_asleep_min','behaviour'),
 ('exercise_min','hrv_sdnn','physiology'), ('strength_volume','hrv_sdnn','physiology'),
 ('screen_active_hours','sleep_asleep_min','behaviour'), ('screen_binge_min','sleep_onset_min','behaviour'),
 ('screen_active_hours','checkin_night_mood','behaviour'),
 ('spend.monetary_7d','checkin_night_stress','behaviour'),
 ('wrist_temp_f','hrv_sdnn','physiology'), ('resp_night','hrv_sdnn','physiology')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------- the specification curve (REQ-TIER-012)
CREATE TABLE IF NOT EXISTS analysis.spec_curves (
    hypothesis_id  TEXT NOT NULL,
    look           SMALLINT NOT NULL,
    spec_id        INTEGER NOT NULL,
    transformation TEXT NOT NULL,
    split          TEXT NOT NULL,
    trim           TEXT NOT NULL,
    window_spec    TEXT NOT NULL,     -- 'window' is a reserved word in PostgreSQL
    test           TEXT NOT NULL,
    n              INTEGER,
    delta          NUMERIC,
    p              NUMERIC,
    same_sign      BOOLEAN,
    code_version   TEXT NOT NULL,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (hypothesis_id, look, spec_id)
);
CREATE INDEX IF NOT EXISTS spec_curves_hyp_idx ON analysis.spec_curves (hypothesis_id, look);
REVOKE ALL ON analysis.spec_curves FROM anon, authenticated;

-- ---------------------------------------------------------------- the brief notices (REQ-TIER-014 / 043)
CREATE TABLE IF NOT EXISTS analysis.brief_notes (
    note_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind          TEXT NOT NULL CHECK (kind IN ('refutation','demotion','confirmation')),
    hypothesis_id TEXT NOT NULL,
    text          TEXT NOT NULL,
    tier          TEXT NOT NULL DEFAULT 'DESCRIPTIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    shown_at      TIMESTAMPTZ
);
COMMENT ON TABLE analysis.brief_notes IS
  'REQ-TIER-014 / REQ-TIER-043: the DESCRIPTIVE statement naming a hypothesis and the check that failed, '
  'surfaced in the next brief (get_today.notices[]).';
REVOKE ALL ON analysis.brief_notes FROM anon, authenticated;

-- ---------------------------------------------------------------- ledger columns (REQ-TIER-013 / 023 / 028 / 042)
ALTER TABLE __CORE__.hypothesis_resolutions
    ADD COLUMN IF NOT EXISTS run_id           UUID,          -- REQ-TIER-042: the job that performed it (ops.runs)
    ADD COLUMN IF NOT EXISTS share_sig        NUMERIC,
    ADD COLUMN IF NOT EXISTS null_share       NUMERIC,
    ADD COLUMN IF NOT EXISTS q_l1             NUMERIC,
    ADD COLUMN IF NOT EXISTS q_l2             NUMERIC,
    ADD COLUMN IF NOT EXISTS counter_frame_n  INTEGER,
    ADD COLUMN IF NOT EXISTS adjustment_set   JSONB,
    ADD COLUMN IF NOT EXISTS beta             NUMERIC,
    ADD COLUMN IF NOT EXISTS outcome_unit     TEXT,
    ADD COLUMN IF NOT EXISTS ci_lo            NUMERIC,
    ADD COLUMN IF NOT EXISTS ci_hi            NUMERIC,
    ADD COLUMN IF NOT EXISTS hac_maxlags      INTEGER,
    ADD COLUMN IF NOT EXISTS prob_direction   NUMERIC,
    ADD COLUMN IF NOT EXISTS e_value_point    NUMERIC,
    ADD COLUMN IF NOT EXISTS e_value_limit    NUMERIC,
    ADD COLUMN IF NOT EXISTS nc_outcome_metric TEXT,
    ADD COLUMN IF NOT EXISTS nc_outcome_p     NUMERIC,
    ADD COLUMN IF NOT EXISTS nc_exposure_p    NUMERIC,
    ADD COLUMN IF NOT EXISTS refuter_results  JSONB,
    ADD COLUMN IF NOT EXISTS next_recheck     DATE;
COMMENT ON COLUMN __CORE__.hypothesis_resolutions.ci_lo IS
  'Frequentist HAC 95% interval, STORED for audit and for the E-value at the limit nearest the null. '
  'REQ-TIER-025 forbids rendering a frequentist interval on a user-facing surface, so get_findings exposes '
  'prob_direction instead; the interval is reachable only through the trace (ADR-0051).';

ALTER TABLE analysis.watch_progress
    ADD COLUMN IF NOT EXISTS share_sig        NUMERIC,
    ADD COLUMN IF NOT EXISTS null_median_share NUMERIC,
    ADD COLUMN IF NOT EXISTS fdr_level1_q     NUMERIC,
    ADD COLUMN IF NOT EXISTS fdr_level2_q     NUMERIC,
    ADD COLUMN IF NOT EXISTS counter_frame_n  INTEGER,
    ADD COLUMN IF NOT EXISTS next_recheck     DATE;

ALTER TABLE __CORE__.hypothesis_resolutions DROP CONSTRAINT IF EXISTS hypothesis_resolutions_reason_check;
ALTER TABLE __CORE__.hypothesis_resolutions ADD CONSTRAINT hypothesis_resolutions_reason_check CHECK (reason IN (
    'promoted_same_sign_q_lt_0_10', 'refuted_opposite_sign_q_lt_0_10',                    -- v1
    'promoted_same_sign_p_lt_0_05', 'refuted_opposite_sign_p_lt_0_10',                    -- v2 look 1
    'kept_promoted_same_sign_p_lt_0_10', 'demoted_sign_unstable',                          -- v2 look 2
    'insufficient_window_too_short', 'insufficient_low_n_eff', 'insufficient_sign_unstable',
    'insufficient_low_coverage', 'expired_no_decision_120d',
    'insufficient_fdr_not_rejected', 'insufficient_spec_curve_unstable',                   -- B9.1 promotion gate
    'confirmed_all_checks_passed', 'insufficient_no_adjustment_set',                       -- B9.2 confirmation gate
    'refuted_negative_control_failed', 'refuted_refutation_test_failed', 'demoted_recheck_failed'));

-- REQ-TIER-040: promotion may not skip a step. Demotion to any lower tier or REFUTED is unrestricted
-- (REQ-TIER-041) and needs no human approval (REQ-TIER-044 — nothing here asks for one).
CREATE OR REPLACE FUNCTION __CORE__.reject_tier_skip() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE rank_old int; rank_new int;
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
    rank_old := CASE OLD.status WHEN 'CANDIDATE' THEN 0 WHEN 'INSUFFICIENT' THEN 0 WHEN 'PROMOTED' THEN 1
                                WHEN 'CONFIRMED_OBSERVATIONAL' THEN 2 WHEN 'EXPERIMENTAL' THEN 3 ELSE -1 END;
    rank_new := CASE NEW.status WHEN 'CANDIDATE' THEN 0 WHEN 'INSUFFICIENT' THEN 0 WHEN 'PROMOTED' THEN 1
                                WHEN 'CONFIRMED_OBSERVATIONAL' THEN 2 WHEN 'EXPERIMENTAL' THEN 3 ELSE -1 END;
    -- REFUTED (rank -1) is reachable from anywhere; any downward move is permitted.
    IF rank_new > rank_old + 1 THEN
        RAISE EXCEPTION
          'REQ-TIER-040: promotion may not skip a step (% -> %); the order is CANDIDATE/INSUFFICIENT -> PROMOTED -> CONFIRMED_OBSERVATIONAL -> EXPERIMENTAL.',
          OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS hypothesis_register_tier_order ON __CORE__.hypothesis_register;
CREATE TRIGGER hypothesis_register_tier_order
    BEFORE UPDATE ON __CORE__.hypothesis_register
    FOR EACH ROW EXECUTE FUNCTION __CORE__.reject_tier_skip();

-- ---------------------------------------------------------------- envelopes (all additive)
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
      'notices', (      -- REQ-TIER-014 / REQ-TIER-043: demotions and refutations, named, in the next brief
        SELECT jsonb_agg(jsonb_build_object('kind', n.kind, 'tier', n.tier, 'text', n.text,
                 'hypothesis_id', n.hypothesis_id, 'at', n.created_at,
                 'trace', jsonb_build_object('table','analysis.brief_notes','note_id',n.note_id))
               ORDER BY n.created_at DESC)
          FROM analysis.brief_notes n WHERE n.created_at > now() - interval '14 days'),
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
                 'spec_curve', (SELECT jsonb_build_object('n_specs', count(*), 'share_sig', wp.share_sig,
                                        'null_median_share', wp.null_median_share)
                                  FROM analysis.spec_curves sc WHERE sc.hypothesis_id = w.hypothesis_id
                                 HAVING count(*) > 0),
                 'fdr', jsonb_build_object('q_l1', wp.fdr_level1_q, 'q_l2', wp.fdr_level2_q),
                 'looks_done', w.looks_done,
                 'insufficiency_reason', CASE WHEN w.looks_done = 0 AND w.status = 'INSUFFICIENT' THEN 'window_too_short' END,
                 'last_look_reason', w.last_look_reason,
                 'resolution_rule', w.resolution_rule, 'rule_version', w.rule_version, 'status', w.status,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',w.hypothesis_id))
               ORDER BY w.preregistered_at DESC)
          FROM public._watching_rows() w
          LEFT JOIN analysis.watch_progress wp ON wp.hypothesis_id = w.hypothesis_id),
      'promoted', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'PROMOTED',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'direction', h.direction, 'adjustment_set', h.adjustment_set,
                 'registered_at', h.preregistered_at::date,
                 'promoted_at', (SELECT r.resolved_at::date FROM __CORE__.hypothesis_resolutions r
                                  WHERE r.hypothesis_id = h.hypothesis_id AND r.status_to = 'PROMOTED'
                                  ORDER BY r.resolved_at DESC LIMIT 1),
                 'note', 'pre-registered, survived the specification curve and hierarchical FDR on post-registration data; not yet a causal claim',
                 'spec_curve', jsonb_build_object('n_specs', (SELECT count(*) FROM analysis.spec_curves sc
                                                               WHERE sc.hypothesis_id = h.hypothesis_id AND sc.look = 1),
                                                  'share_sig', wp.share_sig, 'null_median_share', wp.null_median_share),
                 'fdr', jsonb_build_object('q_l1', wp.fdr_level1_q, 'q_l2', wp.fdr_level2_q),
                 'counter_frame_n', wp.counter_frame_n,          -- REQ-TIER-028, in the same payload as the claim
                 'next_recheck', wp.next_recheck,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h
          LEFT JOIN analysis.watch_progress wp ON wp.hypothesis_id = h.hypothesis_id
         WHERE h.status = 'PROMOTED'),
      'confirmed', (
        -- REQ-TIER-023: adjustment set, E-value at the point estimate, and the negative-control result in the
        -- SAME payload as the claim. REQ-TIER-024: the effect is in absolute outcome units, never a percentage.
        -- REQ-TIER-025: no frequentist interval is rendered — `prob_direction` is the probability-of-direction
        -- statement; the stored HAC interval is reachable only through the trace (ADR-0051).
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'CONFIRMED_OBSERVATIONAL',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'direction', h.direction,
                 'adjustment_set', coalesce(r.adjustment_set, h.adjustment_set),
                 'effect', jsonb_build_object('beta', round(r.beta, 4), 'unit', r.outcome_unit,
                                              'per', '1 unit of ' || h.exposure_metric,
                                              'hac_maxlags', r.hac_maxlags,
                                              'prob_direction', round(r.prob_direction, 4)),
                 'e_value', jsonb_build_object('point', round(r.e_value_point, 3), 'limit', round(r.e_value_limit, 3),
                                               'note', 'RR approximated from the standardized effect (Chinn 2000, RR = exp(0.91*d)); an approximation, not a measured risk ratio'),
                 'negative_controls', jsonb_build_object('outcome_metric', r.nc_outcome_metric,
                                                         'outcome_p', round(r.nc_outcome_p, 4),
                                                         'future_exposure_p', round(r.nc_exposure_p, 4)),
                 'refuters', r.refuter_results,
                 'counter_frame_n', r.counter_frame_n,
                 'confirmed_at', r.resolved_at::date, 'next_recheck', r.next_recheck,
                 'registered_at', h.preregistered_at::date,
                 'trace', jsonb_build_object('table','core.hypothesis_resolutions','resolution_id',r.resolution_id,
                                             'hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h
          LEFT JOIN LATERAL (SELECT * FROM __CORE__.hypothesis_resolutions rr
                              WHERE rr.hypothesis_id = h.hypothesis_id AND rr.status_to = 'CONFIRMED_OBSERVATIONAL'
                              ORDER BY rr.resolved_at DESC LIMIT 1) r ON true
         WHERE h.status = 'CONFIRMED_OBSERVATIONAL'),
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
                 'run_id', r.run_id,          -- REQ-TIER-042: the job that performed it
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
