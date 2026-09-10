-- 0056_atom_panel.sql — connect the analysis layer to core.atoms (REQ-INF-108, REQ-ASK-021,
-- RULE-06, RULE-08, RULE-12, RULE-13; ADR-0089). Joe's rulings of 2026-09-09 on device
-- precedence and sleep duration are implemented here as DATA, not as branches in a function.
--
-- WHY A SEPARATE LANE AND NOT A MERGE. `analysis.panel` holds 111,891 legacy rows across 350
-- metrics whose definitions are unverified (OQ-51). Seven metric names exist in both lanes and
-- the overlap was measured before this was written:
--
--   metric              legacy avg   atoms avg   verdict
--   steps                   2,239       3,047    different populations
--   sleep_deep_min            1.3        78.2    legacy is in HOURS despite the _min suffix
--   sleep_rem_min             1.6       102.0    legacy is in HOURS despite the _min suffix
--   sleep_asleep_min        411.2       122.4    legacy means TOTAL sleep; the atom means the
--                                                UNSTAGED portion only
--   checkin_morning_energy    5.0         5.0    identical
--
-- Two of those would corrupt an answer by a factor of sixty and one by a factor of three, in
-- silence, under a name that asserts the unit. So a metric has ONE owning lane. Where atoms
-- own a metric, the legacy rows for it are EXCLUDED — not blended, not used to backfill days
-- the atoms miss, because a series that changes definition mid-window is worse than a short
-- series (RULE-12). Coverage before the atom lane starts is absent and disclosed, never
-- imputed (RULE-06).

-- RULE-13: the aggregation is a registered specification, never a query-time choice. It is a
-- table so Joe can change a measurement definition without a code change, and so an answer can
-- cite the method and version that produced it.
CREATE TABLE IF NOT EXISTS config.panel_aggregation (
    metric            TEXT PRIMARY KEY REFERENCES __CORE__.metric_registry(metric_key),
    method            TEXT NOT NULL CHECK (method IN ('sum', 'median')),
    -- Joe's ruling, 2026-09-09: prefer the Watch, never sum across devices. Measured, not
    -- assumed: on days both reported, the Watch alone was 1.01x a one-device day, the iPhone
    -- alone 0.97x, and their sum 1.98x — each device independently records the whole day.
    -- The array is a PRECEDENCE order; the first device with any row that subject day wins and
    -- the others are not read.
    device_precedence TEXT[] NOT NULL DEFAULT ARRAY['Watch', 'iPhone'],
    method_version    TEXT NOT NULL,
    note              TEXT NOT NULL
);
REVOKE ALL ON config.panel_aggregation FROM anon, authenticated;

-- Seeded FROM the registry so the method cannot disagree with the metric's own state_class.
-- A total accumulates and its day is the sum; a measurement is a reading and its day is the
-- median — the robust centre, and the same statistic `describe` already renders, so the panel
-- and the sentence cannot mean different things.
INSERT INTO config.panel_aggregation (metric, method, method_version, note)
SELECT r.metric_key,
       CASE WHEN r.state_class IN ('total', 'total_increasing') THEN 'sum' ELSE 'median' END,
       'atom-panel-v1',
       CASE WHEN r.state_class IN ('total', 'total_increasing')
            THEN 'a total accumulates over the day; the day is the sum of its records'
            ELSE 'a reading has no daily total; the day is the median of its readings, which '
                 'is what describe renders and is robust to wrist-sensor outliers' END
  FROM __CORE__.metric_registry r
 WHERE EXISTS (SELECT 1 FROM __CORE__.atoms a WHERE a.metric_key = r.metric_key)
   -- OQ-64. `config.*` is sometimes rebound alongside __CORE__ (the Ask fixture) and sometimes
   -- shared with production while __CORE__ is not (the spine test), so the foreign key targets
   -- a different registry in each. Asking "am I the real core" is too blunt — it makes the seed
   -- a no-op in the fixture that legitimately rebinds both. The precise condition is whether
   -- the CONSTRAINT THIS ROW WILL BE CHECKED AGAINST points at the registry being read.
   AND (SELECT c.confrelid FROM pg_constraint c
         WHERE c.conrelid = 'config.panel_aggregation'::regclass AND c.contype = 'f'
           AND c.conkey = ARRAY[(SELECT a.attnum FROM pg_attribute a
                                  WHERE a.attrelid = c.conrelid AND a.attname = 'metric')]
         LIMIT 1) = to_regclass('__CORE__.metric_registry')::oid
ON CONFLICT (metric) DO NOTHING;

-- A metric composed of OTHER metrics. Joe's sleep ruling lives here rather than in SQL.
CREATE TABLE IF NOT EXISTS config.panel_composition (
    metric      TEXT NOT NULL REFERENCES __CORE__.metric_registry(metric_key),
    component   TEXT NOT NULL REFERENCES __CORE__.metric_registry(metric_key),
    method      TEXT NOT NULL CHECK (method IN ('interval_union_minutes')),
    method_version TEXT NOT NULL,
    note        TEXT NOT NULL,
    PRIMARY KEY (metric, component),
    CONSTRAINT a_metric_is_not_its_own_component CHECK (metric <> component)
);
REVOKE ALL ON config.panel_composition FROM anon, authenticated;

-- Joe's ruling, 2026-09-09: sleep duration is core + deep + REM + asleep-unspecified,
-- EXCLUDING awake. `interval_union_minutes` is not a sum: it merges the segments' time ranges
-- and measures the union, so two segments that overlap are counted once. The stored data
-- happens not to overlap — 0 overlapping pairs across every stage combination, checked before
-- this was written — but "happens not to" is not a guarantee, and a duplicated segment from a
-- future import must not inflate a night's sleep by its own length.
-- `sleep_awake_min` is deliberately absent: time in bed awake is not sleep.
INSERT INTO config.panel_composition (metric, component, method, method_version, note)
SELECT v.* FROM (VALUES
 ('sleep_minutes','sleep_core_min',  'interval_union_minutes','sleep-union-v1','staged core sleep'),
 ('sleep_minutes','sleep_deep_min',  'interval_union_minutes','sleep-union-v1','staged deep sleep'),
 ('sleep_minutes','sleep_rem_min',   'interval_union_minutes','sleep-union-v1','staged REM sleep'),
 ('sleep_minutes','sleep_asleep_min','interval_union_minutes','sleep-union-v1',
  'the part of the night the Watch could not stage; never overlaps a staged segment, and '
  'omitting it would undercount exactly the nights staging failed')
) AS v(metric, component, method, method_version, note)
 WHERE EXISTS (SELECT 1 FROM __CORE__.metric_registry r WHERE r.metric_key = v.metric)
   AND EXISTS (SELECT 1 FROM __CORE__.metric_registry r WHERE r.metric_key = v.component)
   -- OQ-64. `config.*` is sometimes rebound alongside __CORE__ (the Ask fixture) and sometimes
   -- shared with production while __CORE__ is not (the spine test), so the foreign key targets
   -- a different registry in each. Asking "am I the real core" is too blunt — it makes the seed
   -- a no-op in the fixture that legitimately rebinds both. The precise condition is whether
   -- the CONSTRAINT THIS ROW WILL BE CHECKED AGAINST points at the registry being read.
   AND (SELECT c.confrelid FROM pg_constraint c
         WHERE c.conrelid = 'config.panel_composition'::regclass AND c.contype = 'f'
           AND c.conkey = ARRAY[(SELECT a.attnum FROM pg_attribute a
                                  WHERE a.attrelid = c.conrelid AND a.attname = 'metric')]
         LIMIT 1) = to_regclass('__CORE__.metric_registry')::oid
ON CONFLICT DO NOTHING;

-- The device a row came from, from its own provenance. One place, so no two queries can
-- disagree about what "the Watch" means.
CREATE OR REPLACE FUNCTION analysis._atom_device(p_evidence text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN p_evidence ~* 'source=[^;]*watch'  THEN 'Watch'
    WHEN p_evidence ~* 'source=[^;]*iphone' THEN 'iPhone'
    ELSE coalesce((regexp_match(p_evidence, 'source=([^;]+)'))[1], 'unknown') END
$$;

-- The atoms that are CURRENT and KNOWN as of a date.
--   * `recorded_at < as_of + 1` is the knowledge-time cutoff. core.atoms has a real
--     recorded_at, so unlike analysis.panel this lane is genuinely bitemporal: a value
--     imported next month does not appear in a replay of a question asked today
--     (INV-4, RULE-04, REQ-INF-108). This is the half of OQ-45 that atoms can close.
--   * a superseded atom is not current. A human correction appends and supersedes, and the
--     panel must read the correction, not both (RULE-10, INV-2).
-- TWO CLOCKS, TWO PARAMETERS. `p_as_of` is the SUBJECT-DAY cutoff — which days count.
-- `p_known_at` is the KNOWLEDGE-TIME cutoff — what the system had learned when the question
-- was asked. Conflating them is a real and tempting error: this migration originally passed
-- as_of to both, and because Ask defaults as_of to YESTERDAY (today is incomplete), the
-- 33,355 atoms imported TODAY were invisible to every question. The answer was correct
-- bitemporally and useless in practice, which is how you know the two cutoffs are different
-- questions. A live question wants every day up to yesterday, using everything known now; a
-- replay wants both cutoffs set to the moment being replayed.
CREATE OR REPLACE FUNCTION analysis.f_atom_rows(p_as_of date, p_known_at timestamptz)
RETURNS TABLE (subject_day date, metric text, device text, value numeric,
               valid_interval tstzrange, atom_id uuid)
LANGUAGE sql STABLE AS $$
  SELECT a.subject_day, a.metric_key, analysis._atom_device(a.evidence_span),
         a.value_point, a.valid_interval, a.id
    FROM __CORE__.atoms a
   WHERE a.metric_key IS NOT NULL
     AND a.presence = 'observed'
     AND a.subject_day <= p_as_of
     AND a.recorded_at <= p_known_at
     AND NOT EXISTS (SELECT 1 FROM __CORE__.atoms s
                      WHERE s.supersedes = a.id
                        AND s.recorded_at <= p_known_at)
$$;

-- Device precedence, applied per (metric, subject day): the first device in the metric's
-- precedence list that has ANY row that day owns the day, and the others are not read.
CREATE OR REPLACE FUNCTION analysis.f_atom_day_device(p_as_of date, p_known_at timestamptz)
RETURNS TABLE (subject_day date, metric text, device text, n_devices int)
LANGUAGE sql STABLE AS $$
  SELECT r.subject_day, r.metric,
         (ARRAY_AGG(r.device ORDER BY coalesce(
              array_position(g.device_precedence, r.device), 999), r.device))[1],
         count(DISTINCT r.device)::int
    FROM analysis.f_atom_rows(p_as_of, p_known_at) r
    JOIN config.panel_aggregation g ON g.metric = r.metric
   GROUP BY r.subject_day, r.metric
$$;

-- One value per metric per subject day, from the winning device only.
CREATE OR REPLACE FUNCTION analysis.f_atom_panel(p_as_of date, p_known_at timestamptz)
RETURNS TABLE (day date, metric text, value numeric, device text,
               n_atoms int, n_devices int, method text, method_version text)
LANGUAGE sql STABLE AS $$
  SELECT r.subject_day, r.metric,
         CASE g.method
           WHEN 'sum'    THEN sum(r.value)
           WHEN 'median' THEN percentile_cont(0.5) WITHIN GROUP (ORDER BY r.value)
         END,
         d.device, count(*)::int, d.n_devices, g.method, g.method_version
    FROM analysis.f_atom_rows(p_as_of, p_known_at) r
    JOIN analysis.f_atom_day_device(p_as_of, p_known_at) d
      ON d.subject_day = r.subject_day AND d.metric = r.metric AND d.device = r.device
    JOIN config.panel_aggregation g ON g.metric = r.metric
   WHERE r.value IS NOT NULL
   -- COMPONENTS are served: "how much deep sleep did I get" must have something to answer
   -- from, and an earlier draft withholding them cost that for a double-count nothing performs.
   --
   -- The COMPOSED METRIC ITSELF is not, and that distinction was missing. `sleep_minutes` is
   -- composed here AND written directly by tools/extract_checkins.py from Joe's self-reported
   -- sleep, so both arms of f_daily_panel emitted it: two rows for one metric on one day.
   -- Coverage then counts two, can exceed 1.0, and sails past the 0.60 INSUFFICIENT floor on
   -- a doubled denominator — 12 real nights in 30 reads as 0.80 instead of 0.40. Worse, the
   -- median mixes a self-report with a device interval union in one distribution, which is
   -- INV-5: two lanes sharing a column.
   --
   -- Zero such atoms exist in production today. It would have fired the first time Joe logged
   -- a sleep number in a check-in, and nothing would have looked wrong. See OQ-68 for the
   -- underlying question — a metric with both a self-reported and a derived source needs two
   -- names, not one.
     AND NOT EXISTS (SELECT 1 FROM config.panel_composition c WHERE c.metric = r.metric)
   GROUP BY r.subject_day, r.metric, d.device, d.n_devices, g.method, g.method_version
$$;

-- Composed metrics: the union of the components' intervals, in minutes.
CREATE OR REPLACE FUNCTION analysis.f_atom_composed(p_as_of date, p_known_at timestamptz)
RETURNS TABLE (day date, metric text, value numeric, device text,
               n_atoms int, n_devices int, method text, method_version text)
LANGUAGE sql STABLE AS $$
  WITH parts AS (
    SELECT c.metric AS composed, r.subject_day, r.device, r.valid_interval
      FROM config.panel_composition c
      JOIN analysis.f_atom_rows(p_as_of, p_known_at) r ON r.metric = c.component
     -- NOT NULL is not enough: a range with an unbounded end passes it, `upper()` is then
     -- NULL, and the sum over the multirange is NULL — so the night's duration is NULL and the
     -- row is still EMITTED, counted toward coverage and toward `n`. A night with no
     -- computable duration reported as a night with data is worse than a missing night
     -- (RULE-06). HealthKit can emit an open end when an export is truncated mid-session.
     WHERE r.valid_interval IS NOT NULL
       AND NOT upper_inf(r.valid_interval) AND NOT lower_inf(r.valid_interval)),
  -- Device precedence, applied to the COMPOSITION as well as to its components. Without this
  -- `range_agg` unioned a Watch segment and a phone segment into one night and then labelled
  -- the total with `min(device)` — 150 minutes attributed to the Watch of which 90 came from
  -- the phone. Two devices' segments generally do NOT overlap, so the union adds them: the
  -- "0 overlapping pairs" check that justifies the union offers no protection here, and
  -- `sleep_minutes` is the metric Joe's sleep question resolves to.
  winner AS (
    SELECT p.composed, p.subject_day,
           -- A composed metric has no panel_aggregation row of its own (it has no atoms), so
           -- the precedence is taken from its components' shared default rather than falling
           -- back to alphabetical order, which would pick a device for a reason nobody chose.
           (ARRAY_AGG(p.device ORDER BY coalesce(array_position(
                coalesce(g.device_precedence, ARRAY['Watch','iPhone']), p.device), 999),
                p.device))[1] AS device,
           count(DISTINCT p.device)::int AS n_devices
      FROM parts p
      LEFT JOIN config.panel_aggregation g ON g.metric = p.composed
     GROUP BY p.composed, p.subject_day),
  merged AS (
    SELECT p.composed, p.subject_day, count(*)::int AS n_atoms,
           w.n_devices, w.device, range_agg(p.valid_interval) AS ranges
      FROM parts p JOIN winner w
        ON w.composed = p.composed AND w.subject_day = p.subject_day AND w.device = p.device
     GROUP BY p.composed, p.subject_day, w.device, w.n_devices)
  SELECT m.subject_day, m.composed,
         round((SELECT sum(extract(epoch FROM (upper(x) - lower(x))) / 60.0)
                  FROM unnest(m.ranges) x)::numeric, 1),
         m.device, m.n_atoms, m.n_devices, 'interval_union_minutes',
         (SELECT min(c.method_version) FROM config.panel_composition c
           WHERE c.metric = m.composed)
    FROM merged m
$$;

-- REQ-INF-108. The panel Ask reads. Its signature is unchanged on purpose: `public.ask` is
-- already live against it and this must not alter that contract.
--
-- A metric owned by the atom lane is served ONLY from atoms. The legacy row is dropped even on
-- days the atoms do not cover, because a series whose definition changes mid-window is worse
-- than a short series — see the measured incompatibilities in this file's header.
CREATE OR REPLACE FUNCTION analysis.f_daily_panel(p_as_of date, p_known_at timestamptz)
RETURNS TABLE (day date, metric text, value numeric)
LANGUAGE sql STABLE
AS $fn$
    SELECT a.day, a.metric, a.value FROM analysis.f_atom_panel(p_as_of, p_known_at) a
    UNION ALL
    SELECT c.day, c.metric, c.value FROM analysis.f_atom_composed(p_as_of, p_known_at) c
    UNION ALL
    SELECT p.day, p.metric, p.value
      FROM analysis.panel p
     WHERE p.day <= p_as_of
       AND NOT EXISTS (SELECT 1 FROM config.panel_aggregation g WHERE g.metric = p.metric)
       AND NOT EXISTS (SELECT 1 FROM config.panel_composition k WHERE k.metric = p.metric)
$fn$;
-- The one-argument form Ask already calls: every subject day up to as_of, using everything
-- known NOW. Replay passes the second argument explicitly.
CREATE OR REPLACE FUNCTION analysis.f_daily_panel(p_as_of date)
RETURNS TABLE (day date, metric text, value numeric)
LANGUAGE sql STABLE
AS $fn$ SELECT * FROM analysis.f_daily_panel(p_as_of, now()) $fn$;

COMMENT ON FUNCTION analysis.f_daily_panel(date) IS
  'REQ-INF-108. The atom lane is bitemporal (core.atoms has recorded_at, and superseded atoms '
  'are excluded); the legacy analysis.panel lane still honours a subject-day cutoff only and '
  'is served only for metrics the atom lane does not own (OQ-45, OQ-51).';

-- Traceable sources, per REQ-ASK-021: which lane, which device, how many atoms, what method.
CREATE OR REPLACE FUNCTION analysis.f_panel_provenance(p_metric text, p_from date, p_to date,
                                                       p_as_of date,
                                                       p_known_at timestamptz DEFAULT now())
RETURNS TABLE (day date, lane text, device text, n_atoms int, n_devices int,
               method text, method_version text, value numeric)
LANGUAGE sql STABLE AS $$
  SELECT a.day, 'atoms', a.device, a.n_atoms, a.n_devices, a.method, a.method_version, a.value
    FROM analysis.f_atom_panel(p_as_of, p_known_at) a
   WHERE a.metric = p_metric AND a.day BETWEEN p_from AND p_to
  UNION ALL
  SELECT c.day, 'atoms:composed', c.device, c.n_atoms, c.n_devices, c.method, c.method_version, c.value
    FROM analysis.f_atom_composed(p_as_of, p_known_at) c
   WHERE c.metric = p_metric AND c.day BETWEEN p_from AND p_to
  UNION ALL
  SELECT p.day, 'legacy:' || coalesce(p.src, '?'), NULL, NULL, NULL, NULL, p.code_version, p.value
    FROM analysis.panel p
   WHERE p.metric = p_metric AND p.day BETWEEN p_from AND p_to AND p.day <= p_as_of
     AND NOT EXISTS (SELECT 1 FROM config.panel_aggregation g WHERE g.metric = p.metric)
     AND NOT EXISTS (SELECT 1 FROM config.panel_composition k WHERE k.metric = p.metric)
  ORDER BY 1
$$;

-- Partial coverage, disclosed rather than inferred (RULE-06, REQ-ASK-021). A metric the atom
-- lane owns has NO data before its first atom, and that is a gap, not a zero.
CREATE OR REPLACE VIEW analysis.v_atom_lane_coverage AS
SELECT g.metric, min(a.subject_day) AS first_day, max(a.subject_day) AS last_day,
       count(DISTINCT a.subject_day)::int AS days_with_data,
       (max(a.subject_day) - min(a.subject_day) + 1) AS days_spanned,
       bool_or(EXISTS (SELECT 1 FROM analysis.panel p WHERE p.metric = g.metric))
         AS legacy_rows_exist_and_are_excluded
  FROM config.panel_aggregation g
  LEFT JOIN __CORE__.atoms a ON a.metric_key = g.metric AND a.presence = 'observed'
 GROUP BY g.metric;
REVOKE ALL ON analysis.v_atom_lane_coverage FROM anon, authenticated;

-- RULE-12 applied to NAMING, not just to storage.
--
-- "how is my sleep" resolved to `sleep_asleep_min` at similarity 1.0 and served the UNSTAGED
-- fragment — 16 atoms over 3 days — instead of `sleep_minutes`, the metric that actually means
-- how long Joe slept. The cause is a trigram artefact: "sleep" is a substring of "Asleep
-- (unspecified)", which scores a perfect 1.0, while "Sleep duration" scores lower. The answer
-- would have been confidently wrong about the one thing the question asked.
--
-- A component of a composed metric is an INPUT, not an answer. It stays resolvable by its own
-- name — "how much deep sleep" must still reach `sleep_deep_min` — but when a composed metric
-- matches the same phrase at all, the composed metric wins regardless of similarity, because
-- the part can never be the better answer to a question about the whole.
CREATE OR REPLACE FUNCTION public._ask_resolve_metric(p_text text, p_exclude text DEFAULT NULL)
RETURNS TABLE (metric text, display text, unit text, sim real)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    WITH cand AS (
        SELECT mr.metric_key AS metric, mr.display_name AS display, mr.unit FROM __CORE__.metric_registry mr
        UNION
        SELECT dm.metric, dm.display_name, dm.unit FROM config.domain_metrics dm
          JOIN __CORE__.metric_registry mr ON mr.metric_key = dm.metric
        UNION
        SELECT d.hero_metric, d.display_name, mr.unit FROM config.domains d
          JOIN __CORE__.metric_registry mr ON mr.metric_key = d.hero_metric
    ), scored AS (
        SELECT c.metric, c.display, c.unit,
               greatest(extensions.similarity(lower(c.display), lower(p_text)),
                        extensions.similarity(lower(replace(replace(c.metric,'_',' '),'.',' ')), lower(p_text))) AS sim
          FROM cand c
         WHERE p_exclude IS NULL OR c.metric <> p_exclude
    ), parts AS (
        -- A component whose whole also matches, and where the phrase carries NO word that
        -- distinguishes the part from the whole.
        --
        -- The distinction is the whole point. "deep sleep" carries "deep", which is in
        -- "Deep sleep" and not in "Sleep duration", so the asker means the part and gets it.
        -- Bare "sleep" carries no such word — it is inside both names — so it means the whole.
        -- Demoting on similarity alone was the naive version and it sent "deep sleep" to
        -- Sleep duration; not demoting at all sent "sleep" to the 3-day unstaged fragment,
        -- because "sleep" is a substring of "Asleep" and trigram-scores a perfect 1.0.
        SELECT DISTINCT s.metric
          FROM scored s
          JOIN config.panel_composition k ON k.component = s.metric
          -- The whole no longer has to clear the SAME floor as the part. "sleep quality"
          -- strips to `sleep quality`, against which "Sleep duration" scores 0.32 and
          -- "Asleep (unspecified)" scores 0.43 — so the demotion did not fire and the answer
          -- came from the 3-day unstaged fragment, the exact failure this rule was written to
          -- stop. A part is demoted whenever its whole is a PLAUSIBLE reading of the phrase,
          -- and a whole that scores at all is more plausible than a fragment of itself.
          JOIN scored w ON w.metric = k.metric AND w.sim >= 0.20
         WHERE NOT EXISTS (
                 SELECT 1 FROM regexp_split_to_table(
                                 regexp_replace(lower(p_text), '[^a-z0-9 ]', ' ', 'g'),
                                 '\s+') AS tok
                  WHERE length(tok) > 2
                    AND position(tok IN lower(s.display)) > 0
                    AND position(tok IN lower(w.display)) = 0)
    ), ranked AS (
        SELECT s.metric, mr.display_name AS display, mr.unit, max(s.sim) AS sim,
               (s.metric IN (SELECT p.metric FROM parts p))::int AS is_a_part
          FROM scored s JOIN __CORE__.metric_registry mr ON mr.metric_key = s.metric
         GROUP BY s.metric, mr.display_name, mr.unit
    )
    SELECT r.metric, r.display, r.unit, r.sim
      FROM ranked r ORDER BY r.is_a_part ASC, r.sim DESC, r.metric LIMIT 3
$fn$;
