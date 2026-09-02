-- 0029_timeline_api.sql — E1: any day of your life, minute-ordered (ADR-0038)
-- Owner-locked (0024 pattern). Sources every timestamped record: browsing,
-- YouTube (channel+title), transactions, calendar, check-ins (legacy + spine),
-- meals/notes/sets (atoms). Sleep rendered as a wake-anchored entry when known.

CREATE OR REPLACE FUNCTION public.get_timeline(p_day date)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE t0 timestamptz; t1 timestamptz; out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    t0 := (p_day::timestamptz + interval '4 hours');   -- subject-day window (ADR-0019)
    t1 := t0 + interval '24 hours';
    WITH entries AS (
        SELECT ts, 'web' AS kind,
               coalesce(payload->>'title','') || ' — ' || coalesce(payload->>'domain','') AS text,
               'chrome' AS src, id::text AS row_id
          FROM public.events WHERE kind='chrome_visit' AND ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'video',
               coalesce(payload->>'title','') || ' — ' || coalesce(payload->>'channel',''),
               'youtube', id::text
          FROM public.events WHERE kind='youtube_watch' AND ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'calendar', coalesce(payload->>'summary', payload->>'title', 'event'),
               'calendar', id::text
          FROM public.events WHERE kind='calendar' AND ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'money',
               coalesce(merchant,'?') || ' · $' || round(abs(amount)::numeric,2)::text
               || coalesce(' ('||category||')',''),
               'transactions', id::text
          FROM public.transactions WHERE ts >= t0 AND ts < t1
        UNION ALL
        SELECT ts, 'checkin',
               type || ' check-in' || coalesce(': "'||left(note,80)||'"',''),
               'checkins', id::text
          FROM public.checkins WHERE ts >= t0 AND ts < t1
        UNION ALL
        SELECT a.occurred_at, a.kind,
               coalesce(a.evidence_span,'') ||
               CASE WHEN a.value_point IS NOT NULL
                    THEN ' ('||a.value_point||coalesce(' '||a.unit,'')||')' ELSE '' END,
               'atoms', a.id::text
          FROM core.atoms_current a
         WHERE a.occurred_at >= t0 AND a.occurred_at < t1
           AND a.kind IN ('consume','note','workout','self_report')
    )
    SELECT jsonb_build_object(
        'day', p_day,
        'sleep', (SELECT jsonb_build_object('asleep_min', value)
                    FROM analysis.panel WHERE day = p_day AND metric='sleep_asleep_min'),
        'n', (SELECT count(*) FROM entries),
        'entries', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                        'at', to_char(ts AT TIME ZONE 'America/New_York', 'HH24:MI'),
                        'kind', kind, 'text', left(text, 160),
                        'src', src, 'row_id', row_id) ORDER BY ts), '[]'::jsonb)
                      FROM entries))
    INTO out;
    RETURN out;
END $fn$;

REVOKE ALL ON FUNCTION public.get_timeline(date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_timeline(date) FROM anon;
GRANT EXECUTE ON FUNCTION public.get_timeline(date) TO authenticated;
