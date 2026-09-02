# B4 — `get_entity(p_type, p_key)`: the entity page (migration 0037)

**What this is.** SOURCES §4 module 8 tap-through: a merchant, a category, a site, a
channel, an exercise. First seen, last seen, how often, how much, when in the week and
day, the recent rows. `core.entities` is still shape-only (ADR-0004; resolution is
Phase 4), so in v1 an entity is **(type, key)** derived from the legacy tables — not a
`core.entities` id. When resolution ships, `get_entity` gains an `entity_id` field;
nothing here is renamed.

**Requirement IDs satisfied:** REQ-ASK-003 (unknown type → refusal string), REQ-ASK-011
(every recent row carries `row_id`+`src`; every aggregate carries `trace`), REQ-INF-505,
ADR-0036, REQ-LOC-005.
**ADR to write:** ADR-0043 — "Entity pages in v1 are keyed by (type, key) over
`public.transactions` / `public.events` / `core.atoms_current`; `place` delegates to
`get_place` (B5) and returns the refusal string until B5 is live."

## Step 1 — migration `migrations/0037_get_entity.sql`

```sql
-- 0037_get_entity.sql — the entity page (ADR-0043, THE_FILE §4 module 8)
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
         WHERE p_type = 'exercise' AND a.kind = 'workout' AND __EXERCISE_EXPR__ = p_key   -- same expression as B2 module 8
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
```

## Step 2 — the envelope, exactly

```json
{"type":"merchant","key":"McDonald's","as_of":"2026-09-01",
 "n":41,"first_seen":"2024-11-02","last_seen":"2026-07-21","days_since_last":42,
 "n_90d":3,"amount_total":486.12,"amount_90d":35.61,"unit":"$",
 "by_month":[{"month":"2025-03","n":4,"amount":47.90}],
 "by_weekday":[{"dow":5,"n":12}],
 "by_hour":[{"hour":19,"n":9}],
 "recent":[{"day":"2026-07-21","at":"19:42","text":"McDonald's · $11.87 (Fast food)","src":"transactions","row_id":"8812"}],
 "trace":{"tables":"public.transactions","key":{"type":"merchant","key":"McDonald's"}}}
```

`amount_*` absent for non-money types. `n: 0` form carries only `note`. Unknown
type ⇒ `refusal` + `nearest`. `place` ⇒ `refusal` + `note` until B5.

## Step 3 — tests `tests/test_get_entity.py`

```
test_ADR_0036_get_entity_refuses_without_owner_jwt
test_REQ_ASK_003_get_entity_unknown_type_returns_refusal_string_verbatim
test_ADR_0043_get_entity_place_returns_refusal_until_B5
test_REQ_INF_505_get_entity_unknown_key_returns_n_zero_and_note_only
test_ADR_0043_get_entity_merchant_by_month_sums_to_n
    -> pick the top merchant from `SELECT merchant, count(*) FROM public.transactions GROUP BY 1 ORDER BY 2 DESC LIMIT 1`
test_ADR_0043_get_entity_channel_recent_is_newest_first_and_max_20
test_REQ_ASK_011_get_entity_every_recent_row_has_src_and_row_id_and_top_has_trace
test_REQ_INF_109_get_entity_last_seen_not_after_as_of
test_REQ_LOC_005_migration_0037_has_no_coordinate_literal
```

## Done when

- Dry-run then apply pasted; four owner calls pasted (top merchant, top category, top
  channel, a nonsense type).
- Tests pass, output pasted. ADR-0043; DECISIONS row; PROGRESS + WHAT I DID NOT DO
  (must name: no `core.entities` linkage; `place` deferred; co-occurrence not built).
