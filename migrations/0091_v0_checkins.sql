-- ADR0166: owner-only structured check-ins, isolated from legacy 0–10 data.
CREATE TABLE __CORE__.v0_checkin_entries (
    entry_id uuid PRIMARY KEY REFERENCES __CORE__.raw_captures(capture_id),
    supersedes uuid UNIQUE REFERENCES __CORE__.v0_checkin_entries(entry_id),
    request jsonb NOT NULL,
    occurred_at timestamptz NOT NULL CHECK(isfinite(occurred_at)),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    subject_day date NOT NULL,
    period text NOT NULL CHECK(period IN ('morning','evening'))
);
ALTER TABLE __CORE__.v0_checkin_entries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.v0_checkin_entries FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER v0_checkins_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.v0_checkin_entries FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER v0_checkins_recorded_at BEFORE INSERT ON __CORE__.v0_checkin_entries
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE FUNCTION public.save_v0_checkin(p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE cid uuid; prior uuid; at_time timestamptz; day date; period text;
        keys text[]; key text; saved __CORE__.v0_checkin_entries; receipt jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF jsonb_typeof(p_request) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'check-in object required';
    END IF;
    SELECT array_agg(k ORDER BY k) INTO keys FROM jsonb_object_keys(p_request) k;
    IF keys IS DISTINCT FROM ARRAY['entry_id','note','occurred_at','period','ratings','supersedes'] THEN
        RAISE EXCEPTION 'invalid check-in fields';
    END IF;
    IF jsonb_typeof(p_request->'entry_id') IS DISTINCT FROM 'string'
       OR (p_request->>'entry_id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
        RAISE EXCEPTION 'UUIDv7 entry identity required';
    END IF;
    cid := (p_request->>'entry_id')::uuid;
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
    period := p_request->>'period';
    IF period IS NULL OR period NOT IN ('morning','evening') THEN
        RAISE EXCEPTION 'invalid check-in period';
    END IF;
    IF jsonb_typeof(p_request->'note') IS DISTINCT FROM 'string'
       OR length(p_request->>'note')>4000 THEN
        RAISE EXCEPTION 'note must be text of at most 4000 characters';
    END IF;
    IF jsonb_typeof(p_request->'ratings') IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'ratings object required';
    END IF;
    SELECT array_agg(k ORDER BY k) INTO keys FROM jsonb_object_keys(p_request->'ratings') k;
    IF keys IS DISTINCT FROM (CASE WHEN period='morning' THEN ARRAY['energy','sleep_quality'] ELSE ARRAY['energy','mood'] END) THEN
        RAISE EXCEPTION 'invalid rating fields';
    END IF;
    FOREACH key IN ARRAY keys LOOP
        IF jsonb_typeof(p_request->'ratings'->key) IS DISTINCT FROM 'number'
           OR (p_request->'ratings'->>key)::numeric NOT BETWEEN 1 AND 10
           OR trunc((p_request->'ratings'->>key)::numeric)<>(p_request->'ratings'->>key)::numeric THEN
            RAISE EXCEPTION 'ratings must be integers from 1 to 10';
        END IF;
    END LOOP;
    -- Single-owner writes are short; serialize identity and successor decisions.
    PERFORM pg_advisory_xact_lock(9166001);
    SELECT * INTO saved FROM __CORE__.v0_checkin_entries WHERE entry_id=cid;
    IF FOUND THEN
        IF saved.request IS DISTINCT FROM p_request THEN
            RAISE EXCEPTION 'entry identity reused with changed contents';
        END IF;
        RETURN jsonb_build_object('status','saved','entry_id',cid,'recorded_at',saved.recorded_at,
                                  'subject_day',saved.subject_day,'definition','v0_checkin_v1');
    END IF;
    IF prior IS NOT NULL THEN
        IF NOT EXISTS(SELECT 1 FROM __CORE__.v0_checkin_entries e WHERE e.entry_id=prior)
           OR EXISTS(SELECT 1 FROM __CORE__.v0_checkin_entries WHERE supersedes=prior) THEN
            RAISE EXCEPTION 'stale or unknown correction predecessor';
        END IF;
    END IF;
    IF EXISTS(SELECT 1 FROM __CORE__.raw_captures WHERE capture_id=cid) THEN
        RAISE EXCEPTION 'capture identity already used';
    END IF;
    day := (at_time AT TIME ZONE 'America/New_York' - interval '4 hours')::date;
    receipt := public.receive_capture(jsonb_build_object('capture_id',cid,
        'captured_at',p_request->>'occurred_at','source','pwa_text',
        'payload',jsonb_build_object('kind','v0_checkin','definition','v0_checkin_v1',
            'response_scale',jsonb_build_array(1,10),'entry',p_request))::text);
    IF receipt->>'status' IS DISTINCT FROM 'created' THEN
        RAISE EXCEPTION 'check-in capture could not be saved';
    END IF;
    INSERT INTO __CORE__.v0_checkin_entries(entry_id,supersedes,request,occurred_at,subject_day,period)
        VALUES(cid,prior,p_request,at_time,day,period) RETURNING * INTO saved;
    RETURN jsonb_build_object('status','saved','entry_id',cid,'recorded_at',saved.recorded_at,
                              'subject_day',day,'definition','v0_checkin_v1');
END $$;
REVOKE ALL ON FUNCTION public.save_v0_checkin(jsonb) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.save_v0_checkin(jsonb) TO authenticated;

CREATE FUNCTION public.get_v0_checkins(p_day date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE result jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF p_day IS NULL THEN RAISE EXCEPTION 'day required'; END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('entry_id',e.entry_id,'supersedes',e.supersedes,
        'occurred_at',e.occurred_at,'recorded_at',e.recorded_at,'subject_day',e.subject_day,
        'period',e.period,'ratings',e.request->'ratings','note',e.request->>'note',
        'definition','v0_checkin_v1','response_scale',jsonb_build_array(1,10))
        ORDER BY e.occurred_at,e.recorded_at,e.entry_id),'[]'::jsonb) INTO result
        FROM __CORE__.v0_checkin_entries e WHERE e.subject_day=p_day
        AND NOT EXISTS(SELECT 1 FROM __CORE__.v0_checkin_entries n WHERE n.supersedes=e.entry_id);
    RETURN jsonb_build_object('day',p_day,'entries',result);
END $$;
REVOKE ALL ON FUNCTION public.get_v0_checkins(date) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.get_v0_checkins(date) TO authenticated;
