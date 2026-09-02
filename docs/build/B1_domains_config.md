# B1 — `config.domains`: the SOURCES index (migration 0034)

**What this is.** The table that turns "twenty domains" into config for one Universal
Domain Module (`docs/THE_FILE.md` §4). Lovable reads `get_domains()` once and draws the
index: five pillars, sources under each, latest value, coverage badge, density. Every
later RPC (`get_domain`, B2) keys off `config.domains.domain_key`.

**Requirement IDs satisfied:** REQ-INF-505 (absent means absent), REQ-INF-109
(staleness declared, never forward-filled), REQ-ASK-003 (unknown key → refusal string),
REQ-NAR-014 (numeral carries unit), REQ-NAR-015 (registered rounding per metric),
REQ-LOC-005 (no coordinate literal in git). ADR-0036 pattern (one envelope per surface,
authenticated-only).

**ADR to write:** ADR-0040 — "Domain configuration lives in a `config` schema
(`config.domains`, `config.domain_metrics`, `config.coverage_thresholds`), read through
`get_domains()`. `THE_FILE.md`'s `domains.config` is realised as `config.domains`.
Config is neither append-only nor derived; it changes only by migration."

## Step 0 — DISCOVER (paste all five outputs into PROGRESS before writing any seed)

```sql
SELECT metric, src, count(*) AS days, min(day) AS first_day, max(day) AS last_day
  FROM analysis.panel GROUP BY 1,2 ORDER BY 1,2;
SELECT source, metric, count(*) FROM public.signals GROUP BY 1,2 ORDER BY 1,2;
SELECT kind, count(*), min(ts), max(ts) FROM public.events GROUP BY 1;
SELECT count(*), min(ts), max(ts) FROM public.transactions;
SELECT kind, metric_key, count(*) FROM core.atoms_current GROUP BY 1,2 ORDER BY 1,2;
```

Seed **only** `domain_metrics` rows whose `metric` appears in the first result. If a
metric named below is absent from `analysis.panel`, delete that `domain_metrics` row
from the seed and list it under WHAT I DID NOT DO. Keep the `config.domains` row
regardless (the index must show "never captured"). Never insert a panel row to make a
seed valid (RULE-01).

## Step 1 — migration `migrations/0034_domain_config.sql`

Write the file exactly as follows (three tables, one seed block, one function).

```sql
-- 0034_domain_config.sql — config.domains: the SOURCES index (ADR-0040, THE_FILE §4)
-- Config, not data: not append-only, not derived. Changes only by migration.
-- anon/authenticated get no table access; reads go through get_domains().

CREATE SCHEMA IF NOT EXISTS config;
REVOKE ALL ON SCHEMA config FROM anon, authenticated;

CREATE TABLE IF NOT EXISTS config.domains (
    domain_key      TEXT PRIMARY KEY,
    pillar          TEXT NOT NULL CHECK (pillar IN ('body','movement','fuel','mind','life')),
    display_name    TEXT NOT NULL,
    replaces        TEXT,
    hero_metric     TEXT,                      -- analysis.panel metric name; NULL = no scalar hero
    hero_unit       TEXT,
    entity_source   TEXT CHECK (entity_source IN
                      ('transactions_merchant','transactions_category',
                       'events_chrome_domain','events_youtube_channel',
                       'atoms_workout_exercise','places')),
    forecastable    BOOLEAN NOT NULL DEFAULT false,
    capture_action  TEXT NOT NULL,             -- the ONE action that fills an empty source
    sort_order      INTEGER NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS config.domain_metrics (
    domain_key      TEXT NOT NULL REFERENCES config.domains(domain_key),
    metric          TEXT NOT NULL,             -- analysis.panel metric name
    display_name    TEXT NOT NULL,
    unit            TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('hero','why')),
    rounding        INTEGER NOT NULL DEFAULT 0, -- decimals; the registered rounding (REQ-NAR-015)
    sort_order      INTEGER NOT NULL,
    PRIMARY KEY (domain_key, metric)
);

-- THE_FILE Part I coverage vocabulary. PROVISIONAL thresholds (OQ appended this session).
CREATE TABLE IF NOT EXISTS config.coverage_thresholds (k TEXT PRIMARY KEY, v INTEGER NOT NULL);
INSERT INTO config.coverage_thresholds VALUES ('fresh_max_days', 1), ('stale_max_days', 30)
ON CONFLICT (k) DO NOTHING;
```

### Seed (same file)

Both INSERTs end in `ON CONFLICT DO NOTHING` because the pytest fixture re-applies the
whole migration chain to throwaway schemas and `config.*` is not tokenised — without it
every spine test would fail on the second apply.

```sql
INSERT INTO config.domains
 (domain_key, pillar, display_name, replaces, hero_metric, hero_unit, entity_source, forecastable, capture_action, sort_order) VALUES
 ('sleep',    'body',     'Sleep',     'Apple Health · Sleep / Whoop', 'sleep_asleep_min',       'min',     NULL,                     true,  'Wear the watch to bed; refresh the Apple Health export', 10),
 ('recovery', 'body',     'Recovery',  'Whoop',                        'hrv_sdnn',               'ms',      NULL,                     true,  'Wear the watch to bed; refresh the Apple Health export', 20),
 ('vitals',   'body',     'Vitals',    'Apple Health · Heart',         'rhr',                    'bpm',     NULL,                     false, 'Wear the watch to bed; refresh the Apple Health export', 30),
 ('body',     'body',     'Body',      'Apple Health · Body',          'weight_lb',              'lb',      NULL,                     false, 'Step on the scale; log weight in the Night check-in', 40),
 ('workouts', 'movement', 'Workouts',  'Strong / Hevy',                'strength_volume',        'lb·reps', 'atoms_workout_exercise', false, 'Run the Log Workout Shortcut after every session', 50),
 ('activity', 'movement', 'Activity',  'Apple Fitness',                'steps',                  'steps',   NULL,                     false, 'Carry the phone; refresh the Apple Health export', 60),
 ('places',   'movement', 'Places',    'Google Timeline',              NULL,                     NULL,      'places',                 false, 'Install the location logger (build B5)', 70),
 ('food',     'fuel',     'Food',      'MyFitnessPal',                 'meals_logged',           'meals',   NULL,                     false, 'Run the Log Food Shortcut at every meal', 80),
 ('drink',    'fuel',     'Drink',     'Drink Control',                'alcohol_standard_drinks','drinks',  NULL,                     false, 'Log drinks in the Night check-in; log a dry night as none', 90),
 ('attention','mind',     'Attention', 'Screen Time / RescueTime',     'screen_active_hours',    'h',       NULL,                     false, 'Keep the Chrome and YouTube history exports running', 100),
 ('content',  'mind',     'Content',   'YouTube / Chrome history',     'yt_events',              'events',  'events_youtube_channel', false, 'Keep the history exports running', 110),
 ('mood',     'mind',     'Check-ins', 'Daylio',                       'checkin_night_mood',     '/10',     NULL,                     false, 'Run the Night check-in Shortcut', 120),
 ('money',    'life',     'Money',     'Mint / Copilot',               'spend.monetary_7d',      '$',       'transactions_merchant',  false, 'Refresh the bank export', 130),
 ('calendar', 'life',     'Calendar',  'Google Calendar',              NULL,                     NULL,      NULL,                     false, 'Keep the calendar export running', 140)
ON CONFLICT (domain_key) DO NOTHING;

INSERT INTO config.domain_metrics (domain_key, metric, display_name, unit, role, rounding, sort_order) VALUES
 ('sleep','sleep_asleep_min','Asleep','min','hero',0,1),
 ('sleep','sleep_inbed_min','In bed','min','why',0,2),
 ('sleep','sleep_efficiency','Efficiency','%','why',0,3),
 ('sleep','sleep_deep_pct','Deep','%','why',0,4),
 ('sleep','sleep_rem_pct','REM','%','why',0,5),
 ('sleep','sleep_onset_min','Onset','min','why',0,6),
 ('sleep','sleep_waso_min','Awake after onset','min','why',0,7),
 ('sleep','sleep_midpoint','Midpoint','clock','why',2,8),
 ('recovery','hrv_sdnn','HRV (SDNN)','ms','hero',0,1),
 ('recovery','hrv_rmssd','HRV (RMSSD)','ms','why',0,2),
 ('recovery','rhr','Resting HR','bpm','why',0,3),
 ('recovery','resp_night','Respiratory rate','/min','why',1,4),
 ('vitals','rhr','Resting HR','bpm','hero',0,1),
 ('vitals','resp_night','Respiratory rate','/min','why',1,2),
 ('vitals','wrist_temp_f','Wrist temperature','°F','why',1,3),
 ('body','weight_lb','Weight','lb','hero',1,1),
 ('workouts','strength_volume','Volume','lb·reps','hero',0,1),
 ('activity','steps','Steps','steps','hero',0,1),
 ('activity','active_kcal','Active energy','kcal','why',0,2),
 ('activity','exercise_min','Exercise','min','why',0,3),
 ('food','meals_logged','Meals logged','meals','hero',0,1),
 ('drink','alcohol_standard_drinks','Standard drinks','drinks','hero',1,1),
 ('drink','alcohol_ethanol_grams','Ethanol','g','why',0,2),
 ('attention','screen_active_hours','Active hours','h','hero',1,1),
 ('attention','screen_sessions','Sessions','sessions','why',0,2),
 ('attention','screen_binge_min','Binge minutes','min','why',0,3),
 ('attention','screen_max_binge','Longest binge','min','why',0,4),
 ('content','yt_events','YouTube events','events','hero',0,1),
 ('content','chrome_events','Chrome events','events','why',0,2),
 ('mood','checkin_night_mood','Mood (night)','/10','hero',0,1),
 ('mood','checkin_night_energy','Energy (night)','/10','why',0,2),
 ('mood','checkin_night_stress','Stress (night)','/10','why',0,3),
 ('mood','checkin_night_day_rating','Day rating','/10','why',0,4),
 ('mood','checkin_morning_mood','Mood (morning)','/10','why',0,5),
 ('mood','checkin_morning_energy','Energy (morning)','/10','why',0,6),
 ('mood','checkin_morning_sleep_feel','Sleep feel','/10','why',0,7),
 ('money','spend.monetary_7d','Spend, 7-day','$','hero',0,1)
ON CONFLICT (domain_key, metric) DO NOTHING;
```

Note `weight_lb`, `alcohol_*`, `meals_logged`, `strength_volume` are atom-fed panel
metrics; Step 0's fifth query tells you whether any atoms exist yet. Expect several to
be absent today. That is the honest state; remove those `domain_metrics` rows only.

### The RPC (same file)

```sql
CREATE OR REPLACE FUNCTION public.get_domains()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb; d date; fresh_max int; stale_max int;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1;
    SELECT v INTO fresh_max FROM config.coverage_thresholds WHERE k='fresh_max_days';
    SELECT v INTO stale_max FROM config.coverage_thresholds WHERE k='stale_max_days';
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'as_of', d,
      'pillars', jsonb_build_array('body','movement','fuel','mind','life'),
      'domains', (
        SELECT jsonb_agg(jsonb_build_object(
            'domain', c.domain_key, 'pillar', c.pillar, 'display_name', c.display_name,
            'replaces', c.replaces, 'sort_order', c.sort_order,
            'hero', CASE WHEN h.day IS NULL THEN NULL ELSE jsonb_build_object(
                'metric', c.hero_metric, 'unit', c.hero_unit,
                'value', round(h.value, coalesce(m.rounding,0)), 'day', h.day,
                'trace', jsonb_build_object('table','analysis.panel','day',h.day,
                                            'metric',c.hero_metric,'src',h.src,
                                            'code_version',h.code_version)) END,
            'coverage', jsonb_build_object(
                'status', CASE WHEN s.last_day IS NULL THEN 'never_captured'
                               WHEN d - s.last_day <= fresh_max THEN 'fresh'
                               WHEN d - s.last_day <= stale_max THEN 'stale'
                               ELSE 'not_logged' END,
                'last_day', s.last_day,
                'stale_days', CASE WHEN s.last_day IS NULL THEN NULL ELSE d - s.last_day END,
                'first_day', s.first_day,
                'days_with_data', s.days,
                'density', CASE WHEN s.days IS NULL THEN 'none'
                                WHEN s.last_day - s.first_day >= 365 THEN 'years'
                                WHEN s.last_day - s.first_day >= 60  THEN 'months'
                                ELSE 'weeks' END),
            'capture_action', c.capture_action)
          ORDER BY c.pillar, c.sort_order)
          FROM config.domains c
          LEFT JOIN config.domain_metrics m ON m.domain_key=c.domain_key AND m.role='hero'
          LEFT JOIN LATERAL (SELECT p.day, p.value, p.src, p.code_version FROM analysis.panel p
                              WHERE p.metric=c.hero_metric AND p.day<=d
                              ORDER BY p.day DESC LIMIT 1) h ON true          -- never after d: INV-4
          LEFT JOIN LATERAL (SELECT max(p.day) AS last_day, min(p.day) AS first_day,
                                    count(DISTINCT p.day) AS days
                               FROM analysis.panel p
                               JOIN config.domain_metrics dm ON dm.metric=p.metric
                              WHERE dm.domain_key=c.domain_key AND p.day<=d) s ON true
         WHERE c.enabled)
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_domains() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_domains() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_domains() TO authenticated;
```

`places` and `calendar` have no `hero_metric`: their `hero` is absent and coverage is
`never_captured` until B5 / a calendar panel metric exists. Correct, not a bug.

## Step 2 — the envelope, exactly (what Lovable binds to)

```json
{"as_of":"2026-09-01",
 "pillars":["body","movement","fuel","mind","life"],
 "domains":[
  {"domain":"sleep","pillar":"body","display_name":"Sleep","replaces":"Apple Health · Sleep / Whoop","sort_order":10,
   "hero":{"metric":"sleep_asleep_min","unit":"min","value":412,"day":"2026-08-30",
           "trace":{"table":"analysis.panel","day":"2026-08-30","metric":"sleep_asleep_min","src":"signals:apple_sleep","code_version":"panel-v1"}},
   "coverage":{"status":"stale","last_day":"2026-08-30","stale_days":2,"first_day":"2019-09-03","days_with_data":2381,"density":"years"},
   "capture_action":"Wear the watch to bed; refresh the Apple Health export"},
  {"domain":"places","pillar":"movement","display_name":"Places","replaces":"Google Timeline","sort_order":70,
   "coverage":{"status":"never_captured","density":"none"},
   "capture_action":"Install the location logger (build B5)"}
 ]}
```

`hero` absent ⇒ the row renders "never captured → {capture_action}". `coverage.status`
is exactly one of `fresh` `stale` `not_logged` `never_captured`. Nothing else may be
invented client-side.

## Step 3 — tests `tests/test_get_domains.py`

Fixture: `lib.db.connect()`, one cursor, `set_config('request.jwt.claims', ...)` as in
`tools/_probe_state.py` lines 46–48, call `select public.get_domains()`, parse, **rollback**
at teardown. Test names, exactly:

```
test_ADR_0036_get_domains_refuses_without_owner_jwt
    -> before set_config, calling raises; "owner only" in str(exc)
test_REQ_INF_505_get_domains_never_emits_hero_for_never_captured
    -> every domain with coverage.status == 'never_captured' has no 'hero' key
test_REQ_INF_109_get_domains_hero_day_never_after_as_of
    -> for every hero: hero['day'] <= as_of
test_REQ_NAR_014_get_domains_every_hero_carries_unit_and_trace
    -> hero has 'unit' and 'trace' with all five trace keys
test_ADR_0040_every_seeded_metric_exists_in_panel_or_is_declared_absent
    -> SELECT dm.metric FROM config.domain_metrics dm
         WHERE NOT EXISTS (SELECT 1 FROM analysis.panel p WHERE p.metric=dm.metric)
       must be empty (Step 0 removed the absent ones)
test_REQ_LOC_005_migration_0034_has_no_coordinate_literal
    -> re.search(r'-?\d{1,3}\.\d{4,}', open('migrations/0034_domain_config.sql').read()) is None
test_ADR_0040_coverage_status_is_closed_vocabulary
    -> every coverage.status in {'fresh','stale','not_logged','never_captured'}
```

## Done when

- Dry-run output, then real-apply output, pasted.
- `select public.get_domains()` as owner: full JSON pasted, plus a one-line count of
  domains per `coverage.status`.
- `python3 -m pytest tests/test_get_domains.py -v` — all pass, output pasted.
- ADR-0040 written; `docs/DECISIONS.md` row added; OQ appended: "coverage thresholds
  fresh≤1d / stale≤30d are provisional; set against real capture cadence".
- `python3 tools/update_features.py` run (B0); `python3 tools/validate_layout.py` 0 failed.
- PROGRESS entry with WHAT I DID NOT DO listing every seed row removed by Step 0.
