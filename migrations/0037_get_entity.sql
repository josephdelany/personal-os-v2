-- 0037_get_entity.sql — the entity page (ADR-0043, THE_FILE §4 module 8)
-- Built under docs/build/B4_get_entity.md (session 17, 2026-09-02).
-- __EXERCISE_EXPR__ = evidence_span (ADR-0041 (c): the workout extractor stores the exercise name
-- verbatim in evidence_span on each per-attribute atom). `place` returns the refusal until B5.
CREATE OR REPLACE FUNCTION public.get_entity(p_type text, p_key text)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb; d date;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1;
    IF p_type NOT IN ('merchant','category','site','channel','exercise','place') THEN
        RETURN jsonb_build_object('refusal', 'I do not track that.',
                                  'nearest', jsonb_build_array('merchant','category','site','channel','exercise','place'));
    END IF;
    IF p_type = 'place' THEN
        RETURN jsonb_build_object('refusal', 'I do not track that.', 'note', 'places arrive with build B5');
    END IF;

    WITH rows AS (
        SELECT ts, abs(amount) AS amt, id::text AS row_id, 'transactions' AS src,
               coalesce(merchant,'?') || ' · $' || round(abs(amount)::numeric,2)::text || coalesce(' ('||category||')','') AS text
          FROM public.transactions
         WHERE p_type = 'merchant' AND merchant = p_key AND ts < (d+1)::timestamptz
        UNION ALL
        SELECT ts, abs(amount), id::text, 'transactions',
               coalesce(merchant,'?') || ' · $' || round(abs(amount)::numeric,2)::text
          FROM public.transactions
         WHERE p_type = 'category' AND category = p_key AND ts < (d+1)::timestamptz
        UNION ALL
        SELECT ts, NULL, id::text, 'chrome', coalesce(payload->>'title','')
          FROM public.events
         WHERE p_type = 'site' AND kind = 'chrome_visit' AND payload->>'domain' = p_key AND ts < (d+1)::timestamptz
        UNION ALL
        SELECT ts, NULL, id::text, 'youtube', coalesce(payload->>'title','')
          FROM public.events
         WHERE p_type = 'channel' AND kind = 'youtube_watch' AND payload->>'channel' = p_key AND ts < (d+1)::timestamptz
        UNION ALL
        SELECT a.occurred_at, NULL, a.id::text, 'atoms',
               coalesce(a.evidence_span,'') || CASE WHEN a.value_point IS NOT NULL
                    THEN ' ('||a.value_point||coalesce(' '||a.unit,'')||')' ELSE '' END
          FROM __CORE__.atoms_current a
         WHERE p_type = 'exercise' AND a.kind = 'workout' AND a.evidence_span = p_key   -- same expression as B2 module 8
           AND a.subject_day <= d
    ),
    agg AS (SELECT count(*) AS n, min(ts) AS first_ts, max(ts) AS last_ts,
                   count(*) FILTER (WHERE ts >= (d-89)::timestamptz) AS n_90d,
                   sum(amt) AS amount_total,
                   sum(amt) FILTER (WHERE ts >= (d-89)::timestamptz) AS amount_90d
              FROM rows)
    SELECT jsonb_strip_nulls(jsonb_build_object(
        'type', p_type, 'key', p_key, 'as_of', d,
        'n', agg.n,
        'first_seen', agg.first_ts::date, 'last_seen', agg.last_ts::date,
        'days_since_last', CASE WHEN agg.last_ts IS NULL THEN NULL ELSE d - agg.last_ts::date END,
        'n_90d', agg.n_90d,
        'amount_total', round(agg.amount_total::numeric, 2),
        'amount_90d', round(agg.amount_90d::numeric, 2),
        'unit', CASE WHEN p_type IN ('merchant','category') THEN '$' ELSE 'events' END,
        'by_month', (SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object('month', m, 'n', n, 'amount', a)) ORDER BY m)
                       FROM (SELECT to_char(date_trunc('month', ts AT TIME ZONE 'America/New_York'),'YYYY-MM') AS m,
                                    count(*) AS n, round(sum(amt)::numeric,2) AS a FROM rows GROUP BY 1) g),
        'by_weekday', (SELECT jsonb_agg(jsonb_build_object('dow', dow, 'n', n) ORDER BY dow)
                         FROM (SELECT extract(isodow FROM ts AT TIME ZONE 'America/New_York')::int AS dow, count(*) AS n
                                 FROM rows GROUP BY 1) g),
        'by_hour', (SELECT jsonb_agg(jsonb_build_object('hour', h, 'n', n) ORDER BY h)
                      FROM (SELECT extract(hour FROM ts AT TIME ZONE 'America/New_York')::int AS h, count(*) AS n
                              FROM rows GROUP BY 1) g),
        'recent', (SELECT jsonb_agg(jsonb_build_object(
                        'day', ((ts AT TIME ZONE 'America/New_York') - interval '4 hours')::date,
                        'at', to_char(ts AT TIME ZONE 'America/New_York','HH24:MI'),
                        'text', left(text,160), 'src', src, 'row_id', row_id) ORDER BY ts DESC)
                     FROM (SELECT * FROM rows ORDER BY ts DESC LIMIT 20) r),
        'trace', jsonb_build_object('tables', CASE p_type
                    WHEN 'merchant' THEN 'public.transactions' WHEN 'category' THEN 'public.transactions'
                    WHEN 'site' THEN 'public.events' WHEN 'channel' THEN 'public.events'
                    ELSE 'core.atoms_current' END, 'key', jsonb_build_object('type', p_type, 'key', p_key))
    )) INTO out FROM agg;
    IF (out->>'n')::int = 0 THEN
        RETURN jsonb_build_object('type', p_type, 'key', p_key, 'as_of', d, 'n', 0,
                                  'note', 'Nothing recorded for this ' || p_type || '.');
    END IF;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_entity(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_entity(text, text) FROM anon;
GRANT EXECUTE ON FUNCTION public.get_entity(text, text) TO authenticated;
