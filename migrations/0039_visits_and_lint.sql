-- 0039_visits_and_lint.sql — in-database visit derivation + the one public view of visits (ADR-0045;
-- REQ-LOC-011/012/013/015). Built under docs/build/B5_movements.md §B5.2 (session 17, 2026-09-02).
-- Deviations from B5's text, recorded in ADR-0045:
--   (a) the human-assignment stash is CREATE TEMP TABLE IF NOT EXISTS + DELETE, so derive_visits() can run
--       more than once in one transaction (the tests do); B5's CREATE TEMP TABLE would fail the second call.
--   (b) the three `places` domain_metrics rows self-register through config.ensure_places_metrics(), called
--       by the panel build, the first night analysis.panel carries `away_min` — seeding them now would break
--       B1's ratified rule/test that every seeded metric exists in the panel (ADR-0040). The hero_metric on
--       config.domains is set now (harmless: hero is absent until the panel has it).

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
    CREATE TEMP TABLE IF NOT EXISTS _human (arrive_at timestamptz, depart_at timestamptz, human_place_id uuid) ON COMMIT DROP;
    DELETE FROM _human;
    INSERT INTO _human SELECT arrive_at, depart_at, human_place_id FROM restricted.visits
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

-- ---------- the places domain gets a hero once the panel carries it ----------
UPDATE config.domains SET hero_metric='away_min', hero_unit='min' WHERE domain_key='places';

-- Self-registering seed (deviation (b)): inserts the three rows only when analysis.panel has away_min.
-- Called by tools/engines/panel.py at the end of every build; idempotent (ON CONFLICT DO NOTHING).
CREATE OR REPLACE FUNCTION config.ensure_places_metrics()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE n int := 0;
BEGIN
    IF EXISTS (SELECT 1 FROM analysis.panel WHERE metric = 'away_min') THEN
        INSERT INTO config.domain_metrics (domain_key, metric, display_name, unit, role, rounding, sort_order) VALUES
          ('places','away_min','Away','min','hero',0,1),
          ('places','home_min','At home','min','why',0,2),
          ('places','places_distinct','Distinct places','places','why',0,3)
        ON CONFLICT (domain_key, metric) DO NOTHING;
        GET DIAGNOSTICS n = ROW_COUNT;
    END IF;
    RETURN n;
END $fn$;
REVOKE ALL ON FUNCTION config.ensure_places_metrics() FROM PUBLIC, anon, authenticated, service_role;
SELECT config.ensure_places_metrics();
