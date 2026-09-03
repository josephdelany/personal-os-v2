-- 0048_pending_excludes_void.sql — B10: a VOID prediction stops waiting (ADR-0052).
-- A recommendation's forward prediction is conditional ("if the driver is in your top quartile on at least
-- 7 of the next 14 days ..."). When the antecedent never happened the prediction was not tested: scoring it
-- either way would corrupt the calibration ledger, so `recommend.score_predictions` marks it void —
-- outcome_bool stays NULL, resolved_at is set, and the reason goes in feature_snapshot_hash. This teaches
-- `get_findings.predictions_pending` to stop listing a resolved-but-unscored row as pending. One clause.
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
         WHERE p.outcome_bool IS NULL AND p.resolved_at IS NULL
           AND p.model_version NOT LIKE 'forecast-%')
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_findings() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_findings() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_findings() TO authenticated;
