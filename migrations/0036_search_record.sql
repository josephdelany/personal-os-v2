-- 0036_search_record.sql — THE RECORD search (ADR-0042, THE_FILE §2)
-- Built under docs/build/B3_search_record.md (session 17, 2026-09-02). DISCOVER confirmed:
-- pg_trgm lives in schema `extensions`; public.events carries title/domain (chrome_visit),
-- title/channel (youtube_watch), summary|title (calendar); public.checkins has type + note.
-- No branch was dropped. Coordinates and the location schema are never searched (ADR-0042).
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

-- Trigram indexes on the searched text. Expression indexes on jsonb text keys.
CREATE INDEX IF NOT EXISTS events_title_trgm    ON public.events USING gin ((payload->>'title')   extensions.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS events_domain_trgm   ON public.events USING gin ((payload->>'domain')  extensions.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS events_channel_trgm  ON public.events USING gin ((payload->>'channel') extensions.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS tx_merchant_trgm     ON public.transactions USING gin (merchant extensions.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS atoms_evidence_trgm  ON __CORE__.atoms USING gin (evidence_span extensions.gin_trgm_ops);

CREATE OR REPLACE FUNCTION public.search_record(p_q text, p_limit int DEFAULT 50)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb; q text; lim int;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    q := trim(coalesce(p_q, ''));
    IF length(q) < 2 THEN
        RETURN jsonb_build_object('q', q, 'n', 0, 'hits', '[]'::jsonb, 'by_month', '[]'::jsonb,
                                  'note', 'Type at least two characters.');
    END IF;
    lim := least(greatest(coalesce(p_limit, 50), 1), 200);
    WITH hits AS (
        SELECT ts, 'web' AS kind,
               coalesce(payload->>'title','') || ' — ' || coalesce(payload->>'domain','') AS text,
               'chrome' AS src, id::text AS row_id
          FROM public.events WHERE kind='chrome_visit'
           AND (payload->>'title' ILIKE '%'||q||'%' OR payload->>'domain' ILIKE '%'||q||'%')
        UNION ALL
        SELECT ts, 'video', coalesce(payload->>'title','') || ' — ' || coalesce(payload->>'channel',''),
               'youtube', id::text
          FROM public.events WHERE kind='youtube_watch'
           AND (payload->>'title' ILIKE '%'||q||'%' OR payload->>'channel' ILIKE '%'||q||'%')
        UNION ALL
        SELECT ts, 'calendar', coalesce(payload->>'summary', payload->>'title', 'event'), 'calendar', id::text
          FROM public.events WHERE kind='calendar'
           AND coalesce(payload->>'summary', payload->>'title', '') ILIKE '%'||q||'%'
        UNION ALL
        SELECT ts, 'money', coalesce(merchant,'?') || ' · $' || round(abs(amount)::numeric,2)::text
               || coalesce(' ('||category||')',''), 'transactions', id::text
          FROM public.transactions
         WHERE merchant ILIKE '%'||q||'%' OR category ILIKE '%'||q||'%'
        UNION ALL
        SELECT ts, 'checkin', type || ' check-in' || coalesce(': "'||left(note,80)||'"',''), 'checkins', id::text
          FROM public.checkins WHERE note ILIKE '%'||q||'%'
        UNION ALL
        SELECT a.occurred_at, a.kind,
               coalesce(a.evidence_span,'') ||
               CASE WHEN a.value_point IS NOT NULL THEN ' ('||a.value_point||coalesce(' '||a.unit,'')||')' ELSE '' END,
               'atoms', a.id::text
          FROM __CORE__.atoms_current a
         WHERE a.evidence_span ILIKE '%'||q||'%'
    )
    SELECT jsonb_build_object(
        'q', q,
        'n', (SELECT count(*) FROM hits),
        'hits', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                    'day', ((ts AT TIME ZONE 'America/New_York') - interval '4 hours')::date,   -- subject day (ADR-0019)
                    'at', to_char(ts AT TIME ZONE 'America/New_York', 'HH24:MI'),
                    'kind', kind, 'text', left(text, 160), 'src', src, 'row_id', row_id)
                  ORDER BY ts DESC), '[]'::jsonb)
                   FROM (SELECT * FROM hits ORDER BY ts DESC LIMIT lim) h),
        'by_month', (SELECT coalesce(jsonb_agg(jsonb_build_object('month', m, 'n', n) ORDER BY m), '[]'::jsonb)
                       FROM (SELECT to_char(date_trunc('month', ts AT TIME ZONE 'America/New_York'), 'YYYY-MM') AS m, count(*) AS n
                               FROM hits GROUP BY 1) g),
        'truncated', (SELECT count(*) FROM hits) > lim)
    INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.search_record(text, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.search_record(text, int) FROM anon;
GRANT EXECUTE ON FUNCTION public.search_record(text, int) TO authenticated;
