-- 0043_resolver_two_looks.sql — the two-look ruling (Joe, 2026-09-02, OQ-44(d); ADR-0048 §12)
-- The resolver looks at a watch exactly twice (first night >= 30 paired days; once more at 120)
-- and every look writes a ledger row, so a look is never repeated. Each look stores which look
-- it was, the Kish effective sample size it was gated on (REQ-TIER-017 floor 20; RULE-21: no n
-- without n_eff) and the outcome's lag-1 rho that deflated it. Additive; nothing renamed.
ALTER TABLE __CORE__.hypothesis_resolutions
    ADD COLUMN IF NOT EXISTS look        SMALLINT CHECK (look IN (1, 2)),
    ADD COLUMN IF NOT EXISTS n_eff       NUMERIC,
    ADD COLUMN IF NOT EXISTS rho_outcome NUMERIC;
COMMENT ON COLUMN __CORE__.hypothesis_resolutions.n_eff IS
  'Kish effective sample size of the paired post-registration window: post_days*(1-rho)/(1+rho), rho deflating only. Gated at 20 (REQ-TIER-017, ADR-0048 §12).';

-- get_findings.history: add look and n_eff (RULE-21: a surface reporting n reports n_eff). Additive.
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
                 'hypothesis_id', h.hypothesis_id, 'tier', 'WATCHING',
                 'source', replace(h.hypothesis_id, 'watch:', ''),
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'direction', h.direction, 'registered_at', h.preregistered_at::date,
                 'data_from', h.confirmation_data_from::date,
                 'days_elapsed', current_date - h.preregistered_at::date, 'days_needed', 30,
                 'looks_done', (SELECT count(*) FROM __CORE__.hypothesis_resolutions r
                                 WHERE r.hypothesis_id = h.hypothesis_id
                                   AND r.reason IN ('insufficient_low_n_eff','insufficient_sign_unstable')),
                 'resolution_rule', h.resolution_rule, 'status', h.status,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h
         WHERE h.hypothesis_id LIKE 'watch:%' AND h.status IN ('INSUFFICIENT','PROMOTED')
           AND NOT EXISTS (SELECT 1 FROM __CORE__.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id
                              AND r.reason = 'expired_no_decision_120d')),
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
                 'reason', r.reason, 'look', r.look, 'post_days', r.post_days,
                 'n_eff', r.n_eff, 'family_m', r.family_m,
                 'delta', round(r.delta, 4), 'q_fdr', round(r.q_fdr, 4),
                 'trace', jsonb_build_object('table','core.hypothesis_resolutions','resolution_id',r.resolution_id))
               ORDER BY r.resolved_at DESC, r.resolution_id)
          FROM (SELECT * FROM __CORE__.hypothesis_resolutions ORDER BY resolved_at DESC, resolution_id LIMIT 50) r
          JOIN __CORE__.hypothesis_register h ON h.hypothesis_id = r.hypothesis_id),
      'counts', (
        SELECT jsonb_build_object(
            'candidates', count(*) FILTER (WHERE status='CANDIDATE'),
            'watching',   count(*) FILTER (WHERE hypothesis_id LIKE 'watch:%' AND status IN ('INSUFFICIENT','PROMOTED')
                                             AND NOT EXISTS (SELECT 1 FROM __CORE__.hypothesis_resolutions r
                                                              WHERE r.hypothesis_id = h.hypothesis_id
                                                                AND r.reason = 'expired_no_decision_120d')),
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
