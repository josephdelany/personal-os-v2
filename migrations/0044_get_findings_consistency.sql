-- 0044_get_findings_consistency.sql — get_findings after the session-19 adversarial review (ADR-0048 §13)
-- Findings fixed here: `looks_done` now comes from the ledger's `look` column (one definition, not a
-- hand-copied reason list); a PROMOTED watch leaves `watching` (its tier is PROMOTED, one of RULE-16's six)
-- and gets its own `promoted` list, with a note that it is not a causal claim; `days_needed` is the paired
-- days to the NEXT look (30, then 120), not a fixed 30; a watch on the clock reports
-- `insufficiency_reason: window_too_short` (REQ-INF-107); `history` rows carry `status_changed` so a look
-- record is distinguishable from a status change. Additive: no field renamed or removed; `counts` keys
-- unchanged (B6 contract) — `counts.watching` now excludes PROMOTED like the list it counts.
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
                 'days_elapsed', current_date - h.preregistered_at::date,
                 'days_needed', CASE WHEN lk.looks_done = 0 THEN 30 ELSE 120 END,   -- paired days to the NEXT look (ADR-0048 §12)
                 'looks_done', lk.looks_done,
                 'insufficiency_reason', CASE WHEN lk.looks_done = 0 THEN 'window_too_short' END,   -- REQ-INF-107
                 'last_look_reason', lk.last_reason,
                 'resolution_rule', h.resolution_rule, 'status', h.status,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM __CORE__.hypothesis_register h
          CROSS JOIN LATERAL (
            SELECT coalesce(max(r.look), 0) AS looks_done,
                   (SELECT r2.reason FROM __CORE__.hypothesis_resolutions r2
                     WHERE r2.hypothesis_id = h.hypothesis_id
                     ORDER BY r2.resolved_at DESC, r2.resolution_id LIMIT 1) AS last_reason
              FROM __CORE__.hypothesis_resolutions r
             WHERE r.hypothesis_id = h.hypothesis_id
               AND r.reason IN ('insufficient_low_n_eff','insufficient_sign_unstable')) lk
         WHERE h.hypothesis_id LIKE 'watch:%' AND h.status = 'INSUFFICIENT'
           AND NOT EXISTS (SELECT 1 FROM __CORE__.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id
                              AND r.reason = 'expired_no_decision_120d')),
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
                 'reason', r.reason, 'look', r.look, 'post_days', r.post_days,
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
            'watching',   count(*) FILTER (WHERE hypothesis_id LIKE 'watch:%' AND status = 'INSUFFICIENT'
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
