-- 0040_movements_api.sql — MOVEMENTS read API: get_movements / get_place / get_places; get_entity(place) rewired
-- (ADR-0046 with ADR-0044/0045; REQ-LOC-002/003/007/012/013/015/016/017/018). Built under
-- docs/build/B5_movements.md §B5.3 (session 17, 2026-09-02). Labels, minutes and aggregates cross the
-- boundary; a coordinate never does. Deviations from B5's text, recorded in ADR-0046:
--   (a) get_places is plpgsql with the RAISE pattern (B5's sql sketch returned NULL for a non-owner).
--   (b) get_entity(place) casts the key to uuid inside an exception block so a non-uuid key returns the
--       REQ-ASK-003 refusal instead of a cast error.

-- ---------- get_movements(p_day): labels, minutes, aggregates. Never a coordinate. ----------
CREATE OR REPLACE FUNCTION public.get_movements(p_day date DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE d date; today date; out jsonb; t0 timestamptz; t1 timestamptz;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN RAISE EXCEPTION 'owner only'; END IF;
    today := (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date;
    d := coalesce(p_day, today);
    t0 := d::timestamptz + interval '4 hours'; t1 := t0 + interval '24 hours';
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'day', d, 'tier', 'DESCRIPTIVE', 'provisional', true,                      -- REQ-LOC-013/017
      'coverage', (SELECT jsonb_build_object(
            'fixes', count(*), 'first_fix_at', to_char(min(captured_at) AT TIME ZONE 'America/New_York','HH24:MI'),
            'last_fix_at', to_char(max(captured_at) AT TIME ZONE 'America/New_York','HH24:MI'),
            'longest_gap_min', (SELECT round(max(extract(epoch FROM gap))/60)
                                  FROM (SELECT captured_at - lag(captured_at) OVER (ORDER BY captured_at) AS gap
                                          FROM restricted.location_fixes WHERE captured_at >= t0 AND captured_at < t1) g),
            'status', CASE WHEN count(*) = 0 THEN 'none'
                           WHEN count(*) < 24 THEN 'partial' ELSE 'fresh' END)
          FROM restricted.location_fixes WHERE captured_at >= t0 AND captured_at < t1),
      'last_known', CASE WHEN d <> today THEN NULL ELSE (
          SELECT jsonb_build_object('label', coalesce(v.label, 'unknown place'), 'kind', v.kind,
                                    'at', to_char(v.depart_at AT TIME ZONE 'America/New_York','HH24:MI'),
                                    'minutes_ago', round(extract(epoch FROM now() - v.depart_at)/60))
            FROM analysis.visits_public v ORDER BY v.depart_at DESC LIMIT 1) END,
      'visits', (SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                    'visit_id', v.visit_id, 'label', coalesce(v.label, 'unknown place'), 'kind', v.kind,
                    'is_home', v.is_home, 'place_id', v.place_id,
                    'arrive', to_char(v.arrive_at AT TIME ZONE 'America/New_York','HH24:MI'),
                    'depart', to_char(v.depart_at AT TIME ZONE 'America/New_York','HH24:MI'),
                    'dwell_min', round(v.dwell_min), 'n_fixes', v.n_fixes,
                    'trace', jsonb_build_object('table','analysis.visits_public','visit_id',v.visit_id,'code_version',v.code_version)))
                  ORDER BY v.arrive_at)
                   FROM analysis.visits_public v WHERE v.subject_day = d),
      'unknown_visits', (SELECT count(*) FROM analysis.visits_public v WHERE v.subject_day = d AND v.place_id IS NULL),
      'mobility', (SELECT jsonb_strip_nulls(jsonb_build_object(
            'distinct_places', count(DISTINCT v.place_id),
            'home_min', round(sum(v.dwell_min) FILTER (WHERE v.is_home)),
            'away_min', round(sum(v.dwell_min) FILTER (WHERE NOT coalesce(v.is_home,false))),
            'first_leave', to_char(min(v.arrive_at) FILTER (WHERE NOT coalesce(v.is_home,false)) AT TIME ZONE 'America/New_York','HH24:MI'),
            'last_return', to_char(max(v.arrive_at) FILTER (WHERE v.is_home) AT TIME ZONE 'America/New_York','HH24:MI'),
            'trips', greatest(count(*) - 1, 0),
            'radius_of_gyration_km', (SELECT round((sqrt(avg(power(restricted.dist_m(lat, lon, avg_lat, avg_lon),2)))/1000)::numeric, 1)
                                        FROM restricted.location_fixes, (SELECT avg(lat) avg_lat, avg(lon) avg_lon
                                               FROM restricted.location_fixes WHERE captured_at >= t0 AND captured_at < t1) c
                                       WHERE captured_at >= t0 AND captured_at < t1),
            'window', 'subject_day'))
          FROM analysis.visits_public v WHERE v.subject_day = d
        HAVING count(*) > 0)
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_movements(date) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_movements(date) TO authenticated;

-- ---------- get_place(p_place_id) ----------
CREATE OR REPLACE FUNCTION public.get_place(p_place_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE out jsonb; d date;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN RAISE EXCEPTION 'owner only'; END IF;
    d := (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date;
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'place_id', p.place_id, 'label', p.label, 'kind', p.kind, 'is_home', p.is_home, 'tier', 'DESCRIPTIVE',
      'visits_n', (SELECT count(*) FROM analysis.visits_public v WHERE v.place_id = p.place_id),
      'first_visit', (SELECT min(subject_day) FROM analysis.visits_public v WHERE v.place_id = p.place_id),
      'last_visit',  (SELECT max(subject_day) FROM analysis.visits_public v WHERE v.place_id = p.place_id),
      'dwell_total_min',  (SELECT round(sum(dwell_min)) FROM analysis.visits_public v WHERE v.place_id = p.place_id),
      'dwell_median_min', (SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY dwell_min)) FROM analysis.visits_public v WHERE v.place_id = p.place_id),
      'by_weekday', (SELECT jsonb_agg(jsonb_build_object('dow', dow, 'n', n) ORDER BY dow)
                       FROM (SELECT extract(isodow FROM arrive_at AT TIME ZONE 'America/New_York')::int dow, count(*) n
                               FROM analysis.visits_public v WHERE v.place_id = p.place_id GROUP BY 1) g),
      'by_arrival_hour', (SELECT jsonb_agg(jsonb_build_object('hour', h, 'n', n) ORDER BY h)
                            FROM (SELECT extract(hour FROM arrive_at AT TIME ZONE 'America/New_York')::int h, count(*) n
                                    FROM analysis.visits_public v WHERE v.place_id = p.place_id GROUP BY 1) g),
      'recent', (SELECT jsonb_agg(jsonb_build_object('day', subject_day,
                    'arrive', to_char(arrive_at AT TIME ZONE 'America/New_York','HH24:MI'),
                    'depart', to_char(depart_at AT TIME ZONE 'America/New_York','HH24:MI'),
                    'dwell_min', round(dwell_min), 'visit_id', visit_id) ORDER BY arrive_at DESC)
                   FROM (SELECT * FROM analysis.visits_public v WHERE v.place_id = p.place_id ORDER BY arrive_at DESC LIMIT 20) r),
      -- money at this place: transactions whose timestamp falls inside a visit here
      'money_here', (SELECT jsonb_agg(jsonb_build_object('merchant', merchant, 'n', n, 'amount', amt) ORDER BY amt DESC)
                       FROM (SELECT coalesce(t.merchant,'?') merchant, count(*) n, round(sum(abs(t.amount))::numeric,2) amt
                               FROM public.transactions t
                               JOIN analysis.visits_public v ON v.place_id = p.place_id
                                AND t.ts >= v.arrive_at - interval '15 minutes' AND t.ts <= v.depart_at + interval '15 minutes'
                              GROUP BY 1 ORDER BY amt DESC LIMIT 10) m),
      'trace', jsonb_build_object('table','analysis.visits_public','place_id',p.place_id)
    )) INTO out
      FROM restricted.places_current p WHERE p.place_id = p_place_id;
    IF out IS NULL THEN RETURN jsonb_build_object('refusal','I do not track that.'); END IF;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_place(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_place(uuid) TO authenticated;

-- ---------- get_places(): the places register for THE DESK / MOVEMENTS — labels only ----------
CREATE OR REPLACE FUNCTION public.get_places()
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE out jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN RAISE EXCEPTION 'owner only'; END IF;
    SELECT jsonb_build_object('places', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'place_id', p.place_id, 'label', p.label, 'kind', p.kind, 'is_home', p.is_home,
        'visits_n', (SELECT count(*) FROM analysis.visits_public v WHERE v.place_id = p.place_id),
        'last_visit', (SELECT max(subject_day) FROM analysis.visits_public v WHERE v.place_id = p.place_id))
      ORDER BY p.is_home DESC, p.label) FROM restricted.places_current p), '[]'::jsonb))
    INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_places() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_places() TO authenticated;

-- ---------- get_entity: the place type now delegates to get_place (B4 said "until B5") ----------
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
        BEGIN
            RETURN public.get_place(p_key::uuid);                       -- B5.3: delegate (ADR-0043)
        EXCEPTION WHEN invalid_text_representation THEN
            RETURN jsonb_build_object('refusal', 'I do not track that.', 'note', 'a place key is a place_id (uuid)');
        END;
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
