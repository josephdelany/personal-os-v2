# B2 — `get_domain(p_domain, p_window)`: the nine-module envelope (migration 0035)

**What this is.** The single largest gap in `docs/THE_FILE.md` Part III. One call
returns everything the SOURCES page (§4) renders for one domain: hero, why, history,
rhythm, notables, drives / driven-by, forecast, entities, capture. Lovable computes
nothing. Built once, it serves every domain in `config.domains` (B1 must be live).

**Requirement IDs satisfied:** REQ-ASK-003 (refusal string for an unknown key, with
the nearest tracked keys), REQ-ASK-011 (every numeral click-through traceable),
REQ-INF-505 (absent means absent), REQ-INF-109 (no forward-fill past staleness),
REQ-NAR-014 (unit with every numeral), REQ-NAR-015 (registered rounding only),
REQ-TIER-050 / REQ-TIER-053 (exploratory rows: text and labels only; CANDIDATE rows
only on the EXPLORATORY-labelled list), REQ-TIER-005 (tier, n, n_eff carried with
every claim), REQ-LOC-005, INV-3, INV-4.

**ADR to write:** ADR-0041 — "`get_domain` is the Universal Domain Module envelope.
Module presence is data-driven: a module is absent when its source has no rows. The
opening sentence is composed from a closed set of templates in SQL (RULE-15). Rhythm
always uses the trailing 365 days; history uses `p_window`. Changepoints are not
computed in v1."

## Step 0 — DISCOVER (paste outputs into PROGRESS)

```sql
SELECT domain_key, hero_metric, entity_source FROM config.domains ORDER BY sort_order;
SELECT metric, count(*), min(day), max(day) FROM analysis.baselines GROUP BY 1 ORDER BY 1;
SELECT metric, min(day_target), max(day_target), count(*) FROM analysis.forecasts GROUP BY 1;
SELECT model_version, hypothesis_id, left(claim_text,80) FROM core.predictions
 WHERE model_version LIKE 'forecast-%' ORDER BY created_at DESC LIMIT 5;
SELECT kind, metric_key, left(evidence_span,40), unit FROM core.atoms_current
 WHERE kind='workout' LIMIT 5;
SELECT status, count(*) FROM core.hypothesis_register GROUP BY 1;
```

The fourth result decides how a forecast's track record is matched to a metric (see
module 7). The fifth decides where the exercise name lives for `atoms_workout_exercise`
(module 8). Record both decisions in ADR-0041.

## Step 1 — migration `migrations/0035_get_domain.sql`

### 1a. Config addition

```sql
ALTER TABLE config.domains ADD COLUMN IF NOT EXISTS capture_shortcut TEXT;
UPDATE config.domains SET capture_shortcut = CASE domain_key
    WHEN 'food' THEN 'Log Food' WHEN 'workouts' THEN 'Log Workout'
    WHEN 'mood' THEN 'Night check-in' WHEN 'drink' THEN 'Night check-in'
    WHEN 'body' THEN 'Night check-in' ELSE NULL END;
```
(`config` is not append-only; this UPDATE is legal. It is the only UPDATE in the file.)

### 1b. The function — write it exactly like this, then fill the two DISCOVER-dependent lines

```sql
CREATE OR REPLACE FUNCTION public.get_domain(p_domain text, p_window text DEFAULT '90d')
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE
    out jsonb; d date; w_days int; w0 date;
    c   config.domains%ROWTYPE;
    hm  config.domain_metrics%ROWTYPE;
    fresh_max int; stale_max int;
    cov_status text; cov_last date; cov_first date; cov_days int;
    hero jsonb; sentence text;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1;
    w_days := CASE p_window WHEN '7d' THEN 7 WHEN '30d' THEN 30 WHEN '90d' THEN 90
                            WHEN '1y' THEN 365 WHEN 'all' THEN NULL ELSE 90 END;
    w0 := CASE WHEN w_days IS NULL THEN DATE '2000-01-01' ELSE d - w_days + 1 END;

    -- REQ-ASK-003: unknown key -> the refusal string, verbatim, plus nearest keys
    SELECT * INTO c FROM config.domains WHERE domain_key = p_domain AND enabled;
    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'refusal', 'I do not track that.',
            'nearest', (SELECT jsonb_agg(domain_key ORDER BY similarity(domain_key, p_domain) DESC)
                          FROM (SELECT domain_key FROM config.domains WHERE enabled
                                ORDER BY similarity(domain_key, p_domain) DESC LIMIT 3) n));
    END IF;
    SELECT * INTO hm FROM config.domain_metrics WHERE domain_key = c.domain_key AND role='hero';
    SELECT v INTO fresh_max FROM config.coverage_thresholds WHERE k='fresh_max_days';
    SELECT v INTO stale_max FROM config.coverage_thresholds WHERE k='stale_max_days';

    -- coverage across every metric of the domain (same rule as get_domains)
    SELECT max(p.day), min(p.day), count(DISTINCT p.day)
      INTO cov_last, cov_first, cov_days
      FROM analysis.panel p JOIN config.domain_metrics dm ON dm.metric = p.metric
     WHERE dm.domain_key = c.domain_key AND p.day <= d;
    cov_status := CASE WHEN cov_last IS NULL THEN 'never_captured'
                       WHEN d - cov_last <= fresh_max THEN 'fresh'
                       WHEN d - cov_last <= stale_max THEN 'stale'
                       ELSE 'not_logged' END;

    -- module 1: hero = latest panel value <= d, with that day's personal band if any
    SELECT jsonb_strip_nulls(jsonb_build_object(
             'metric', hm.metric, 'display_name', hm.display_name, 'unit', hm.unit,
             'value', round(p.value, hm.rounding), 'day', p.day,
             'band', CASE WHEN b.band_lo IS NULL THEN NULL
                          ELSE jsonb_build_array(round(b.band_lo, hm.rounding), round(b.band_hi, hm.rounding)) END,
             'z', round(b.z_fast, 2), 'run_len', b.run_len,
             'position', CASE WHEN b.band_lo IS NULL THEN NULL
                              WHEN p.value > b.band_hi THEN 'above'
                              WHEN p.value < b.band_lo THEN 'below' ELSE 'inside' END,
             'trace', jsonb_build_object('table','analysis.panel','day',p.day,'metric',p.metric,
                                         'src',p.src,'code_version',p.code_version)))
      INTO hero
      FROM analysis.panel p
      LEFT JOIN analysis.baselines b ON b.day = p.day AND b.metric = p.metric
     WHERE p.metric = hm.metric AND p.day <= d
     ORDER BY p.day DESC LIMIT 1;

    -- the opening sentence: closed templates only (RULE-15, ADR-0041)
    sentence := CASE
      WHEN cov_status = 'never_captured' THEN
        c.display_name || ': never captured. ' || c.capture_action || '.'
      WHEN cov_status = 'not_logged' THEN
        c.display_name || ': not logged since ' || to_char(cov_last, 'DD Mon YYYY') || '. ' || c.capture_action || '.'
      WHEN hero IS NULL THEN
        c.display_name || ': no scalar summary for this source.'
      WHEN hero->>'position' IS NULL THEN
        hm.display_name || ' ' || (hero->>'value') || ' ' || hm.unit || ' on ' ||
        to_char((hero->>'day')::date, 'DD Mon') || '; no personal band yet.'
      WHEN hero->>'position' = 'inside' THEN
        hm.display_name || ' in your normal band (' || (hero->>'value') || ' ' || hm.unit ||
        ', band ' || (hero->'band'->>0) || '–' || (hero->'band'->>1) || ').'
      ELSE
        hm.display_name || ' ' ||
        CASE WHEN hero->>'position' = 'above'
             THEN round((hero->>'value')::numeric - (hero->'band'->>1)::numeric, hm.rounding)::text || ' ' || hm.unit || ' above your band'
             ELSE round((hero->'band'->>0)::numeric - (hero->>'value')::numeric, hm.rounding)::text || ' ' || hm.unit || ' below your band' END ||
        CASE WHEN abs(coalesce((hero->>'run_len')::int, 0)) >= 2
             THEN ' for the ' || abs((hero->>'run_len')::int) ||
                  CASE WHEN abs((hero->>'run_len')::int) % 100 IN (11,12,13) THEN 'th'
                       WHEN abs((hero->>'run_len')::int) % 10 = 1 THEN 'st'
                       WHEN abs((hero->>'run_len')::int) % 10 = 2 THEN 'nd'
                       WHEN abs((hero->>'run_len')::int) % 10 = 3 THEN 'rd' ELSE 'th' END || ' day'
             ELSE '' END || '.'
    END;
    IF cov_status = 'stale' THEN
        sentence := 'Stale · ' || (d - cov_last) || 'd. ' || sentence;
    END IF;

    SELECT jsonb_strip_nulls(jsonb_build_object(
      'domain', c.domain_key, 'pillar', c.pillar, 'display_name', c.display_name,
      'replaces', c.replaces, 'as_of', d, 'window', coalesce(p_window,'90d'),
      'coverage', jsonb_build_object(
          'status', cov_status, 'last_day', cov_last,
          'stale_days', CASE WHEN cov_last IS NULL THEN NULL ELSE d - cov_last END,
          'first_day', cov_first, 'days_with_data', cov_days,
          'days_in_window', (SELECT count(DISTINCT p.day) FROM analysis.panel p
                              WHERE p.metric = hm.metric AND p.day BETWEEN w0 AND d),
          'density', CASE WHEN cov_days IS NULL THEN 'none'
                          WHEN cov_last - cov_first >= 365 THEN 'years'
                          WHEN cov_last - cov_first >= 60 THEN 'months' ELSE 'weeks' END),
      'sentence', sentence,
      'hero', hero,

      -- module 2: why — each sub-factor, latest value <= d, its band, its delta vs its own 28d median
      'why', (
        SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                 'metric', m.metric, 'display_name', m.display_name, 'unit', m.unit,
                 'value', round(p.value, m.rounding), 'day', p.day,
                 'band', CASE WHEN b.band_lo IS NULL THEN NULL
                              ELSE jsonb_build_array(round(b.band_lo, m.rounding), round(b.band_hi, m.rounding)) END,
                 'z', round(b.z_fast, 2),
                 'delta_vs_28d_median', round(p.value - med.m28, m.rounding),
                 'trace', jsonb_build_object('table','analysis.panel','day',p.day,'metric',p.metric,
                                             'src',p.src,'code_version',p.code_version)))
               ORDER BY m.sort_order)
          FROM config.domain_metrics m
          JOIN LATERAL (SELECT * FROM analysis.panel q WHERE q.metric = m.metric AND q.day <= d
                         ORDER BY q.day DESC LIMIT 1) p ON true
          LEFT JOIN analysis.baselines b ON b.day = p.day AND b.metric = p.metric
          LEFT JOIN LATERAL (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY q.value) AS m28
                               FROM analysis.panel q
                              WHERE q.metric = m.metric AND q.day BETWEEN p.day - 27 AND p.day) med ON true
         WHERE m.domain_key = c.domain_key AND m.role = 'why'),

      -- module 3: history — the hero series over the window with the rolling band
      'history', (
        SELECT jsonb_strip_nulls(jsonb_build_object(
                 'metric', hm.metric, 'unit', hm.unit, 'window', coalesce(p_window,'90d'),
                 'n', count(*),
                 'points', jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                     'day', p.day, 'value', round(p.value, hm.rounding),
                     'lo', round(b.band_lo, hm.rounding), 'hi', round(b.band_hi, hm.rounding)))
                     ORDER BY p.day),
                 'trace', jsonb_build_object('table','analysis.panel','metric',hm.metric,
                                             'key','(day, metric)',
                                             'src_set', (SELECT jsonb_agg(DISTINCT q.src) FROM analysis.panel q
                                                          WHERE q.metric = hm.metric AND q.day BETWEEN w0 AND d),
                                             'band_table','analysis.baselines')))
          FROM analysis.panel p
          LEFT JOIN analysis.baselines b ON b.day = p.day AND b.metric = p.metric
         WHERE p.metric = hm.metric AND p.day BETWEEN w0 AND d
        HAVING count(*) > 0),

      -- module 4: rhythm — weekday medians over the trailing 365 days (fixed window, RULE-13)
      'rhythm', (
        WITH wd AS (
          SELECT extract(isodow FROM p.day)::int AS dow,
                 percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value) AS med, count(*) AS n
            FROM analysis.panel p
           WHERE p.metric = hm.metric AND p.day BETWEEN d - 364 AND d
           GROUP BY 1),
        ext AS (SELECT (SELECT dow FROM wd ORDER BY med DESC LIMIT 1) AS hi_dow,
                       (SELECT dow FROM wd ORDER BY med ASC  LIMIT 1) AS lo_dow,
                       (SELECT round(med, hm.rounding) FROM wd ORDER BY med DESC LIMIT 1) AS hi_med,
                       (SELECT round(med, hm.rounding) FROM wd ORDER BY med ASC  LIMIT 1) AS lo_med)
        SELECT jsonb_strip_nulls(jsonb_build_object(
                 'window', '365d', 'unit', hm.unit,
                 'weekday', (SELECT jsonb_agg(jsonb_build_object('dow', dow, 'median', round(med, hm.rounding), 'n', n) ORDER BY dow) FROM wd),
                 'sentence', CASE WHEN (SELECT count(*) FROM wd) = 7 THEN
                     'Highest on ' || to_char(DATE '2024-01-01' + (ext.hi_dow - 1), 'FMDay') || 's (' || ext.hi_med || ' ' || hm.unit ||
                     '), lowest on ' || to_char(DATE '2024-01-01' + (ext.lo_dow - 1), 'FMDay') || 's (' || ext.lo_med || ' ' || hm.unit || ').'
                     ELSE NULL END,
                 'trace', jsonb_build_object('table','analysis.panel','metric',hm.metric,'window_days',365)))
          FROM ext
         WHERE (SELECT count(*) FROM wd) > 0),

      -- module 5: notables — dated facts from baselines and panel; no badges
      'notables', (
        SELECT jsonb_agg(n ORDER BY (n->>'day')::date DESC) FROM (
          -- band breaks, trailing 365d, |z| >= 2, top 5
          SELECT jsonb_build_object('kind','band_break','day',b.day,
                   'text', hm.display_name || ' ' || round(b.value, hm.rounding) || ' ' || hm.unit || ' on ' ||
                           to_char(b.day,'DD Mon') || ' — ' || CASE WHEN b.z_fast > 0 THEN 'above' ELSE 'below' END ||
                           ' your band (' || round(b.band_lo, hm.rounding) || '–' || round(b.band_hi, hm.rounding) || ').',
                   'trace', jsonb_build_object('table','analysis.baselines','day',b.day,'metric',b.metric,'code_version',b.code_version)) AS n
            FROM (SELECT * FROM analysis.baselines WHERE metric = hm.metric AND day BETWEEN d - 364 AND d
                     AND abs(z_fast) >= 2 ORDER BY abs(z_fast) DESC LIMIT 5) b
          UNION ALL
          SELECT jsonb_build_object('kind','record_high','day',p.day,
                   'text', 'Highest recorded: ' || round(p.value, hm.rounding) || ' ' || hm.unit || ' on ' || to_char(p.day,'DD Mon YYYY') || '.',
                   'trace', jsonb_build_object('table','analysis.panel','day',p.day,'metric',p.metric,'src',p.src,'code_version',p.code_version))
            FROM (SELECT * FROM analysis.panel WHERE metric = hm.metric AND day <= d ORDER BY value DESC, day DESC LIMIT 1) p
          UNION ALL
          SELECT jsonb_build_object('kind','record_low','day',p.day,
                   'text', 'Lowest recorded: ' || round(p.value, hm.rounding) || ' ' || hm.unit || ' on ' || to_char(p.day,'DD Mon YYYY') || '.',
                   'trace', jsonb_build_object('table','analysis.panel','day',p.day,'metric',p.metric,'src',p.src,'code_version',p.code_version))
            FROM (SELECT * FROM analysis.panel WHERE metric = hm.metric AND day <= d ORDER BY value ASC, day DESC LIMIT 1) p
          UNION ALL
          SELECT jsonb_build_object('kind','longest_run','day',b.day,
                   'text', 'Longest run outside your band: ' || abs(b.run_len) || ' days ' ||
                           CASE WHEN b.run_len > 0 THEN 'above' ELSE 'below' END || ', ending ' || to_char(b.day,'DD Mon YYYY') || '.',
                   'trace', jsonb_build_object('table','analysis.baselines','day',b.day,'metric',b.metric,'code_version',b.code_version))
            FROM (SELECT * FROM analysis.baselines WHERE metric = hm.metric AND day BETWEEN d - 364 AND d
                     AND abs(run_len) >= 3 ORDER BY abs(run_len) DESC, day DESC LIMIT 1) b
        ) x),

      -- modules 6a/6b: what drives this / what this drives — text and labels ONLY (REQ-TIER-050)
      'driven_by', (SELECT public._domain_claims(c.domain_key, 'outcome')),
      'drives',    (SELECT public._domain_claims(c.domain_key, 'driver')),

      -- module 7: forecast for the hero metric, with its own track record beside it
      'forecast', CASE WHEN NOT c.forecastable THEN NULL ELSE (
        SELECT jsonb_strip_nulls(jsonb_build_object(
                 'metric', f.metric, 'unit', hm.unit, 'day_target', f.day_target,
                 'lo', round(f.lo, hm.rounding), 'point', round(f.point, hm.rounding), 'hi', round(f.hi, hm.rounding),
                 'claimed_coverage', 0.90,
                 'trace', jsonb_build_object('table','analysis.forecasts','day_target',f.day_target,'metric',f.metric,'code_version',f.code_version),
                 'track_record', (
                    SELECT jsonb_build_object('resolved', count(*), 'inside_band', count(*) FILTER (WHERE outcome_bool),
                                              'achieved_coverage', round(avg(outcome_bool::int)::numeric, 2))
                      FROM core.predictions pr
                     WHERE pr.model_version LIKE 'forecast-%' AND pr.outcome_bool IS NOT NULL
                       AND __METRIC_MATCH__                              -- DISCOVER: fill from Step 0 query 4
                    HAVING count(*) > 0)))
          FROM analysis.forecasts f
         WHERE f.metric = hm.metric AND f.day_target = d + 1) END,

      -- module 8: entities — ranked things inside this source, by entity_source
      'entities', CASE c.entity_source
        WHEN 'transactions_merchant' THEN (
          SELECT jsonb_agg(jsonb_build_object('type','merchant','key',name,'n',n,'amount',amt,'last',last_ts::date) ORDER BY amt DESC)
            FROM (SELECT coalesce(merchant,'?') AS name, count(*) AS n, round(sum(abs(amount))::numeric,2) AS amt, max(ts) AS last_ts
                    FROM public.transactions WHERE ts >= w0::timestamptz AND ts < (d+1)::timestamptz
                   GROUP BY 1 ORDER BY amt DESC LIMIT 15) t)
        WHEN 'events_youtube_channel' THEN (
          SELECT jsonb_agg(jsonb_build_object('type','channel','key',name,'n',n,'last',last_ts::date) ORDER BY n DESC)
            FROM (SELECT coalesce(payload->>'channel','?') AS name, count(*) AS n, max(ts) AS last_ts
                    FROM public.events WHERE kind='youtube_watch' AND ts >= w0::timestamptz AND ts < (d+1)::timestamptz
                   GROUP BY 1 ORDER BY n DESC LIMIT 15) t)
        WHEN 'events_chrome_domain' THEN (
          SELECT jsonb_agg(jsonb_build_object('type','site','key',name,'n',n,'last',last_ts::date) ORDER BY n DESC)
            FROM (SELECT coalesce(payload->>'domain','?') AS name, count(*) AS n, max(ts) AS last_ts
                    FROM public.events WHERE kind='chrome_visit' AND ts >= w0::timestamptz AND ts < (d+1)::timestamptz
                   GROUP BY 1 ORDER BY n DESC LIMIT 15) t)
        WHEN 'atoms_workout_exercise' THEN (
          SELECT jsonb_agg(jsonb_build_object('type','exercise','key',name,'n',n,'last',last_day) ORDER BY n DESC)
            FROM (SELECT __EXERCISE_EXPR__ AS name, count(*) AS n, max(subject_day) AS last_day   -- DISCOVER: fill from Step 0 query 5
                    FROM core.atoms_current WHERE kind='workout' AND subject_day BETWEEN w0 AND d
                   GROUP BY 1 ORDER BY n DESC LIMIT 15) t)
        ELSE NULL END,

      -- module 9: capture / correct
      'capture', jsonb_strip_nulls(jsonb_build_object(
          'action', c.capture_action, 'shortcut', c.capture_shortcut,
          'correct_via', 'ingest_capture'))
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_domain(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_domain(text, text) FROM anon;
GRANT EXECUTE ON FUNCTION public.get_domain(text, text) TO authenticated;
```

`similarity()` needs `CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;`
at the top of the file (B3 needs it too). Because the function runs with
`search_path = ''`, call it **schema-qualified**: run
`SELECT extnamespace::regnamespace FROM pg_extension WHERE extname='pg_trgm'` and write
`extensions.similarity(...)` (or whatever schema that returns) in both places. An
unqualified `similarity(` will fail at call time, not at CREATE time — test it.

### 1c. The claims helper (same file, defined BEFORE get_domain)

One helper so modules 6a and 6b are the same code. It reads `analysis.contrasts` for
the latest run joined to `core.hypothesis_register`, filtered by whether the domain's
metrics are the `outcome` (driven_by) or the `driver` (drives). Sentence template is
copied **verbatim** from `migrations/0031_patterns_watch_api.sql` lines 43–50.

```sql
CREATE OR REPLACE FUNCTION public._domain_claims(p_domain text, p_side text)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
  SELECT jsonb_agg(jsonb_build_object(
           'hypothesis_id', h.hypothesis_id,
           'tier', CASE h.status WHEN 'CANDIDATE' THEN 'EXPLORATORY'
                                 WHEN 'PROMOTED' THEN 'WATCHING'
                                 WHEN 'CONFIRMED_OBSERVATIONAL' THEN 'CONFIRMED'
                                 WHEN 'REFUTED' THEN 'REFUTED'
                                 ELSE 'INSUFFICIENT' END,
           'driver', c.driver, 'outcome', c.outcome, 'lag_days', c.lag_days,
           'sentence',
             'On your highest-' || c.driver || ' days, ' || c.outcome ||
             CASE WHEN c.lag_days > 0 THEN ' ' || c.lag_days || ' day(s) later' ELSE ' the same day' END ||
             ' ran ' || to_char(abs(c.delta), 'FM999999990.99') ||
             CASE WHEN c.delta >= 0 THEN ' higher' ELSE ' lower' END ||
             ' than after your lowest (vs seasonal+weekday baseline). ' ||
             'This may reflect a pattern; it is exploratory and unverified.',
           'n', c.n_hi + c.n_lo, 'n_eff', jsonb_build_array(c.n_eff_hi, c.n_eff_lo),
           'q', round(c.q_fdr::numeric, 4),
           'controlled_for', CASE WHEN c.weekday_partialled THEN 'weekday' ELSE NULL END,
           'watched', EXISTS (SELECT 1 FROM core.hypothesis_register w WHERE w.hypothesis_id = 'watch:' || h.hypothesis_id),
           'trace', jsonb_build_object('table','analysis.contrasts','contrast_id',c.contrast_id,'code_version',c.code_version))
         ORDER BY CASE h.status WHEN 'CONFIRMED_OBSERVATIONAL' THEN 0 WHEN 'PROMOTED' THEN 1
                                WHEN 'CANDIDATE' THEN 2 WHEN 'REFUTED' THEN 3 ELSE 4 END, c.q_fdr)
    FROM analysis.contrasts c
    JOIN core.hypothesis_register h ON h.hypothesis_id = c.hypothesis_id
   WHERE c.run_date = (SELECT max(run_date) FROM analysis.contrasts)
     AND h.hypothesis_id NOT LIKE 'watch:%'
     AND CASE p_side WHEN 'outcome' THEN c.outcome ELSE c.driver END
         IN (SELECT metric FROM config.domain_metrics WHERE domain_key = p_domain);
$fn$;
REVOKE ALL ON FUNCTION public._domain_claims(text, text) FROM PUBLIC, anon, authenticated;
```

Only `get_domain` (SECURITY DEFINER) may call it; clients cannot. Note the sentence
for a CONFIRMED row still says "exploratory and unverified" — that is wrong for that
tier. In v1 there are zero CONFIRMED rows (Step 0 query 6 shows it). Record in
OPEN_QUESTIONS: "tier-specific sentence templates for `_domain_claims` when the first
non-CANDIDATE row exists (REQ-TIER-020 tier_vocabulary)". Do not build it now.

## Step 2 — the envelope, exactly

Top-level keys, in order, and when each is absent:

| key | type | absent when |
|---|---|---|
| `domain` `pillar` `display_name` `replaces` `as_of` `window` | strings/date | never |
| `coverage` | `{status, last_day, stale_days, first_day, days_with_data, days_in_window, density}` | never (fields inside may be absent) |
| `sentence` | string | never |
| `hero` | `{metric, display_name, unit, value, day, band:[lo,hi], z, run_len, position, trace}` | no panel row for hero_metric |
| `why` | `[{metric, display_name, unit, value, day, band, z, delta_vs_28d_median, trace}]` | no `why` metrics with data |
| `history` | `{metric, unit, window, n, points:[{day, value, lo, hi}], trace}` | no points in window |
| `rhythm` | `{window:'365d', unit, weekday:[{dow 1..7, median, n}], sentence, trace}` | no data in 365d; `sentence` absent unless all 7 weekdays present |
| `notables` | `[{kind, day, text, trace}]`, kind ∈ band_break · record_high · record_low · longest_run | none |
| `driven_by` `drives` | `[{hypothesis_id, tier, driver, outcome, lag_days, sentence, n, n_eff:[hi,lo], q, controlled_for, watched, trace}]` | none |
| `forecast` | `{metric, unit, day_target, lo, point, hi, claimed_coverage, trace, track_record:{resolved, inside_band, achieved_coverage}}` | not forecastable, or no row for d+1 |
| `entities` | `[{type, key, n, amount?, last}]` | no entity_source, or none in window |
| `capture` | `{action, shortcut?, correct_via}` | never |
| `refusal` `nearest` | string, string[] | present ONLY for an unknown domain; then nothing else is present |

**Tier vocabulary on this envelope is exactly:** `EXPLORATORY` `WATCHING` `CONFIRMED`
`REFUTED` `INSUFFICIENT`. (`DESCRIPTIVE` is implicit for everything outside
`drives`/`driven_by`.)

## Step 3 — tests `tests/test_get_domain.py`

Same fixture as B1. Call for `sleep`, `money`, `attention`, `places`, and `nonsense`.

```
test_ADR_0036_get_domain_refuses_without_owner_jwt
test_REQ_ASK_003_get_domain_unknown_key_returns_refusal_string_verbatim
    -> out['refusal'] == 'I do not track that.' and 1 <= len(out['nearest']) <= 3 and 'hero' not in out
test_REQ_INF_505_get_domain_never_captured_has_no_hero_why_history
    -> for 'places': coverage.status == 'never_captured'; none of hero/why/history/rhythm/notables present; sentence startswith 'Places: never captured.'
test_REQ_INF_109_get_domain_no_day_after_as_of
    -> every hero.day, why[].day, history.points[].day, notables[].day <= as_of
test_REQ_NAR_014_get_domain_every_value_carries_unit
    -> hero, each why item, history, rhythm, forecast each have 'unit'
test_REQ_ASK_011_get_domain_every_module_carries_trace
    -> hero, why[], history, rhythm, notables[], drives[], driven_by[], forecast each have 'trace'
test_REQ_TIER_053_get_domain_claims_only_from_hypothesis_register
    -> every drives/driven_by hypothesis_id exists in core.hypothesis_register (query it in the same transaction)
test_REQ_TIER_050_get_domain_claims_are_text_and_labels_only
    -> every claim has 'tier' in the five-word set and 'sentence'; no key of a claim holds a list longer than 2 (n_eff is exactly 2)
test_ADR_0041_get_domain_sentence_matches_closed_templates
    -> re.fullmatch against the union of the seven templates in 1b (write the regexes; 'Stale · Nd. ' prefix optional)
test_ADR_0041_get_domain_window_all_returns_more_points_than_90d
    -> for 'sleep': history.n with 'all' > history.n with '90d'
test_REQ_LOC_005_migration_0035_has_no_coordinate_literal
```

## Done when

- Dry-run then real-apply output pasted.
- `select public.get_domain('sleep','90d')`, `('money','30d')`, `('attention','1y')`,
  `('places')`, `('nonsense')` as owner — each JSON pasted in full (truncate `history.points`
  to first 3 and last 3 in the paste, state `n`).
- `python3 -m pytest tests/test_get_domain.py -v` all pass, output pasted.
- ADR-0041 written with the two DISCOVER decisions (`__METRIC_MATCH__`, `__EXERCISE_EXPR__`)
  quoted as the SQL actually used; DECISIONS row; OQ appended (tier templates).
- `python3 tools/update_features.py`; `python3 tools/validate_layout.py` 0 failed.
- PROGRESS + WHAT I DID NOT DO (must include: changepoints not computed; hour-of-day
  rhythm not computed; CONFIRMED sentence template wrong-but-unreachable; any domain whose
  five calls returned less than hero+history and why).
