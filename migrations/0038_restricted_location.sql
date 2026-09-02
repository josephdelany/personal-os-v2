-- 0038_restricted_location.sql — the restricted coordinate store (ADR-0044; REQ-LOC-001/002/004/006/008/009)
-- Built under docs/build/B5_movements.md §B5.1 (session 17, 2026-09-02).
-- Coordinates enter this schema and never leave it: zero grants; the only readers are SECURITY DEFINER
-- functions inside the database; no file outside migrations/ may name a restricted table (lint, B5.2).
-- IF NOT EXISTS everywhere: restricted.* and analysis.* are literal (not tokenised), so a re-apply
-- against live objects is a no-op. The pytest fixture rewrites the schema name into a disposable one.
-- Deviations from B5's text, recorded in ADR-0044:
--   (a) raw_captures.processing_status = 'enriched' (B5 wrote 'extracted', which the live CHECK
--       received|pending_enrichment|enriched|failed rejects); a location capture needs no extraction.
--   (b) the append-only trigger is a copy of core.reject_mutation() living in restricted (B5 said copy),
--       attached idempotently via a DO block (CREATE TRIGGER has no IF NOT EXISTS).

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

-- append-only (INV-2): the same statement-level mutation rejection as core.atoms (migration 0012)
CREATE OR REPLACE FUNCTION restricted.reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
      'RULE-02: % on % is forbidden; the table is append-only. Corrections supersede, never edit.',
      TG_OP, TG_TABLE_NAME
      USING ERRCODE = 'insufficient_privilege';
END;
$$;
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgname = 'location_fixes_append_only'
                      AND tgrelid = 'restricted.location_fixes'::regclass) THEN
        CREATE TRIGGER location_fixes_append_only
            BEFORE UPDATE OR DELETE OR TRUNCATE ON restricted.location_fixes
            FOR EACH STATEMENT EXECUTE FUNCTION restricted.reject_mutation();
    END IF;
END $do$;

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

-- ---------- ingress: coordinates go to restricted; raw_captures gets a REDACTED payload ----------
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
            jsonb_build_object('kind','location','redacted',true,'source',p_source), 'enriched')
    ON CONFLICT (capture_id) DO NOTHING;
    IF NOT FOUND THEN RETURN jsonb_build_object('ok', true, 'duplicate', true); END IF;
    INSERT INTO restricted.location_fixes
        (raw_capture_id, captured_at, lat, lon, accuracy_m, speed_mps, battery, motion, source, trust_level,
         subject_day, subject_day_rule_version)
    VALUES (cid, p_captured_at, p_lat, p_lon, p_accuracy_m, p_speed_mps, p_battery, p_motion, p_source, 'trusted',
            ((p_captured_at AT TIME ZONE 'America/New_York') - interval '4 hours')::date, 'v1-2026-08-23');
            -- same rule and literal as tools/extract_checkins.py subject_day()/RULE_VERSION (ADR-0019: 04:00 ET, by start) — verified 2026-09-02
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

-- ---------- place registration and human correction. Owner only. ----------
-- REQ-LOC-006/008, RULE-10. Called from "Register this place" with the phone's current fix.
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
