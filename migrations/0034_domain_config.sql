-- 0034_domain_config.sql — config.domains: the SOURCES index (ADR-0040, THE_FILE §4)
-- Config, not data: not append-only, not derived. Changes only by migration.
-- anon/authenticated get no table access; reads go through get_domains().
-- Built under docs/build/B1_domains_config.md (session 17, 2026-09-02).
-- Deviations from B1's text, each minimal and recorded in PROGRESS + ADR-0040:
--   (a) 12 domain_metrics rows removed because their metric is absent from
--       analysis.panel today (B1 Step 0 rule; RULE-01 — never insert a panel row
--       to make a seed valid). The config.domains rows stay, so the index shows
--       "never captured" honestly.
--   (b) coverage.density / days_with_data for a never-captured domain: B1 tested
--       `s.days IS NULL`, but count(DISTINCT ...) over zero rows is 0, not NULL, so
--       an empty domain would have rendered density='weeks' and days_with_data=0
--       (a fabricated-looking zero, REQ-INF-505). Keyed on s.last_day instead.

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

-- THE_FILE Part I coverage vocabulary. PROVISIONAL thresholds (OQ-40, appended this session).
CREATE TABLE IF NOT EXISTS config.coverage_thresholds (k TEXT PRIMARY KEY, v INTEGER NOT NULL);
INSERT INTO config.coverage_thresholds VALUES ('fresh_max_days', 1), ('stale_max_days', 30)
ON CONFLICT (k) DO NOTHING;

-- ---------- seed: the fourteen domains (all kept, regardless of panel presence) ----------
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

-- ---------- seed: domain_metrics — ONLY metrics present in analysis.panel (DISCOVER 2026-09-02) ----------
-- Removed (absent from the panel today; listed in PROGRESS WHAT I DID NOT DO):
--   body/weight_lb · workouts/strength_volume · food/meals_logged ·
--   drink/alcohol_standard_drinks · drink/alcohol_ethanol_grams ·
--   attention/screen_active_hours · mood/checkin_night_mood · mood/checkin_night_energy ·
--   mood/checkin_night_stress · mood/checkin_night_day_rating · mood/checkin_morning_mood ·
--   mood/checkin_morning_sleep_feel
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
 ('activity','steps','Steps','steps','hero',0,1),
 ('activity','active_kcal','Active energy','kcal','why',0,2),
 ('activity','exercise_min','Exercise','min','why',0,3),
 ('attention','screen_sessions','Sessions','sessions','why',0,2),
 ('attention','screen_binge_min','Binge minutes','min','why',0,3),
 ('attention','screen_max_binge','Longest binge','min','why',0,4),
 ('content','yt_events','YouTube events','events','hero',0,1),
 ('content','chrome_events','Chrome events','events','why',0,2),
 ('mood','checkin_morning_energy','Energy (morning)','/10','why',0,6),
 ('money','spend.monetary_7d','Spend, 7-day','$','hero',0,1)
ON CONFLICT (domain_key, metric) DO NOTHING;

-- ---------- the RPC ----------
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
                'days_with_data', CASE WHEN s.last_day IS NULL THEN NULL ELSE s.days END,
                'density', CASE WHEN s.last_day IS NULL THEN 'none'
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
