-- ADR0172: keep original transport evidence and retry identity inside the boundary.
CREATE TABLE restricted.location_receipts (
    identity_sha256 text PRIMARY KEY CHECK(identity_sha256 ~ '^[a-f0-9]{64}$'),
    identity_record jsonb NOT NULL,
    source_record jsonb NOT NULL,
    raw_capture_id uuid NOT NULL UNIQUE REFERENCES __CORE__.raw_captures(capture_id),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON restricted.location_receipts FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER location_receipts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON restricted.location_receipts FOR EACH STATEMENT EXECUTE FUNCTION restricted.reject_mutation();
CREATE TRIGGER location_receipts_recorded_at BEFORE INSERT ON restricted.location_receipts
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

-- ADR0046 selected the authenticated edge transport. The unused public Shortcut
-- fallback must not bypass that capability; no built repository caller uses it.
REVOKE ALL ON FUNCTION public.ingest_location(uuid,timestamptz,float8,float8,numeric,numeric,numeric,text[],text)
    FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.ingest_location_batch(p_batch jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE f jsonb; identity_record jsonb; fingerprint text; saved restricted.location_receipts;
        cid uuid; n integer:=0; inserted integer:=0; duplicates integer:=0; k text;
        capture_ids jsonb:='[]'::jsonb;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'location import requires READ COMMITTED isolation';
    END IF;
    IF jsonb_typeof(p_batch) IS DISTINCT FROM 'object'
        OR jsonb_typeof(p_batch->'locations') IS DISTINCT FROM 'array'
        OR octet_length(p_batch::text)>1048576 THEN
        RAISE EXCEPTION 'bounded locations array required';
    END IF;
    IF jsonb_array_length(p_batch->'locations')>1000 THEN
        RAISE EXCEPTION 'location batch exceeds 1000 records';
    END IF;
    PERFORM pg_advisory_xact_lock(9172001);
    FOR f IN SELECT value FROM jsonb_array_elements(p_batch->'locations') LOOP
        IF f->>'type' IS DISTINCT FROM 'Feature'
            OR f->'geometry'->>'type' IS DISTINCT FROM 'Point'
            OR jsonb_typeof(f->'geometry'->'coordinates') IS DISTINCT FROM 'array'
            OR jsonb_typeof(f->'properties') IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'location point feature required';
        END IF;
        IF jsonb_array_length(f->'geometry'->'coordinates') NOT IN (2,3)
            OR jsonb_typeof(f->'geometry'->'coordinates'->0) IS DISTINCT FROM 'number'
            OR jsonb_typeof(f->'geometry'->'coordinates'->1) IS DISTINCT FROM 'number'
            OR jsonb_typeof(f->'properties'->'timestamp') IS DISTINCT FROM 'string'
            OR f->'properties'->>'timestamp' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?([zZ]|[+-]([01][0-9]|2[0-3]):?[0-5][0-9])$' THEN
            RAISE EXCEPTION 'location values and timezone-bearing timestamp required';
        END IF;
        FOREACH k IN ARRAY ARRAY['horizontal_accuracy','speed','battery_level'] LOOP
            IF coalesce(jsonb_typeof(f->'properties'->k),'null') NOT IN ('number','null') THEN
                RAISE EXCEPTION 'invalid location measurement type';
            END IF;
        END LOOP;
        IF coalesce(jsonb_typeof(f->'properties'->'motion'),'null') NOT IN ('array','null') THEN
            RAISE EXCEPTION 'motion array required';
        END IF;
        IF EXISTS(SELECT 1 FROM jsonb_array_elements(
            coalesce(nullif(f->'properties'->'motion','null'::jsonb),'[]'::jsonb)) x
            WHERE jsonb_typeof(x) IS DISTINCT FROM 'string') THEN
            RAISE EXCEPTION 'motion states must be strings';
        END IF;
        -- A batch may be split/reordered on retry. Overland explicitly documents
        -- this one property as a transport count, not a measurement identity.
        identity_record:=jsonb_set(f,'{properties}',(f->'properties')-'locations_in_payload');
        fingerprint:=encode(sha256(convert_to(identity_record::text,'UTF8')),'hex');
        SELECT * INTO saved FROM restricted.location_receipts r WHERE r.identity_sha256=fingerprint;
        IF FOUND THEN
            IF saved.identity_record IS DISTINCT FROM identity_record THEN
                RAISE EXCEPTION 'location identity collision';
            END IF;
            duplicates:=duplicates+1;
            cid:=saved.raw_capture_id;
        ELSE
            cid:=gen_random_uuid();
            PERFORM public.ingest_location(cid,
                (f->'properties'->>'timestamp')::timestamptz,
                (f->'geometry'->'coordinates'->>1)::float8,
                (f->'geometry'->'coordinates'->>0)::float8,
                (f->'properties'->>'horizontal_accuracy')::numeric,
                (f->'properties'->>'speed')::numeric,
                (f->'properties'->>'battery_level')::numeric,
                (SELECT array_agg(x) FROM jsonb_array_elements_text(
                    coalesce(nullif(f->'properties'->'motion','null'::jsonb),'[]'::jsonb)) x),
                'overland');
            INSERT INTO restricted.location_receipts(identity_sha256,identity_record,source_record,raw_capture_id)
                VALUES(fingerprint,identity_record,f,cid);
            inserted:=inserted+1;
        END IF;
        capture_ids:=capture_ids || jsonb_build_array(cid);
        n:=n+1;
    END LOOP;
    RETURN jsonb_build_object('result','ok','n',n,'inserted',inserted,'duplicates',duplicates,
        'capture_ids',capture_ids);
END $$;
REVOKE ALL ON FUNCTION public.ingest_location_batch(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_location_batch(jsonb) TO service_role;

-- Retain exact contributing observations; expose only the stored observed span.
ALTER TABLE restricted.visits ADD COLUMN source_capture_ids uuid[];
ALTER TABLE restricted.visits ADD COLUMN observed_span_min numeric
    GENERATED ALWAYS AS (extract(epoch FROM depart_at-arrive_at)/60) STORED;
ALTER TABLE restricted.visits ALTER COLUMN computed_at SET DEFAULT clock_timestamp();
ALTER TABLE restricted.location_fixes ALTER COLUMN recorded_at SET DEFAULT clock_timestamp();
CREATE TRIGGER v0_location_fixes_recorded_at BEFORE INSERT ON restricted.location_fixes
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();
-- Same derivation owner/thresholds as0039. Add inputs, stable tie order and reject
-- negative accuracy as an unusable distance bound; human assignment logic remains.
CREATE OR REPLACE FUNCTION restricted.derive_visits(p_from date)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    rmax float8; dmin numeric; gmax numeric; amax numeric;
    f record; n int := 0;
    cur_lat float8; cur_lon float8; cur_n int := 0; cur_start timestamptz; cur_last timestamptz; cur_inputs uuid[] := '{}';
    start_at timestamptz; earlier timestamptz;
BEGIN
    SELECT v INTO rmax FROM restricted.visit_params WHERE k='stay_radius_m';
    SELECT v INTO dmin FROM restricted.visit_params WHERE k='min_dwell_min';
    SELECT v INTO gmax FROM restricted.visit_params WHERE k='max_gap_min';
    SELECT v INTO amax FROM restricted.visit_params WHERE k='max_accuracy_m';
    -- Rebuild whole affected stays, including one gap of preceding context.
    -- A date-only cut otherwise duplicates a stay that began before the cut.
    start_at := (p_from::timestamp+interval '4 hours') AT TIME ZONE 'America/New_York';
    SELECT least(start_at,
        (SELECT min(arrive_at) FROM restricted.visits
            WHERE depart_at>=start_at-(gmax||' minutes')::interval),
        (SELECT min(captured_at) FROM restricted.location_fixes
            WHERE captured_at>=start_at-(gmax||' minutes')::interval AND captured_at<start_at))
        INTO start_at;
    LOOP
        SELECT min(arrive_at) INTO earlier FROM restricted.visits
            WHERE depart_at>=start_at AND arrive_at<start_at;
        EXIT WHEN earlier IS NULL;
        start_at:=earlier;
    END LOOP;
    -- preserve human assignments across rebuilds: stash (arrive_at, human_place_id) then re-apply by overlap
    CREATE TEMP TABLE IF NOT EXISTS _human (arrive_at timestamptz, depart_at timestamptz, human_place_id uuid) ON COMMIT DROP;
    DELETE FROM _human;
    INSERT INTO _human SELECT arrive_at, depart_at, human_place_id FROM restricted.visits
                        WHERE depart_at >= start_at AND human_place_id IS NOT NULL;
    DELETE FROM restricted.visits WHERE depart_at >= start_at;
    FOR f IN SELECT raw_capture_id, captured_at, lat, lon, subject_day, subject_day_rule_version
               FROM restricted.location_fixes
              WHERE captured_at >= start_at AND (accuracy_m IS NULL OR (accuracy_m >= 0 AND accuracy_m <= amax))
              ORDER BY captured_at,raw_capture_id LOOP
        IF cur_n > 0 AND restricted.dist_m(cur_lat, cur_lon, f.lat, f.lon) <= rmax
           AND f.captured_at - cur_last <= (gmax || ' minutes')::interval THEN
            cur_lat := (cur_lat*cur_n + f.lat)/(cur_n+1); cur_lon := (cur_lon*cur_n + f.lon)/(cur_n+1);
            cur_n := cur_n + 1; cur_last := f.captured_at; cur_inputs := array_append(cur_inputs,f.raw_capture_id);
        ELSE
            IF cur_n > 0 AND cur_last - cur_start >= (dmin || ' minutes')::interval THEN
                IF (SELECT count(DISTINCT human_place_id) FROM _human h
                    WHERE tstzrange(h.arrive_at,h.depart_at,'[]') && tstzrange(cur_start,cur_last,'[]'))>1 THEN
                    RAISE EXCEPTION 'visit refresh would merge conflicting human assignments';
                END IF;
                INSERT INTO restricted.visits (place_id, arrive_at, depart_at, subject_day, n_fixes, c_lat, c_lon, code_version, source_capture_ids)
                SELECT (SELECT place_id FROM restricted.places_current p
                         WHERE restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) <= p.radius_m
                         ORDER BY restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) LIMIT 1),
                       cur_start, cur_last, ((cur_start AT TIME ZONE 'America/New_York') - interval '4 hours')::date, cur_n, cur_lat, cur_lon, 'visits-v2', cur_inputs;
                n := n + 1;
            END IF;
            cur_lat := f.lat; cur_lon := f.lon; cur_n := 1; cur_start := f.captured_at; cur_last := f.captured_at; cur_inputs := ARRAY[f.raw_capture_id];
        END IF;
    END LOOP;
    IF cur_n > 0 AND cur_last - cur_start >= (dmin || ' minutes')::interval THEN
        IF (SELECT count(DISTINCT human_place_id) FROM _human h
                    WHERE tstzrange(h.arrive_at,h.depart_at,'[]') && tstzrange(cur_start,cur_last,'[]'))>1 THEN
                    RAISE EXCEPTION 'visit refresh would merge conflicting human assignments';
                END IF;
                INSERT INTO restricted.visits (place_id, arrive_at, depart_at, subject_day, n_fixes, c_lat, c_lon, code_version, source_capture_ids)
        SELECT (SELECT place_id FROM restricted.places_current p
                 WHERE restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) <= p.radius_m
                 ORDER BY restricted.dist_m(p.lat, p.lon, cur_lat, cur_lon) LIMIT 1),
               cur_start, cur_last, ((cur_start AT TIME ZONE 'America/New_York') - interval '4 hours')::date, cur_n, cur_lat, cur_lon, 'visits-v2', cur_inputs;
        n := n + 1;
    END IF;
    UPDATE restricted.visits v SET human_place_id = h.human_place_id
      FROM _human h WHERE v.arrive_at >= start_at
       AND tstzrange(v.arrive_at, v.depart_at) && tstzrange(h.arrive_at, h.depart_at);
    RETURN n;
END $fn$;
REVOKE ALL ON FUNCTION restricted.derive_visits(date) FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE restricted.v0_visit_refreshes (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_day date NOT NULL,
    input_recorded_through timestamptz NOT NULL,
    visits_written integer NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON restricted.v0_visit_refreshes FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER v0_visit_refreshes_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON restricted.v0_visit_refreshes FOR EACH STATEMENT EXECUTE FUNCTION restricted.reject_mutation();
CREATE TRIGGER v0_visit_refreshes_recorded_at BEFORE INSERT ON restricted.v0_visit_refreshes
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE FUNCTION public.refresh_v0_visits() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE prior timestamptz; through_time timestamptz; from_day date; written integer;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'visit refresh requires READ COMMITTED isolation';
    END IF;
    PERFORM pg_advisory_xact_lock(9172001);
    through_time:=clock_timestamp();
    SELECT coalesce(max(input_recorded_through),'-infinity'::timestamptz)
        INTO prior FROM restricted.v0_visit_refreshes;
    SELECT least((through_time AT TIME ZONE 'America/New_York'-interval '4 hours')::date-3,
        min(f.subject_day),CASE WHEN prior='-infinity'::timestamptz
            THEN (SELECT min(subject_day) FROM restricted.location_fixes) END) INTO from_day
        FROM restricted.location_receipts r
        JOIN restricted.location_fixes f ON f.raw_capture_id=r.raw_capture_id
        WHERE r.recorded_at>prior AND r.recorded_at<=through_time;
    written:=restricted.derive_visits(from_day);
    INSERT INTO restricted.v0_visit_refreshes(from_day,input_recorded_through,visits_written)
        VALUES(from_day,through_time,written);
    RETURN written;
END $$;
REVOKE ALL ON FUNCTION public.refresh_v0_visits() FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE restricted.v0_visit_reads (
    read_id uuid PRIMARY KEY,
    subject_day date NOT NULL,
    result jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON restricted.v0_visit_reads FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER v0_visit_reads_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON restricted.v0_visit_reads FOR EACH STATEMENT EXECUTE FUNCTION restricted.reject_mutation();
CREATE TRIGGER v0_visit_reads_recorded_at BEFORE INSERT ON restricted.v0_visit_reads
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE FUNCTION public.get_v0_visits(p_day date DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE d date; t0 timestamptz; t1 timestamptz; answer jsonb; identity uuid:=gen_random_uuid();
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    d:=coalesce(p_day,(statement_timestamp() AT TIME ZONE 'America/New_York'-interval '4 hours')::date);
    IF NOT isfinite(d) THEN RAISE EXCEPTION 'finite subject day required'; END IF;
    t0:=(d::timestamp+interval '4 hours') AT TIME ZONE 'America/New_York';
    t1:=((d+1)::timestamp+interval '4 hours') AT TIME ZONE 'America/New_York';
    WITH fixes AS MATERIALIZED (
        SELECT f.raw_capture_id,f.captured_at,r.recorded_at
        FROM restricted.location_fixes f JOIN __CORE__.raw_captures r ON r.capture_id=f.raw_capture_id
        WHERE f.captured_at>=t0 AND f.captured_at<t1
    ), refresh AS (
        SELECT max(input_recorded_through) AS through_time FROM restricted.v0_visit_refreshes
    ), visits AS MATERIALIZED (
        SELECT v.*,p.label,p.kind,p.is_home,
            coalesce(v.human_place_id,v.place_id) AS resolved_place_id
        FROM restricted.visits v LEFT JOIN restricted.places_current p
            ON p.place_id=coalesce(v.human_place_id,v.place_id)
        WHERE v.arrive_at<t1 AND v.depart_at>=t0 AND v.source_capture_ids IS NOT NULL
    ) SELECT jsonb_build_object(
        'read_id',identity,'day',d,'timezone','America/New_York','day_start',t0,'day_end',t1,
        'tier','DESCRIPTIVE','provisional',true,'history_mode','current derived visits and human assignments',
        'view_scope','whole visits overlapping this subject-day window',
        'code_version','v0_visit_read_v1','computed_at',clock_timestamp(),
        'entries',coalesce((SELECT jsonb_agg(jsonb_build_object(
            'visit_id',visit_id,'source_subject_day',subject_day,'place_id',resolved_place_id,'label',coalesce(label,'unknown place'),
            'kind',kind,'is_home',is_home,'first_observed_at',arrive_at,'last_observed_at',depart_at,
            'observed_span_min',observed_span_min,'unit','min','n_fixes',n_fixes,
            'lane','observed','method','provisional_stay_detection',
            'span_semantics','first to last observation, not proof of continuous presence',
            'place_resolution',CASE WHEN human_place_id IS NOT NULL THEN 'human'
                WHEN place_id IS NOT NULL THEN 'registered_radius' ELSE 'unknown' END,
            'source_capture_ids',source_capture_ids,'code_version',code_version,'derived_at',computed_at,
            'last_received_at',(SELECT max(recorded_at) FROM __CORE__.raw_captures
                WHERE capture_id=ANY(source_capture_ids))) ORDER BY arrive_at,visit_id) FROM visits),'[]'::jsonb),
        'coverage',jsonb_build_object('fix_count',(SELECT count(*) FROM fixes),
            'presence','unknown','first_event_at',(SELECT min(captured_at) FROM fixes),
            'last_event_at',(SELECT max(captured_at) FROM fixes),
            'last_received_at',(SELECT max(recorded_at) FROM fixes),
            'source_capture_ids',coalesce((SELECT jsonb_agg(raw_capture_id ORDER BY captured_at,raw_capture_id)
                FROM fixes),'[]'::jsonb)),
        'processing_status',CASE WHEN NOT EXISTS(SELECT 1 FROM fixes) AND NOT EXISTS(SELECT 1 FROM visits)
            THEN 'missing'
            WHEN (SELECT max(recorded_at) FROM fixes)>(SELECT through_time FROM refresh)
                OR (SELECT through_time FROM refresh) IS NULL
                OR EXISTS(SELECT 1 FROM restricted.visits WHERE arrive_at<t1 AND depart_at>=t0 AND source_capture_ids IS NULL)
            THEN 'awaiting_derivation'
            WHEN NOT EXISTS(SELECT 1 FROM visits) THEN 'no_detected_visits'
            ELSE 'available' END,
        'last_refresh_at',(SELECT through_time FROM refresh)
    ) INTO answer;
    INSERT INTO restricted.v0_visit_reads(read_id,subject_day,result) VALUES(identity,d,answer);
    RETURN answer;
END $$;
REVOKE ALL ON FUNCTION public.get_v0_visits(date) FROM PUBLIC,anon,service_role;
GRANT EXECUTE ON FUNCTION public.get_v0_visits(date) TO authenticated;

-- Reuse the existing day owner without copying its health/entry computations.
ALTER FUNCTION public.get_v0_day(date) SET SCHEMA __CORE__;
REVOKE ALL ON FUNCTION __CORE__.get_v0_day(date) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION public.get_v0_day(p_day date DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE answer jsonb; d date; account uuid; cards jsonb:='[]'::jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    answer:=__CORE__.get_v0_day(p_day);
    d:=(answer->>'day')::date;
    FOR account IN SELECT DISTINCT account_id FROM __CORE__.v0_card_files ORDER BY account_id LOOP
        cards:=cards||jsonb_build_array(public.get_v0_card_activity(account,d,d));
    END LOOP;
    RETURN answer||jsonb_build_object('visits',public.get_v0_visits(d),
        'spending',jsonb_build_object('accounts',cards,
            'date_basis','source transaction calendar date; no intraday timestamp supplied',
            'scope','imported card activity; unresolved exclusions remain visible'));
END $$;
REVOKE ALL ON FUNCTION public.get_v0_day(date) FROM PUBLIC,anon,service_role;
GRANT EXECUTE ON FUNCTION public.get_v0_day(date) TO authenticated;
