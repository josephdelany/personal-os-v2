-- 0024_owner_lock.sql — reads are OWNER-ONLY, not merely authenticated.
-- Supabase allows open signups by default, so 'authenticated' alone would let a
-- stranger who signs up read personal data. Both read RPCs now verify the
-- session's email is Joe's. Write path unchanged (append-only anon ingress).

CREATE OR REPLACE FUNCTION public.get_day(p_day date DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE d date; out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := coalesce(p_day, (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date);
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'day', d,
      'checkin', (SELECT jsonb_object_agg(a.metric_key, jsonb_build_object(
                 'point', a.value_point, 'low', a.value_low, 'high', a.value_high, 'atom_id', a.id))
          FROM __CORE__.atoms_current a
         WHERE a.subject_day = d AND a.kind='self_report' AND a.metric_key LIKE 'checkin_%'),
      'food', (SELECT jsonb_agg(jsonb_build_object('label', a.evidence_span, 'at', a.occurred_at,
                 'precision', a.time_precision, 'atom_id', a.id) ORDER BY a.occurred_at)
          FROM __CORE__.atoms_current a WHERE a.subject_day = d AND a.kind='consume'),
      'notes', (SELECT jsonb_agg(jsonb_build_object('text', a.evidence_span, 'at', a.occurred_at,
                 'atom_id', a.id) ORDER BY a.occurred_at)
          FROM __CORE__.atoms_current a WHERE a.subject_day = d AND a.kind='note'),
      'workout', (SELECT jsonb_agg(jsonb_build_object('metric', a.metric_key, 'value', a.value_point,
                 'exercise', a.evidence_span, 'at', a.occurred_at, 'atom_id', a.id) ORDER BY a.occurred_at)
          FROM __CORE__.atoms_current a WHERE a.subject_day = d AND a.kind='workout'),
      'health', (SELECT jsonb_agg(jsonb_build_object('metric', a.metric_key, 'value', a.value_point,
                 'atom_id', a.id) ORDER BY a.metric_key)
          FROM __CORE__.atoms_current a
         WHERE a.subject_day = d AND a.kind IN ('vital_sample','activity_sample','sleep','heart_rate_variability','body_measurement')),
      'coverage', jsonb_build_object(
        'captures', (SELECT count(*) FROM __CORE__.raw_captures rc
                      WHERE rc.captured_at >= (d::timestamptz + interval '4 hours')
                        AND rc.captured_at <  (d::timestamptz + interval '28 hours')),
        'atoms', (SELECT count(*) FROM __CORE__.atoms a WHERE a.subject_day = d),
        'unextracted', (SELECT count(*) FROM __CORE__.raw_captures rc
                         WHERE rc.payload->>'kind' IN ('checkin','food','workout','health')
                           AND NOT EXISTS (SELECT 1 FROM __CORE__.atoms a WHERE a.raw_capture_id = rc.capture_id))),
      'last_extract_run', (SELECT jsonb_build_object('at', r.started_at, 'status', r.status)
          FROM __OPS__.runs r WHERE r.job_name='extract_checkins' ORDER BY r.started_at DESC LIMIT 1)
    )) INTO out;
    RETURN out;
END $fn$;

-- get_insights: same owner check, body unchanged from 0023 otherwise
CREATE OR REPLACE FUNCTION public.get_insights_guarded()
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    RETURN public.get_insights();
END $fn$;
REVOKE ALL ON FUNCTION public.get_insights() FROM authenticated;  -- only via the guard now
REVOKE ALL ON FUNCTION public.get_insights_guarded() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_insights_guarded() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_insights_guarded() TO authenticated;
