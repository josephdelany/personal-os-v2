-- 0042_hypothesis_resolutions.sql — the watch resolver's ledger + get_findings history (ADR-0048)
-- Built under docs/build/B7_resolve_watches.md (session 18, 2026-09-02).
-- REQ-TIER-043: every status change on a registered hypothesis is recorded, by name, with its
-- reason, and surfaced. REQ-INF-103: the register's pre-registration columns stay frozen (0012
-- trigger); the resolver (tools/engines/resolve.py) UPDATEs `status` only. RULE-02 posture: this
-- ledger is append-only — the 0012 statement-level mutation-rejecting trigger is attached, so even
-- the owner cannot UPDATE/DELETE/TRUNCATE it.

CREATE TABLE IF NOT EXISTS __CORE__.hypothesis_resolutions (
    resolution_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis_id        TEXT NOT NULL REFERENCES __CORE__.hypothesis_register(hypothesis_id),
    resolved_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    status_from          TEXT NOT NULL,
    status_to            TEXT NOT NULL,
    reason               TEXT NOT NULL CHECK (reason IN (
                             'confirmed_same_sign_q_lt_0_10', 'refuted_opposite_sign_q_lt_0_10',
                             'insufficient_window_too_short', 'insufficient_low_n_eff',
                             'insufficient_sign_unstable', 'expired_no_decision_120d')),
    post_days            INTEGER NOT NULL,       -- paired days with both metrics after confirmation_data_from
    n_hi                 INTEGER,
    n_lo                 INTEGER,
    delta                NUMERIC,
    p_raw                NUMERIC,
    q_fdr                NUMERIC,
    registered_direction TEXT NOT NULL,
    observed_direction   TEXT,
    code_version         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS hypothesis_resolutions_hyp_idx
    ON __CORE__.hypothesis_resolutions (hypothesis_id, resolved_at DESC);
COMMENT ON TABLE __CORE__.hypothesis_resolutions IS
  'ADR-0048 / REQ-TIER-043. Append-only ledger of every hypothesis status change written by the '
  'watch resolver (resolve-v1). One row per change; reason is a closed set; statistics are the '
  'post-registration contrast that decided it.';

ALTER TABLE __CORE__.hypothesis_resolutions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.hypothesis_resolutions FROM anon, authenticated;
REVOKE UPDATE, DELETE ON __CORE__.hypothesis_resolutions FROM anon, authenticated, service_role;

DROP TRIGGER IF EXISTS hypothesis_resolutions_append_only ON __CORE__.hypothesis_resolutions;
CREATE TRIGGER hypothesis_resolutions_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.hypothesis_resolutions
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

-- get_findings (0041, ADR-0047) extended additively: a `history` list (last 50 resolutions, newest
-- first, each with tier + trace), and an expired watch (a ledger row with reason
-- expired_no_decision_120d) leaves `watching` and is listed under `insufficient` with its reason —
-- otherwise an expired watch would show "day N of 30" forever. No field renamed or removed.
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
                             ORDER BY r.resolved_at DESC LIMIT 1),
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
                 'resolved_at', r.resolved_at, 'status_from', r.status_from, 'status_to', r.status_to,
                 'reason', r.reason, 'post_days', r.post_days,
                 'delta', round(r.delta, 4), 'q_fdr', round(r.q_fdr, 4),
                 'trace', jsonb_build_object('table','core.hypothesis_resolutions','resolution_id',r.resolution_id))
               ORDER BY r.resolved_at DESC)
          FROM (SELECT * FROM __CORE__.hypothesis_resolutions ORDER BY resolved_at DESC LIMIT 50) r),
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
