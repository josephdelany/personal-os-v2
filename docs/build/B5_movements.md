# B5 — MOVEMENTS: restricted store, ingress, place resolution, `get_movements` / `get_place` (migrations 0038–0040)

**What this is.** THE_FILE §3. The location tracer Joe asked for, built inside the
RULE-29 / REQ-LOC boundary: coordinates enter a `restricted` schema and **never leave
it** — not to a client, not to a log, not to a Python job, not to git. Every surface
receives labels, dwell minutes and aggregates only. This is three sessions:

| Session | Builds | Migration |
|---|---|---|
| B5.1 | `restricted` schema, fixes/places/visits tables, `ingest_location(_batch)`, `register_place`, `assign_place` | 0038 |
| B5.2 | `restricted.derive_visits()`, the hourly call, the lint, `analysis.visits_public`, panel metrics | 0039 |
| B5.3 | `get_movements(p_day)`, `get_place(p_place_id)`, Overland edge function, the Shortcut fallback | 0040 |

**Requirement IDs satisfied:** REQ-LOC-001, -002, -003, -004, -005, -006, -007, -008,
-009, -011, -012, -013, -015, -016, -017, -018 (quote each from
`specs/08-location/requirements.md` at the start of each session). INV-1, INV-2, INV-4.
**ADRs to write:** ADR-0044 (B5.1) — "LOC-Q2 answered: the restricted store is a
schema with zero grants; its only readers are SECURITY DEFINER SQL functions inside
the database; no code outside `migrations/` may name a `restricted.` table (lint)."
ADR-0045 (B5.2) — "Visit derivation runs in-database; thresholds are provisional
(OQ-37)." ADR-0046 (B5.3) — "Background capture via Overland → Supabase Edge Function;
Shortcut automation as fallback."

**DECISION for Joe before B5.3 (ask, do not assume):** Overland (free, open-source iOS
app, background, ~1–3 % battery/day on 'significant changes') or iOS Shortcut
automations (no third-party app; fires only on Arrive/Leave/time triggers you create by
hand on the phone). Recommendation: Overland. Both paths are specified below.

---

## B5.1 — migration `migrations/0038_restricted_location.sql`

### Step 0 — DISCOVER
```sql
SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','postgres');
SELECT proname, prosecdef FROM pg_proc WHERE proname IN ('ingest_capture');
-- how 0017/0020 compute subject_day and its rule version string:
SELECT prosrc FROM pg_proc WHERE proname = 'ingest_capture';
SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='locations';
```
Confirm the `subject_day` rule and `RULE_VERSION` literal in `tools/extract_checkins.py`
(lines ~39–55) match what the DDL below hardcodes (`04:00 America/New_York`, `'v1-2026-08-23'`); if not, use the file's values. The last query documents the 282 legacy
rows; **do not migrate them in this session** (OQ: legacy `public.locations` backfill —
append to OPEN_QUESTIONS, decision needed on whether those are wanted).

### Step 1 — DDL
(`IF NOT EXISTS` everywhere: `restricted.*` and `analysis.*` are literal, not tokenised,
so the pytest fixture's re-apply must be a no-op against live objects.)
```sql
-- 0038_restricted_location.sql — the restricted coordinate store (ADR-0044; REQ-LOC-001/002/004/006/008/009)
CREATE SCHEMA IF NOT EXISTS restricted;
REVOKE ALL ON SCHEMA restricted FROM PUBLIC;
REVOKE ALL ON SCHEMA restricted FROM anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA restricted REVOKE ALL ON TABLES FROM anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS restricted.location_fixes (
    fix_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_capture_id  UUID NOT NULL REFERENCES __CORE__.raw_captures(capture_id),   -- INV-1
    captured_at     TIMESTAMPTZ NOT NULL,
    lat             DOUBLE PRECISION NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon             DOUBLE PRECISION NOT NULL CHECK (lon BETWEEN -180 AND 180),
    accuracy_m      NUMERIC,
    speed_mps       NUMERIC,
    battery         NUMERIC,
    motion          TEXT[],
    source          TEXT NOT NULL CHECK (source IN ('overland','shortcut','legacy')),
    trust_level     __CORE__.trust_level NOT NULL,                                 -- REQ-LOC-004
    subject_day     DATE NOT NULL,
    subject_day_rule_version TEXT NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS location_fixes_captured_idx ON restricted.location_fixes (captured_at);
CREATE INDEX IF NOT EXISTS location_fixes_day_idx      ON restricted.location_fixes (subject_day);
-- append-only (INV-2): copy the mutation-rejecting trigger function + trigger from
-- migrations/0012_grants_and_immutability.sql and attach it to restricted.location_fixes.

CREATE TABLE IF NOT EXISTS restricted.places (
    place_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label           TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('home','gym','bar','work','restaurant','shop','friend','family','transit','other')),
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    radius_m        NUMERIC NOT NULL DEFAULT 75,                                    -- provisional (OQ-37)
    is_home         BOOLEAN NOT NULL DEFAULT false,                                 -- REQ-LOC-008
    provenance      TEXT NOT NULL CHECK (provenance IN ('human','inferred')),
    corrected_by_human BOOLEAN NOT NULL DEFAULT false,                              -- RULE-10
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes      UUID REFERENCES restricted.places(place_id)
);
CREATE OR REPLACE VIEW restricted.places_current AS
    SELECT p.* FROM restricted.places p
    WHERE NOT EXISTS (SELECT 1 FROM restricted.places s WHERE s.supersedes = p.place_id);

-- derived, rebuildable (B5.2 fills it); lives here because centroids are coordinates
CREATE TABLE IF NOT EXISTS restricted.visits (
    visit_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id        UUID REFERENCES restricted.places(place_id),                    -- NULL = unknown (REQ-LOC-009)
    arrive_at       TIMESTAMPTZ NOT NULL,
    depart_at       TIMESTAMPTZ NOT NULL,
    subject_day     DATE NOT NULL,
    n_fixes         INTEGER NOT NULL,
    c_lat           DOUBLE PRECISION NOT NULL,
    c_lon           DOUBLE PRECISION NOT NULL,
    human_place_id  UUID REFERENCES restricted.places(place_id),                    -- RULE-10 override, set by assign_place
    code_version    TEXT NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (depart_at >= arrive_at)
);
CREATE INDEX IF NOT EXISTS visits_day_idx ON restricted.visits (subject_day);

-- haversine, metres
CREATE OR REPLACE FUNCTION restricted.dist_m(lat1 float8, lon1 float8, lat2 float8, lon2 float8)
RETURNS float8 LANGUAGE sql IMMUTABLE AS $f$
  SELECT 2 * 6371000 * asin(sqrt(
      power(sin(radians(lat2-lat1)/2),2) +
      cos(radians(lat1))*cos(radians(lat2))*power(sin(radians(lon2-lon1)/2),2)));
$f$;
```

### Step 2 — ingress (same file). Coordinates go to `restricted`; `raw_captures` gets a REDACTED payload.
```sql
-- REQ-LOC-001/004: the capture row exists for INV-1 lineage, but carries NO coordinate.
CREATE OR REPLACE FUNCTION public.ingest_location(
    p_capture_id uuid, p_captured_at timestamptz, p_lat float8, p_lon float8,
    p_accuracy_m numeric DEFAULT NULL, p_speed_mps numeric DEFAULT NULL,
    p_battery numeric DEFAULT NULL, p_motion text[] DEFAULT NULL,
    p_source text DEFAULT 'shortcut')
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE cid uuid;
BEGIN
    IF p_source NOT IN ('overland','shortcut') THEN RAISE EXCEPTION 'ingest_location: bad source'; END IF;
    IF p_captured_at > now() + interval '10 minutes' THEN RAISE EXCEPTION 'ingest_location: future timestamp'; END IF;
    cid := coalesce(p_capture_id, gen_random_uuid());
    INSERT INTO __CORE__.raw_captures (capture_id, captured_at, source, trust_level, payload, processing_status)
    VALUES (cid, p_captured_at, 'location', 'trusted',
            jsonb_build_object('kind','location','redacted',true,'source',p_source), 'extracted')
    ON CONFLICT (capture_id) DO NOTHING;
    IF NOT FOUND THEN RETURN jsonb_build_object('ok', true, 'duplicate', true); END IF;
    INSERT INTO restricted.location_fixes
        (raw_capture_id, captured_at, lat, lon, accuracy_m, speed_mps, battery, motion, source, trust_level,
         subject_day, subject_day_rule_version)
    VALUES (cid, p_captured_at, p_lat, p_lon, p_accuracy_m, p_speed_mps, p_battery, p_motion, p_source, 'trusted',
            ((p_captured_at AT TIME ZONE 'America/New_York') - interval '4 hours')::date, 'v1-2026-08-23');
            -- same rule as tools/extract_checkins.py subject_day()/RULE_VERSION (ADR-0019: 04:00 ET, by start). Verify the literal there before applying.
    RETURN jsonb_build_object('ok', true);
END $fn$;
REVOKE ALL ON FUNCTION public.ingest_location(uuid,timestamptz,float8,float8,numeric,numeric,numeric,text[],text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ingest_location(uuid,timestamptz,float8,float8,numeric,numeric,numeric,text[],text) TO anon, authenticated;
-- anon EXECUTE mirrors ingest_capture (ADR-0034: write-only path for the phone). It returns no data.

-- Overland batch: GeoJSON FeatureCollection {"locations":[{"geometry":{"coordinates":[lon,lat]},"properties":{...}}]}
CREATE OR REPLACE FUNCTION public.ingest_location_batch(p_batch jsonb)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE f jsonb; n int := 0; r jsonb;
BEGIN
    FOR f IN SELECT * FROM jsonb_array_elements(coalesce(p_batch->'locations','[]'::jsonb)) LOOP
        r := public.ingest_location(
            NULL,
            (f->'properties'->>'timestamp')::timestamptz,
            (f->'geometry'->'coordinates'->>1)::float8,        -- lat
            (f->'geometry'->'coordinates'->>0)::float8,        -- lon
            (f->'properties'->>'horizontal_accuracy')::numeric,
            (f->'properties'->>'speed')::numeric,
            (f->'properties'->>'battery_level')::numeric,
            (SELECT array_agg(x) FROM jsonb_array_elements_text(coalesce(f->'properties'->'motion','[]'::jsonb)) x),
            'overland');
        n := n + 1;
    END LOOP;
    RETURN jsonb_build_object('result','ok','n',n);               -- Overland requires {"result":"ok"}
END $fn$;
REVOKE ALL ON FUNCTION public.ingest_location_batch(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_location_batch(jsonb) TO service_role;   -- only the edge function
```

### Step 3 — place registration and human correction (same file). Owner only.
```sql
-- REQ-LOC-006/008, RULE-10. Called from the "Register this place" Shortcut with the phone's current fix.
CREATE OR REPLACE FUNCTION public.register_place(p_label text, p_kind text, p_lat float8, p_lon float8,
                                                 p_radius_m numeric DEFAULT 75, p_is_home boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE pid uuid;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN RAISE EXCEPTION 'owner only'; END IF;
    INSERT INTO restricted.places (label, kind, lat, lon, radius_m, is_home, provenance, corrected_by_human)
    VALUES (p_label, p_kind, p_lat, p_lon, p_radius_m, p_is_home, 'human', true) RETURNING place_id INTO pid;
    RETURN jsonb_build_object('place_id', pid, 'label', p_label, 'kind', p_kind, 'is_home', p_is_home);
END $fn$;
REVOKE ALL ON FUNCTION public.register_place(text,text,float8,float8,numeric,boolean) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.register_place(text,text,float8,float8,numeric,boolean) TO authenticated;

-- Name an unknown visit from THE DESK: creates the place FROM THE VISIT CENTROID server-side.
-- The client sends a label and a visit_id; no coordinate crosses the boundary in either direction.
CREATE OR REPLACE FUNCTION public.assign_place(p_visit_id uuid, p_label text, p_kind text DEFAULT 'other')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE pid uuid; v restricted.visits%ROWTYPE;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN RAISE EXCEPTION 'owner only'; END IF;
    SELECT * INTO v FROM restricted.visits WHERE visit_id = p_visit_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('refusal', 'I do not track that.'); END IF;
    SELECT place_id INTO pid FROM restricted.places_current WHERE label = p_label LIMIT 1;
    IF pid IS NULL THEN
        INSERT INTO restricted.places (label, kind, lat, lon, provenance, corrected_by_human)
        VALUES (p_label, p_kind, v.c_lat, v.c_lon, 'human', true) RETURNING place_id INTO pid;
    END IF;
    UPDATE restricted.visits SET human_place_id = pid WHERE visit_id = p_visit_id;   -- visits are derived, not append-only
    RETURN jsonb_build_object('visit_id', p_visit_id, 'place_id', pid, 'label', p_label);
END $fn$;
REVOKE ALL ON FUNCTION public.assign_place(uuid,text,text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.assign_place(uuid,text,text) TO authenticated;
```

### B5.1 tests `tests/test_restricted_location.py` (all inside a rolled-back transaction; test coordinates are `0.0`/`0.01`-style ocean points with ≤ 3 decimals — never a real place)
```
test_REQ_LOC_001_restricted_schema_has_no_grants_for_anon_authenticated_service_role
    -> SELECT has_schema_privilege(r,'restricted','USAGE') for each role is false
test_REQ_LOC_004_ingest_location_raw_capture_payload_has_no_coordinate_and_is_trusted
    -> call ingest_location(...); SELECT payload, trust_level FROM core.raw_captures WHERE capture_id=...;
       assert no numeric value anywhere in payload; trust_level == 'trusted'
test_INV_1_every_fix_references_a_raw_capture
test_INV_2_location_fixes_rejects_update_and_delete
test_REQ_LOC_008_register_place_home_flag_persists_and_is_owner_only
test_ADR_0044_ingest_location_batch_parses_overland_geojson_and_returns_result_ok
    -> a two-feature FeatureCollection at (0.0, 0.0) and (0.0, 0.01); n == 2; response['result'] == 'ok'
test_REQ_LOC_005_migration_0038_has_no_coordinate_literal
```

---

## B5.2 — migration `migrations/0039_visits_and_lint.sql`

### Derivation, in-database (REQ-LOC-011/012/013/015; ADR-0045)
```sql
-- Thresholds: PROVISIONAL (OQ-37). Named here once; the function reads this table.
CREATE TABLE IF NOT EXISTS restricted.visit_params (k TEXT PRIMARY KEY, v NUMERIC NOT NULL);
INSERT INTO restricted.visit_params VALUES ('stay_radius_m', 100), ('min_dwell_min', 10),
       ('max_gap_min', 45), ('max_accuracy_m', 150) ON CONFLICT (k) DO NOTHING;

-- Rebuilds visits for subject_day >= p_from. Greedy stay detection:
--   walk fixes in time order (accuracy <= max_accuracy_m); a fix joins the current stay if it is
--   within stay_radius_m of the stay's running centroid AND within max_gap_min of the last fix;
--   otherwise the stay closes. A closed stay is a visit iff dwell >= min_dwell_min.
--   Place = nearest places_current within its radius_m, else NULL (REQ-LOC-009 — never the nearest guess).
--   Gaps are NOT stays (REQ-LOC-015): nothing is imputed between fixes.
CREATE OR REPLACE FUNCTION restricted.derive_visits(p_from date)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    rmax float8; dmin numeric; gmax numeric; amax numeric;
    f record; n int := 0;
    cur_lat float8; cur_lon float8; cur_n int := 0; cur_start timestamptz; cur_last timestamptz;
BEGIN
    SELECT v INTO rmax FROM restricted.visit_params WHERE k='stay_radius_m';
    SELECT v INTO dmin FROM restricted.visit_params WHERE k='min_dwell_min';
    SELECT v INTO gmax FROM restricted.visit_params WHERE k='max_gap_min';
    SELECT v INTO amax FROM restricted.visit_params WHERE k='max_accuracy_m';
    -- preserve human assignments across rebuilds: stash (arrive_at, human_place_id) then re-apply by overlap
    CREATE TEMP TABLE _human ON COMMIT DROP AS
        SELECT arrive_at, depart_at, human_place_id FROM restricted.visits
         WHERE subject_day >= p_from AND human_place_id IS NOT NULL;
    DELETE FROM restricted.visits WHERE subject_day >= p_from;
    FOR f IN SELECT captured_at, lat, lon, subject_day, subject_day_rule_version
               FROM restricted.location_fixes
              WHERE subject_day >= p_from AND (accuracy_m IS NULL OR accuracy_m <= amax)
              ORDER BY captured_at LOOP
        IF cur_n > 0 AND restricted.dist_m(cur_lat, cur_lon, f.lat, f.lon) <= rmax
           AND f.captured_at - cur_last <= (gmax || ' minutes')::interval THEN
            cur_lat := (cur_lat*cur_n + f.lat)/(cur_n+1); cur_lon := (cur_lon*cur_n + f.lon)/(cur_n+1);
            cur_n := cur_n + 1; cur_last := f.captured_at;
        ELSE
            IF cur_n > 0 AND cur_last - cur_start >= (dmin || ' minutes')::interval THEN
                INSERT INTO restricted.visits (place_id, arrive_at, depart_at, subject_day, n_fixes, c_lat, c_lon, code_version)
                SELECT (SELECT place_id FROM restricted.places_current p
                         WHERE restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) <= p.radius_m
                         ORDER BY restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) LIMIT 1),
                       cur_start, cur_last, ((cur_start AT TIME ZONE 'America/New_York') - interval '4 hours')::date, cur_n, cur_lat, cur_lon, 'visits-v1';
                n := n + 1;
            END IF;
            cur_lat := f.lat; cur_lon := f.lon; cur_n := 1; cur_start := f.captured_at; cur_last := f.captured_at;
        END IF;
    END LOOP;
    IF cur_n > 0 AND cur_last - cur_start >= (dmin || ' minutes')::interval THEN
        INSERT INTO restricted.visits (place_id, arrive_at, depart_at, subject_day, n_fixes, c_lat, c_lon, code_version)
        SELECT (SELECT place_id FROM restricted.places_current p
                 WHERE restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) <= p.radius_m
                 ORDER BY restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) LIMIT 1),
               cur_start, cur_last, ((cur_start AT TIME ZONE 'America/New_York') - interval '4 hours')::date, cur_n, cur_lat, cur_lon, 'visits-v1';
        n := n + 1;
    END IF;
    UPDATE restricted.visits v SET human_place_id = h.human_place_id
      FROM _human h WHERE v.subject_day >= p_from
       AND tstzrange(v.arrive_at, v.depart_at) && tstzrange(h.arrive_at, h.depart_at);
    RETURN n;
END $fn$;
REVOKE ALL ON FUNCTION restricted.derive_visits(date) FROM PUBLIC, anon, authenticated, service_role;

-- The ONLY thing outside restricted that may see visits: labels and times, never coordinates.
CREATE OR REPLACE VIEW analysis.visits_public AS
    SELECT v.visit_id, v.subject_day, v.arrive_at, v.depart_at,
           extract(epoch FROM v.depart_at - v.arrive_at)/60 AS dwell_min, v.n_fixes,
           coalesce(v.human_place_id, v.place_id) AS place_id,
           p.label, p.kind, p.is_home, v.code_version
      FROM restricted.visits v
      LEFT JOIN restricted.places_current p ON p.place_id = coalesce(v.human_place_id, v.place_id);
```

### The hourly call
In the existing hourly extraction workflow (the job that runs `tools/extract_checkins.py`
— read `.github/workflows/` to find it), add one step **after** extraction:
`python3 tools/run_sql_scalar.py "select restricted.derive_visits(current_date - 3)"`,
where `tools/run_sql_scalar.py` is a 15-line script that runs exactly one statement
from argv via `lib.db`, prints the scalar, writes an `ops.runs` row
(`job_name='derive_visits'`), and exits. The Python never selects from `restricted.`.

### The lint (REQ-LOC-005 / ADR-0044) — add to `tools/validate_layout.py`
- **Fail** if any file outside `migrations/` and `docs/` contains the string `restricted.`
  except the exact call text `restricted.derive_visits(` inside the workflow and
  `tools/run_sql_scalar.py`'s argv.
- **Fail** if any file in the repo matches `-?\d{1,3}\.\d{4,}` inside a line that also
  contains `lat` or `lon` (case-insensitive), or contains `is_home = true` with a literal.
- Keep the existing checks; total count goes from 38 to 40. Paste the new output.

### Panel metrics (so the `places` domain gets a hero)
In `tools/engines/panel.py` add, from `analysis.visits_public` only:
`places_distinct` (count DISTINCT place_id per subject_day, unknown counted once as NULL→excluded),
`away_min` (sum dwell_min where `is_home` is false or NULL), `home_min` (is_home true).
Then in a migration statement in 0039:
`UPDATE config.domains SET hero_metric='away_min', hero_unit='min' WHERE domain_key='places';`
and insert `domain_metrics` rows for the three (`away_min` hero, `home_min` why,
`places_distinct` why) with `ON CONFLICT DO NOTHING`.

### B5.2 tests `tests/test_derive_visits.py` (rolled back; synthetic ocean fixes)
```
test_REQ_LOC_009_stay_far_from_every_place_yields_visit_with_null_place_id
test_REQ_LOC_015_gap_longer_than_max_gap_splits_into_two_visits_and_imputes_nothing
test_ADR_0045_stay_shorter_than_min_dwell_is_not_a_visit
test_REQ_LOC_006_registered_place_within_radius_resolves_and_human_assignment_survives_rebuild
test_REQ_LOC_012_visits_public_view_exposes_no_coordinate_column
    -> information_schema.columns for analysis.visits_public has none of lat/lon/c_lat/c_lon
test_REQ_LOC_005_lint_fails_on_a_restricted_reference_outside_migrations  (write a temp file, run validate_layout, expect failure, remove it)
```

---

## B5.3 — migration `migrations/0040_movements_api.sql` + capture path

### `get_movements(p_day)` — labels, minutes, aggregates. Never a coordinate.
```sql
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
```
`radius_of_gyration_km` is an aggregate distance (REQ-LOC-012 permits the aggregate);
it is rounded to 0.1 km and is never paired with a centre.

### `get_place(p_place_id)`
```sql
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

-- places register for THE DESK / MOVEMENTS: labels only
CREATE OR REPLACE FUNCTION public.get_places()
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
  SELECT CASE WHEN coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com'
              THEN NULL ELSE
    jsonb_build_object('places', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'place_id', p.place_id, 'label', p.label, 'kind', p.kind, 'is_home', p.is_home,
        'visits_n', (SELECT count(*) FROM analysis.visits_public v WHERE v.place_id = p.place_id),
        'last_visit', (SELECT max(subject_day) FROM analysis.visits_public v WHERE v.place_id = p.place_id))
      ORDER BY p.is_home DESC, p.label) FROM restricted.places_current p), '[]'::jsonb)) END;
$fn$;
REVOKE ALL ON FUNCTION public.get_places() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_places() TO authenticated;
```
(Note `get_places` returns NULL rather than raising when not owner — change it to the
plpgsql RAISE pattern for consistency; the sql-language sketch above is only to show
the shape.)

Also update B4's `get_entity`: `p_type='place'` now returns `public.get_place(p_key::uuid)`.

### The capture path — Overland → Edge Function (ADR-0046), if Joe chose Overland
`supabase/functions/location-ingest/index.ts`:
- Accept POST only. Read the shared secret from `Authorization: Bearer <t>` **or**
  `?token=<t>` (Overland sends its "Access Token" — verify which form against the
  Overland README at github.com/aaronpk/Overland-iOS before writing; record in ADR-0046).
- Compare to `Deno.env.get('LOCATION_TOKEN')` with a constant-time compare; 401 otherwise.
- Forward the body unchanged to `supabase.rpc('ingest_location_batch', {p_batch: body})`
  using the **service-role** client (`SUPABASE_SERVICE_ROLE_KEY` is injected automatically).
- Respond `{"result":"ok"}` with 200; never log the body (REQ-LOC-002: no coordinate in a log line).
Deploy: `supabase functions deploy location-ingest --project-ref cykviouklidnbsbgdgdo --no-verify-jwt`
then `supabase secrets set LOCATION_TOKEN=<Joe generates: openssl rand -hex 24>`. Joe
runs `supabase login` himself (browser). The token is typed into Overland's settings
on the phone and into the secret; **never into chat or git**. Overland settings:
endpoint `https://cykviouklidnbsbgdgdo.functions.supabase.co/location-ingest`, tracking
mode "Significant location changes" (battery), send interval 5 minutes, batch on.

### Fallback — Shortcut, if Joe chose no third-party app
`tools/make_shortcut_location.py`, same generator pattern as `make_shortcut_night.py`:
a Shortcut "Log Location" = Get Current Location → Get Contents of URL (POST
`/rest/v1/rpc/ingest_location`, anon key header, body `{p_captured_at, p_lat, p_lon,
p_accuracy_m, p_source:'shortcut'}`). Joe attaches it to Automations on the phone
(Arrive/Leave places, and a few Time-of-Day triggers, "Run Immediately"). Plus a
Shortcut "Register this place" → `register_place` (magic-link session required;
if that is awkward on the phone, register places from THE DESK on desktop instead).

### B5.3 tests `tests/test_movements_api.py`
```
test_ADR_0036_get_movements_and_get_place_refuse_without_owner_jwt
test_REQ_LOC_002_no_movement_rpc_output_contains_a_coordinate_key_at_any_depth
    -> json-walk get_movements(today), get_movements(a synthetic day), get_place(a synthetic place), get_places();
       no key in {lat, lon, latitude, longitude, coordinates, c_lat, c_lon, geometry}
test_REQ_LOC_002_no_movement_rpc_output_contains_a_number_with_4_plus_decimals
test_REQ_LOC_015_get_movements_day_with_no_fixes_has_coverage_none_and_no_visits_and_no_last_known
test_REQ_LOC_016_unknown_visit_is_labelled_unknown_place_not_nearest
test_REQ_LOC_017_get_movements_carries_tier_descriptive_and_provisional_true
test_REQ_LOC_018_get_movements_renders_with_no_language_layer  (it is pure SQL; assert no http/extension call in 0040)
test_REQ_LOC_005_migrations_0038_0039_0040_and_edge_function_have_no_coordinate_literal
test_ADR_0046_edge_function_never_logs_body   (grep index.ts: no console.log of req/body)
```

### Done when (each session)
- Dry-run then apply pasted; the grants check pasted (`SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_schema='restricted'` → **zero rows**).
- B5.3: one real end-to-end fix from Joe's phone landed (`SELECT count(*) FROM restricted.location_fixes` before/after — counts only, pasted), `derive_visits` run, `get_movements(today)` pasted showing a visit or `coverage.status='partial'`.
- `tools/validate_layout.py` 40 checks, 0 failed. Tests pass. ADRs 0044–0046; DECISIONS rows; OQs (legacy 282 rows; thresholds; home geofence radius).
- PROGRESS + WHAT I DID NOT DO (must name: no inferred places — only human-registered; no transit/commute metrics; no legacy backfill; battery impact unmeasured).
