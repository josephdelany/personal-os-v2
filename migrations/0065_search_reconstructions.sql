-- 0065_search_reconstructions.sql — reconstructions become answerable through `ask`
-- (REQ-REC-011/012/013, INV-4, INV-5; ADR-0134).
--
-- THE GAP. `core.inferred_events` has existed since 0054 and `public.get_reconstruction` since
-- 0055, and NOTHING SURFACED THEM. `ask` had no knowledge of the table at all: a reconstruction
-- could be stored and inspected by event id, and could not be found by anyone who did not
-- already know the id. That is a stored row, not a capability.
--
-- WHY search_record RATHER THAN A NEW `ask` BRANCH. `ask` dispatches from a hardcoded chain
-- inside a 1,000-line function that has already been reproduced wholesale three times
-- (0049 -> 0058 -> 0059). Its `search` operation delegates here, so extending this function
-- reaches `public.ask` without a fourth copy. The narrower change is also the reviewable one.
--
-- WHY A THIRD ARGUMENT AND NOT A MUTATION OF THE OLD ONE. Historical replay needs a knowledge
-- bound (INV-4, REQ-REC-011), and the two-argument form is live and called. So the two-argument
-- form remains and delegates with `now()`; the three-argument form takes the bound. A caller
-- that does not ask for a replay gets today's answer, which is what it already got.
--
-- INV-5 IS THE REASON FOR EVERY FIELD BELOW. A reconstruction is NOT a measurement, and the
-- shape of the hit has to make that impossible to miss: `src` is `inferred_events`, `kind` is
-- `inferred`, `provenance` says so again, and the tier and method travel with it. A hit that
-- rendered like an atom would be an inference laundered into the record — which is the exact
-- failure REQ-REC-013 exists to prevent, arriving through the search box.

CREATE OR REPLACE FUNCTION public.search_record(p_q text, p_limit int, p_known_at timestamptz)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE q text; lim int; known timestamptz; out jsonb;
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
    known := coalesce(p_known_at, now());

    WITH hits AS (
        SELECT ts, kind, text, src, row_id, provenance, tier, method, presence FROM (
            SELECT e.ts, e.kind, e.text, e.src, e.row_id,
                   'measured'::text AS provenance, NULL::text AS tier, NULL::text AS method,
                   NULL::text AS presence
              FROM public._search_measured(q) e
            UNION ALL
            -- REQ-REC-011 / INV-4. The knowledge clock, not the event clock: a replay pinned to
            -- last Tuesday must not see a conclusion this system first reached on Wednesday.
            -- `v_current_events` is not used here because ITS head is today's head; the head as
            -- of `known` is the row that had not been superseded BY THEN.
            SELECT e.event_time_from, 'inferred'::text,
                   e.method_key || ' · ' || e.presence || ' · ' || e.tier
                     || coalesce(' · ' || e.unresolved_ambiguity, ''),
                   'inferred_events'::text, e.event_id::text,
                   'inferred'::text, e.tier, e.method_key || ' v' || e.method_version,
                   -- RULE-07's three-valued presence as its own field. It is already inside
                   -- `text` for display, but a caller that has to parse a sentence to learn
                   -- whether something is `unknown` will eventually parse it wrong, and the
                   -- failure mode is reading `unknown` as `did_not_occur`.
                   e.presence::text
              FROM __CORE__.inferred_events e
             WHERE e.knowledge_time <= known
               AND NOT EXISTS (SELECT 1 FROM __CORE__.inferred_events s
                                WHERE s.supersedes = e.event_id
                                  AND s.knowledge_time <= known)
               -- Separators are normalised on BOTH sides. `method_key` and `event_family` are
               -- snake_case identifiers; a person types "watch non wear", not
               -- "watch_non_wear", and a search that answers only to the internal spelling is
               -- one only its author can use.
               AND (translate(e.method_key, '_', ' ') ILIKE '%'||translate(q, '_', ' ')||'%'
                    OR translate(e.event_family, '_', ' ') ILIKE '%'||translate(q, '_', ' ')||'%'
                    OR translate(e.presence::text, '_', ' ') ILIKE '%'||translate(q, '_', ' ')||'%')
        ) all_hits
    )
    SELECT jsonb_build_object(
        'q', q,
        'known_at', known,
        'n', (SELECT count(*) FROM hits),
        'hits', (SELECT coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                    'day', ((ts AT TIME ZONE 'America/New_York') - interval '4 hours')::date,
                    'at', to_char(ts AT TIME ZONE 'America/New_York', 'HH24:MI'),
                    'kind', kind, 'text', left(text, 160), 'src', src, 'row_id', row_id,
                    -- INV-5. Named on every hit, so a consumer cannot blend the two lanes by
                    -- omission. A measured row says so too; silence is not the marker.
                    'provenance', provenance, 'tier', tier, 'method', method,
                    'presence', presence))
                  ORDER BY ts DESC), '[]'::jsonb)
                   FROM (SELECT * FROM hits ORDER BY ts DESC LIMIT lim) h),
        'by_provenance', (SELECT coalesce(jsonb_object_agg(provenance, n), '{}'::jsonb)
                            FROM (SELECT provenance, count(*) AS n FROM hits GROUP BY 1) p),
        'by_month', (SELECT coalesce(jsonb_agg(jsonb_build_object('month', m, 'n', n) ORDER BY m), '[]'::jsonb)
                       FROM (SELECT to_char(date_trunc('month', ts AT TIME ZONE 'America/New_York'), 'YYYY-MM') AS m,
                                    count(*) AS n FROM hits GROUP BY 1) g),
        'truncated', (SELECT count(*) FROM hits) > lim)
    INTO out;
    RETURN out;
END $fn$;

-- The measured lanes, lifted out of the old body verbatim so the two-argument contract is
-- unchanged and the union above has one place to read them from.
CREATE OR REPLACE FUNCTION public._search_measured(q text)
RETURNS TABLE (ts timestamptz, kind text, text text, src text, row_id text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
    SELECT e.ts, 'web',
           coalesce(e.payload->>'title','') || ' — ' || coalesce(e.payload->>'domain',''),
           'chrome', e.id::text
      FROM public.events e WHERE e.kind='chrome_visit'
       AND (e.payload->>'title' ILIKE '%'||q||'%' OR e.payload->>'domain' ILIKE '%'||q||'%')
    UNION ALL
    SELECT e.ts, 'video',
           coalesce(e.payload->>'title','') || ' — ' || coalesce(e.payload->>'channel',''),
           'youtube', e.id::text
      FROM public.events e WHERE e.kind='youtube_watch'
       AND (e.payload->>'title' ILIKE '%'||q||'%' OR e.payload->>'channel' ILIKE '%'||q||'%')
    UNION ALL
    SELECT e.ts, 'calendar', coalesce(e.payload->>'summary', e.payload->>'title', 'event'),
           'calendar', e.id::text
      FROM public.events e WHERE e.kind='calendar'
       AND coalesce(e.payload->>'summary', e.payload->>'title', '') ILIKE '%'||q||'%'
    UNION ALL
    SELECT t.ts, 'money',
           coalesce(t.merchant,'?') || ' · $' || round(abs(t.amount)::numeric,2)::text
           || coalesce(' ('||t.category||')',''), 'transactions', t.id::text
      FROM public.transactions t
     WHERE t.merchant ILIKE '%'||q||'%' OR t.category ILIKE '%'||q||'%'
    UNION ALL
    SELECT c.ts, 'checkin',
           c.type || ' check-in' || coalesce(': "'||left(c.note,80)||'"',''), 'checkins', c.id::text
      FROM public.checkins c WHERE c.note ILIKE '%'||q||'%'
    UNION ALL
    SELECT a.occurred_at, a.kind,
           coalesce(a.evidence_span,'') ||
           CASE WHEN a.value_point IS NOT NULL
                THEN ' ('||a.value_point||coalesce(' '||a.unit,'')||')' ELSE '' END,
           'atoms', a.id::text
      FROM __CORE__.atoms_current a
     WHERE a.evidence_span ILIKE '%'||q||'%'
$fn$;

-- The two-argument form keeps its contract and delegates with `now()`. Dropped first because
-- 0036 declared it with parameter defaults, and PostgreSQL will not remove those in place.
DROP FUNCTION IF EXISTS public.search_record(text, int);

CREATE OR REPLACE FUNCTION public.search_record(p_q text, p_limit int DEFAULT 50)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
    SELECT public.search_record(p_q, p_limit, now())
$fn$;

REVOKE ALL ON FUNCTION public._search_measured(text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.search_record(text, int, timestamptz) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.search_record(text, int, timestamptz) TO authenticated;
