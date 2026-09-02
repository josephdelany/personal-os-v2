# B3 — `search_record(p_q, p_limit)`: full-text over the record (migration 0036)

**What this is.** THE RECORD §2 search: "every day since 2019, searchable." One
query string in, ranked hits out, each hit a row the timeline already knows how to
render (same `{at, kind, text, src, row_id}` shape as `get_timeline`) plus the day it
belongs to and a per-month histogram of hits for the "when did this happen" strip.

**Requirement IDs satisfied:** REQ-ASK-011 (every hit carries `row_id` + `src` — it is
its own trace), REQ-INF-505 (no hits ⇒ `n: 0`, `hits: []`, `by_month: []` — an empty
list is the honest answer to a search, not an absence), ADR-0036, REQ-LOC-005.
**ADR to write:** ADR-0042 — "Record search is trigram `ILIKE` over the text columns of
`public.events`, `public.transactions`, `public.checkins` and `core.atoms_current`, via
`search_record`. No ranking model; recency order. Coordinates and `restricted.*` are
never searched."

## Step 0 — DISCOVER

```sql
SELECT extnamespace::regnamespace FROM pg_extension WHERE extname='pg_trgm';
SELECT kind, jsonb_object_keys(payload) AS k, count(*) FROM public.events GROUP BY 1,2 ORDER BY 1,2;
SELECT pg_size_pretty(pg_total_relation_size('public.events')),
       pg_size_pretty(pg_total_relation_size('public.transactions'));
```

The second result tells you which payload keys carry text (`title`, `domain`, `channel`,
`summary`, `url`?). Index and search only keys that exist. The third is the storage
baseline: report index sizes after Step 1 against the 500 MB ceiling.

## Step 1 — migration `migrations/0036_search_record.sql`

```sql
-- 0036_search_record.sql — THE RECORD search (ADR-0042, THE_FILE §2)
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
```

If Step 0 shows the extension in a schema other than `extensions`, replace every
`extensions.` prefix accordingly. If `public.checkins` has no `note` column or
`public.events` lacks a key used above, drop that branch and say so in WHAT I DID NOT DO.

## Step 2 — the envelope, exactly

```json
{"q":"mcdonald","n":37,"truncated":false,
 "hits":[{"day":"2026-07-21","at":"19:42","kind":"money","text":"McDonald's · $11.87 (Fast food)","src":"transactions","row_id":"8812"}],
 "by_month":[{"month":"2025-03","n":4},{"month":"2026-07","n":2}]}
```

`hits` newest first, at most `p_limit` (cap 200); `by_month` counts **all** hits, not
just the returned page; `truncated` says whether the page is partial. `kind` uses the
same vocabulary as `get_timeline`. Tap a hit → `get_timeline(day)`.

## Step 3 — tests `tests/test_search_record.py`

```
test_ADR_0036_search_record_refuses_without_owner_jwt
test_ADR_0042_search_record_short_query_returns_empty_with_note
    -> search_record('a') -> n == 0, hits == [], 'note' present
test_REQ_INF_505_search_record_no_match_returns_empty_lists_not_absent
    -> search_record('zzqx-no-such-thing-9f2') -> n == 0 and hits == [] and by_month == []
test_ADR_0042_search_record_hits_are_newest_first_and_capped
    -> pick a term from Step 0 that exists (e.g. the most common youtube channel);
       len(hits) <= p_limit; 'at'/'day' non-increasing order by (day, at)
test_ADR_0042_search_record_by_month_sums_to_n
test_REQ_ASK_011_search_record_every_hit_has_src_and_row_id
test_ADR_0042_search_record_never_touches_restricted_schema
    -> read migrations/0036_search_record.sql; assert 'restricted.' not in text and 'lat' not in text.lower().split()
test_REQ_LOC_005_migration_0036_has_no_coordinate_literal
```

## Done when

- Dry-run then apply pasted; index sizes pasted (`SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) FROM pg_stat_user_indexes WHERE indexrelname LIKE '%trgm'`)
  and the new database total against 500 MB.
- Three owner calls pasted: a merchant you know, a YouTube channel you know, a nonsense string.
- Timing: `EXPLAIN ANALYZE` of one common-term call; state total ms. If > 1500 ms, say
  so in OPEN_QUESTIONS; do not narrow the search to fix it.
- Tests pass, output pasted. ADR-0042; DECISIONS row; PROGRESS + WHAT I DID NOT DO.
