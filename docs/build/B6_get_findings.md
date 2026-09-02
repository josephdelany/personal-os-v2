# B6 — `get_findings()`: the lifecycle lists (migration 0041)

**What this is.** FINDINGS §5 beyond the EXPLORATORY list: what is being WATCHED
(pre-registered tests and their clocks), what is CONFIRMED, what was REFUTED, and what
came back INSUFFICIENT — as rows, not counts. `get_trust` gives counts; `get_patterns`
gives only CANDIDATE rows (REQ-TIER-053). Nothing today lists the rest. Half a session.

**Requirement IDs satisfied:** REQ-TIER-005 (tier, n, n_eff, coverage with every claim),
REQ-TIER-023 (a CONFIRMED row carries adjustment set — here `adjustment_set` verbatim
from the register; E-value and negative control are not computed yet, so the row says
so), REQ-TIER-043 (a demotion is surfaced by name), REQ-TIER-035 (no CANDIDATE row here),
ADR-0036. **ADR to write:** ADR-0047.

## Migration `migrations/0041_get_findings.sql`

```sql
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
          FROM core.hypothesis_register h
         WHERE h.hypothesis_id LIKE 'watch:%' AND h.status IN ('INSUFFICIENT','PROMOTED')),
      'confirmed', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'CONFIRMED',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'direction', h.direction, 'adjustment_set', h.adjustment_set,
                 'e_value', NULL, 'negative_control', NULL,        -- not computed yet: absent, and the UI says so
                 'registered_at', h.preregistered_at::date,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM core.hypothesis_register h WHERE h.status = 'CONFIRMED_OBSERVATIONAL'),
      'refuted', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'REFUTED',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'registered_at', h.preregistered_at::date,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM core.hypothesis_register h WHERE h.status = 'REFUTED'),
      'insufficient', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis_id', h.hypothesis_id, 'tier', 'INSUFFICIENT',
                 'exposure', h.exposure_metric, 'outcome', h.outcome_metric, 'lag_days', h.lag_days,
                 'registered_at', h.preregistered_at::date,
                 'trace', jsonb_build_object('table','core.hypothesis_register','hypothesis_id',h.hypothesis_id))
               ORDER BY h.preregistered_at DESC)
          FROM core.hypothesis_register h
         WHERE h.status = 'INSUFFICIENT' AND h.hypothesis_id NOT LIKE 'watch:%'),
      'counts', (
        SELECT jsonb_build_object(
            'candidates', count(*) FILTER (WHERE status='CANDIDATE'),
            'watching',   count(*) FILTER (WHERE hypothesis_id LIKE 'watch:%' AND status IN ('INSUFFICIENT','PROMOTED')),
            'confirmed',  count(*) FILTER (WHERE status='CONFIRMED_OBSERVATIONAL'),
            'refuted',    count(*) FILTER (WHERE status='REFUTED'))
          FROM core.hypothesis_register),
      'predictions_pending', (
        SELECT jsonb_agg(jsonb_build_object('claim', left(p.claim_text,160), 'tier', p.evidence_tier,
                 'resolves_at', p.resolves_at::date, 'hypothesis_id', p.hypothesis_id,
                 'trace', jsonb_build_object('table','core.predictions','prediction_id',p.prediction_id))
               ORDER BY p.resolves_at)
          FROM core.predictions p
         WHERE p.outcome_bool IS NULL AND p.model_version NOT LIKE 'forecast-%')
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_findings() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_findings() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_findings() TO authenticated;
```

If `core.predictions` has no `evidence_tier`/`claim_text` as named (check
`migrations/0008_predictions.sql`), use the actual column names; do not invent.

## Tests `tests/test_get_findings.py`
```
test_ADR_0036_get_findings_refuses_without_owner_jwt
test_REQ_TIER_035_get_findings_contains_no_candidate_row   (no item anywhere with hypothesis_id whose register status is CANDIDATE)
test_REQ_TIER_005_every_item_carries_tier_and_trace
test_ADR_0047_counts_match_list_lengths_where_lists_present
test_ADR_0047_watching_days_elapsed_is_nonnegative
```

## Done when
Dry-run + apply pasted; owner call pasted; tests pass; ADR-0047; DECISIONS row; PROGRESS + WHAT I DID NOT DO (E-value / negative control not computed; no demotion history table yet, so REQ-TIER-043 is satisfied only for rows currently REFUTED).
