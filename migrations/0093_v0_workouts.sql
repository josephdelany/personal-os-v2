-- ADR0169: owner-only individual workout sets, isolated from legacy extraction.
CREATE TABLE __CORE__.v0_workout_entries (
    entry_id uuid PRIMARY KEY REFERENCES __CORE__.raw_captures(capture_id),
    supersedes uuid UNIQUE REFERENCES __CORE__.v0_workout_entries(entry_id),
    request jsonb NOT NULL,
    occurred_at timestamptz NOT NULL CHECK(isfinite(occurred_at)),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    subject_day date NOT NULL,
    canonical_load_lb numeric,
    assistance_lb numeric
);
ALTER TABLE __CORE__.v0_workout_entries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.v0_workout_entries FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER v0_workouts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.v0_workout_entries FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER v0_workouts_recorded_at BEFORE INSERT ON __CORE__.v0_workout_entries
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE FUNCTION public.save_v0_workout(p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE cid uuid; prior uuid; at_time timestamptz; day date; mode text; load_value numeric;
        load_lb numeric; assistance numeric; reps numeric; rpe numeric; max_load numeric; max_reps numeric;
        keys text[]; key text; saved __CORE__.v0_workout_entries; receipt jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF jsonb_typeof(p_request) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'workout object required';
    END IF;
    SELECT array_agg(k ORDER BY k) INTO keys FROM jsonb_object_keys(p_request) k;
    IF keys IS DISTINCT FROM ARRAY['entry_id','exercise','load','load_unit','movement_mode','note','occurred_at','reps','rpe','supersedes'] THEN
        RAISE EXCEPTION 'invalid workout fields';
    END IF;
    IF jsonb_typeof(p_request->'entry_id') IS DISTINCT FROM 'string'
       OR (p_request->>'entry_id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
        RAISE EXCEPTION 'UUIDv7 entry identity required';
    END IF;
    cid := (p_request->>'entry_id')::uuid;
    -- Single-owner writes are short; serialize identity and successor decisions.
    PERFORM pg_advisory_xact_lock(9169001);
    SELECT * INTO saved FROM __CORE__.v0_workout_entries WHERE entry_id=cid;
    IF FOUND THEN
        IF saved.request IS DISTINCT FROM p_request THEN
            RAISE EXCEPTION 'entry identity reused with changed contents';
        END IF;
        RETURN jsonb_build_object('status','saved','entry_id',cid,'recorded_at',saved.recorded_at,
                                  'subject_day',saved.subject_day,'definition','v0_workout_v1');
    END IF;
    IF p_request->'supersedes' <> 'null'::jsonb THEN
        IF jsonb_typeof(p_request->'supersedes') IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'invalid correction predecessor';
        END IF;
        prior := (p_request->>'supersedes')::uuid;
    END IF;
    IF jsonb_typeof(p_request->'occurred_at') IS DISTINCT FROM 'string'
       OR (p_request->>'occurred_at') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$' THEN
        RAISE EXCEPTION 'explicit offset timestamp required';
    END IF;
    at_time := (p_request->>'occurred_at')::timestamptz;
    IF jsonb_typeof(p_request->'exercise') IS DISTINCT FROM 'string'
       OR length(btrim(p_request->>'exercise'))=0 OR length(p_request->>'exercise')>200 THEN
        RAISE EXCEPTION 'exercise text required, maximum 200 characters';
    END IF;
    IF jsonb_typeof(p_request->'note') IS DISTINCT FROM 'string'
       OR length(p_request->>'note')>4000 THEN
        RAISE EXCEPTION 'note must be text of at most 4000 characters';
    END IF;
    mode := p_request->>'movement_mode';
    IF mode IS NULL OR mode NOT IN ('external_load','bodyweight','assisted') THEN
        RAISE EXCEPTION 'explicit movement mode required';
    END IF;
    SELECT plausible_high INTO max_load FROM __CORE__.metric_registry WHERE metric_key='strength_load_lb';
    SELECT plausible_high INTO max_reps FROM __CORE__.metric_registry WHERE metric_key='strength_reps';
    IF max_load IS NULL OR max_reps IS NULL THEN RAISE EXCEPTION 'strength registry missing'; END IF;
    IF mode='bodyweight' THEN
        IF p_request->'load' <> 'null'::jsonb OR p_request->'load_unit' <> 'null'::jsonb THEN
            RAISE EXCEPTION 'bodyweight has no invented numeric load or unit';
        END IF;
    ELSE
        IF jsonb_typeof(p_request->'load') IS DISTINCT FROM 'number'
           OR (p_request->>'load')::numeric<=0
           OR coalesce(p_request->>'load_unit','') NOT IN ('lb','kg') THEN
            RAISE EXCEPTION 'positive stated load and lb or kg required';
        END IF;
        load_value := (p_request->>'load')::numeric;
        -- Exact international avoirdupois pound definition; store conversion once.
        IF p_request->>'load_unit'='kg' THEN load_value := load_value / 0.45359237; END IF;
        IF mode='external_load' AND load_value>max_load THEN
            RAISE EXCEPTION 'load outside registered bounds';
        END IF;
        IF mode='assisted' THEN assistance := load_value; ELSE load_lb := load_value; END IF;
    END IF;
    IF jsonb_typeof(p_request->'reps') IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION 'positive integer repetitions required';
    END IF;
    reps := (p_request->>'reps')::numeric;
    IF reps<1 OR reps>max_reps OR trunc(reps)<>reps THEN
        RAISE EXCEPTION 'repetitions outside registered integer bounds';
    END IF;
    IF p_request->'rpe' <> 'null'::jsonb THEN
        IF jsonb_typeof(p_request->'rpe') IS DISTINCT FROM 'number' THEN
            RAISE EXCEPTION 'RPE must be numeric or null';
        END IF;
        rpe := (p_request->>'rpe')::numeric;
        IF rpe NOT BETWEEN 0 AND 10 OR trunc(rpe*2)<>rpe*2 THEN
            RAISE EXCEPTION 'RPE uses existing 0–10 half-step scale';
        END IF;
    END IF;
    IF prior IS NOT NULL THEN
        IF NOT EXISTS(SELECT 1 FROM __CORE__.v0_workout_entries e WHERE e.entry_id=prior)
           OR EXISTS(SELECT 1 FROM __CORE__.v0_workout_entries WHERE supersedes=prior) THEN
            RAISE EXCEPTION 'stale or unknown correction predecessor';
        END IF;
    END IF;
    IF EXISTS(SELECT 1 FROM __CORE__.raw_captures WHERE capture_id=cid) THEN
        RAISE EXCEPTION 'capture identity already used';
    END IF;
    day := (at_time AT TIME ZONE 'America/New_York' - interval '4 hours')::date;
    receipt := public.receive_capture(jsonb_build_object('capture_id',cid,
        'captured_at',p_request->>'occurred_at','source','pwa_text',
        'payload',jsonb_build_object('kind','v0_workout','definition','v0_workout_v1',
            'entry',p_request))::text);
    IF receipt->>'status' IS DISTINCT FROM 'created' THEN
        RAISE EXCEPTION 'workout capture could not be saved';
    END IF;
    INSERT INTO __CORE__.v0_workout_entries(entry_id,supersedes,request,occurred_at,subject_day,canonical_load_lb,assistance_lb)
        VALUES(cid,prior,p_request,at_time,day,load_lb,assistance) RETURNING * INTO saved;
    RETURN jsonb_build_object('status','saved','entry_id',cid,'recorded_at',saved.recorded_at,
                              'subject_day',day,'definition','v0_workout_v1');
END $$;
REVOKE ALL ON FUNCTION public.save_v0_workout(jsonb) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.save_v0_workout(jsonb) TO authenticated;

CREATE FUNCTION public.get_v0_workouts(p_day date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE result jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF p_day IS NULL THEN RAISE EXCEPTION 'day required'; END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'entry_id',e.entry_id,'supersedes',e.supersedes,'occurred_at',e.occurred_at,
        'recorded_at',e.recorded_at,'subject_day',e.subject_day,'definition','v0_workout_v1',
        'save_status','saved','exercise',e.request->>'exercise','exercise_entity_id',null,
        'exercise_status','unresolved','movement_mode',e.request->>'movement_mode',
        'load',jsonb_build_object('stated_amount',e.request->'load','stated_unit',e.request->'load_unit',
            'external_load_lb',e.canonical_load_lb,'assistance_lb',e.assistance_lb),
        'reps',e.request->'reps',
        'rpe',CASE WHEN e.request->'rpe'='null'::jsonb THEN 'null'::jsonb ELSE
            jsonb_build_object('value',e.request->'rpe','scale',jsonb_build_array(0,10),
                              'step',0.5,'kind','self_report') END,
        'note',e.request->>'note') ORDER BY e.occurred_at,e.recorded_at,e.entry_id),'[]'::jsonb)
    INTO result FROM __CORE__.v0_workout_entries e WHERE e.subject_day=p_day
        AND NOT EXISTS(SELECT 1 FROM __CORE__.v0_workout_entries n WHERE n.supersedes=e.entry_id);
    RETURN jsonb_build_object('day',p_day,'entries',result);
END $$;
REVOKE ALL ON FUNCTION public.get_v0_workouts(date) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.get_v0_workouts(date) TO authenticated;
