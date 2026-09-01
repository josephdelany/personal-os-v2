-- 0021_read_api_get_day.sql — the front end's read API (ADR-0036)
--
-- One RPC returns one day's honest envelope. ADR-0020: no generic SQL reaches a
-- client — only parameterised, schema-validated, read-only RPCs. Every numeral in
-- the envelope carries its atom_id, so the renderer can satisfy INV-3/RULE-14
-- (no numeral without a stored computation/observation behind it) and a click-
-- through audit is one lookup. Self-report scores ship as their coarsened
-- INTERVALS (low/point/high), never as false-precision points (ADR-0018/RULE-08).
--
-- SECURITY: EXECUTE for `authenticated` ONLY (the signed-in owner via Supabase
-- Auth magic-link). anon gets NOTHING — personal data is never publicly readable.
-- SECURITY DEFINER + empty search_path, same hardening as 0017/0018/0020.

CREATE OR REPLACE FUNCTION public.get_day(p_day date DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $fn$
DECLARE
    d    date;
    out  jsonb;
BEGIN
    -- default: today on the subject-day clock (04:00 ET boundary, ADR-0019)
    d := coalesce(p_day,
                  (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date);

    SELECT jsonb_strip_nulls(jsonb_build_object(
      'day', d,
      'checkin', (
        SELECT jsonb_object_agg(a.metric_key, jsonb_build_object(
                 'point', a.value_point, 'low', a.value_low, 'high', a.value_high,
                 'atom_id', a.id))
          FROM __CORE__.atoms_current a
         WHERE a.subject_day = d AND a.kind = 'self_report'
           AND a.metric_key LIKE 'checkin_%'),
      'food', (
        SELECT jsonb_agg(jsonb_build_object(
                 'label', a.evidence_span, 'at', a.occurred_at,
                 'precision', a.time_precision, 'atom_id', a.id)
               ORDER BY a.occurred_at)
          FROM __CORE__.atoms_current a
         WHERE a.subject_day = d AND a.kind = 'consume'),
      'notes', (
        SELECT jsonb_agg(jsonb_build_object(
                 'text', a.evidence_span, 'at', a.occurred_at, 'atom_id', a.id)
               ORDER BY a.occurred_at)
          FROM __CORE__.atoms_current a
         WHERE a.subject_day = d AND a.kind = 'note'),
      'coverage', jsonb_build_object(
        'captures',    (SELECT count(*) FROM __CORE__.raw_captures rc
                         WHERE rc.captured_at >= (d::timestamptz + interval '4 hours')
                           AND rc.captured_at <  (d::timestamptz + interval '28 hours')),
        'atoms',       (SELECT count(*) FROM __CORE__.atoms a WHERE a.subject_day = d),
        'unextracted', (SELECT count(*) FROM __CORE__.raw_captures rc
                         WHERE rc.payload->>'kind' IN ('checkin','food')
                           AND NOT EXISTS (SELECT 1 FROM __CORE__.atoms a
                                            WHERE a.raw_capture_id = rc.capture_id))),
      'last_extract_run', (
        SELECT jsonb_build_object('at', r.started_at, 'status', r.status)
          FROM __OPS__.runs r WHERE r.job_name = 'extract_checkins'
         ORDER BY r.started_at DESC LIMIT 1)
    )) INTO out;
    RETURN out;
END
$fn$;

REVOKE ALL ON FUNCTION public.get_day(date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_day(date) FROM anon;
GRANT  EXECUTE ON FUNCTION public.get_day(date) TO authenticated;

COMMENT ON FUNCTION public.get_day(date) IS
  'ADR-0036: the daily read envelope. authenticated-only (never anon). Every '
  'numeral carries its atom_id (INV-3/RULE-14); self-reports ship as coarsened '
  'intervals (ADR-0018). Fields get added, never renamed.';
