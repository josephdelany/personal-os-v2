-- ADR0167: owner meal evidence is saved independently of nutrition processing.
CREATE TABLE __CORE__.v0_meal_entries (
    entry_id uuid PRIMARY KEY REFERENCES __CORE__.raw_captures(capture_id),
    supersedes uuid UNIQUE REFERENCES __CORE__.v0_meal_entries(entry_id),
    request jsonb NOT NULL,
    occurred_at timestamptz NOT NULL CHECK(isfinite(occurred_at)),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    subject_day date NOT NULL,
    photo_capture_id uuid REFERENCES __CORE__.raw_captures(capture_id)
);
ALTER TABLE __CORE__.v0_meal_entries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.v0_meal_entries FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER v0_meals_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.v0_meal_entries FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER v0_meals_recorded_at BEFORE INSERT ON __CORE__.v0_meal_entries
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE FUNCTION public.save_v0_meal(p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE cid uuid; prior uuid; at_time timestamptz; day date; photo uuid;
        keys text[]; saved __CORE__.v0_meal_entries; receipt jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF jsonb_typeof(p_request) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'meal object required';
    END IF;
    SELECT array_agg(k ORDER BY k) INTO keys FROM jsonb_object_keys(p_request) k;
    IF keys IS DISTINCT FROM ARRAY['entry_id','occurred_at','photo_capture_id','supersedes','text'] THEN
        RAISE EXCEPTION 'invalid meal fields';
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
    IF jsonb_typeof(p_request->'text') IS DISTINCT FROM 'string'
       OR length(p_request->>'text')>10000 THEN
        RAISE EXCEPTION 'meal text must be at most 10000 characters';
    END IF;
    IF p_request->'photo_capture_id' <> 'null'::jsonb THEN
        IF jsonb_typeof(p_request->'photo_capture_id') IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'invalid photo capture identity';
        END IF;
        photo := (p_request->>'photo_capture_id')::uuid;
        IF NOT EXISTS(SELECT 1 FROM __CORE__.raw_captures r
            JOIN __CORE__.capture_media_uploads u ON u.capture_id=r.capture_id
            JOIN __CORE__.capture_media_receipts v ON v.capture_id=u.capture_id AND v.sha256=u.sha256
            WHERE r.capture_id=photo AND r.source='shortcut_photo' AND u.media_kind='photo'
              AND r.payload->>'media_path'=u.media_path AND r.payload->>'media_sha256'=u.sha256) THEN
            RAISE EXCEPTION 'completed Shortcut photo capture required';
        END IF;
    END IF;
    IF btrim(p_request->>'text')='' AND photo IS NULL THEN
        RAISE EXCEPTION 'meal text or completed photo required';
    END IF;
    -- Single-owner writes are short; serialize identity and successor decisions.
    PERFORM pg_advisory_xact_lock(9167001);
    SELECT * INTO saved FROM __CORE__.v0_meal_entries WHERE entry_id=cid;
    IF FOUND THEN
        IF saved.request IS DISTINCT FROM p_request THEN
            RAISE EXCEPTION 'entry identity reused with changed contents';
        END IF;
        RETURN jsonb_build_object('status','saved','entry_id',cid,'recorded_at',saved.recorded_at,
                                  'subject_day',saved.subject_day,'definition','v0_meal_v1');
    END IF;
    IF prior IS NOT NULL THEN
        IF NOT EXISTS(SELECT 1 FROM __CORE__.v0_meal_entries e WHERE e.entry_id=prior)
           OR EXISTS(SELECT 1 FROM __CORE__.v0_meal_entries WHERE supersedes=prior) THEN
            RAISE EXCEPTION 'stale or unknown correction predecessor';
        END IF;
    END IF;
    IF EXISTS(SELECT 1 FROM __CORE__.raw_captures WHERE capture_id=cid) THEN
        RAISE EXCEPTION 'capture identity already used';
    END IF;
    day := (at_time AT TIME ZONE 'America/New_York' - interval '4 hours')::date;
    receipt := public.receive_capture(jsonb_build_object('capture_id',cid,
        'captured_at',p_request->>'occurred_at','source','pwa_text',
        'payload',jsonb_build_object('kind','food','definition','v0_meal_v1',
            'text',p_request->>'text','photo_capture_id',photo,'entry',p_request))::text);
    IF receipt->>'status' IS DISTINCT FROM 'created' THEN
        RAISE EXCEPTION 'meal capture could not be saved';
    END IF;
    INSERT INTO __CORE__.v0_meal_entries(entry_id,supersedes,request,occurred_at,subject_day,photo_capture_id)
        VALUES(cid,prior,p_request,at_time,day,photo) RETURNING * INTO saved;
    RETURN jsonb_build_object('status','saved','entry_id',cid,'recorded_at',saved.recorded_at,
                              'subject_day',day,'definition','v0_meal_v1');
END $$;
REVOKE ALL ON FUNCTION public.save_v0_meal(jsonb) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.save_v0_meal(jsonb) TO authenticated;

CREATE FUNCTION public.get_v0_meals(p_day date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE result jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF p_day IS NULL THEN RAISE EXCEPTION 'day required'; END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('entry_id',e.entry_id,'supersedes',e.supersedes,
        'occurred_at',e.occurred_at,'recorded_at',e.recorded_at,'subject_day',e.subject_day,
        'text',e.request->>'text','photo_capture_id',e.photo_capture_id,
        'photo',(SELECT jsonb_build_object('bucket','captures','path',u.media_path,
            'content_type',u.content_type,'size_bytes',u.size_bytes)
            FROM __CORE__.capture_media_uploads u WHERE u.capture_id=e.photo_capture_id),
        'definition','v0_meal_v1','save_status','saved',
        'nutrition',jsonb_build_object('status',CASE WHEN EXISTS(
            SELECT 1 FROM __CORE__.capture_resolved_items_current i WHERE i.capture_id=e.entry_id
                AND i.resolution->>'status' IS DISTINCT FROM 'removed')
            THEN 'results_available' WHEN EXISTS(SELECT 1 FROM __CORE__.capture_resolved_items_current i
                WHERE i.capture_id=e.entry_id) THEN 'removed' ELSE 'pending' END,
            'items',coalesce((SELECT jsonb_agg(jsonb_build_object('item_id',i.item_id,
                'item_index',i.item_index,'resolution',i.resolution) ORDER BY i.item_index)
                FROM __CORE__.capture_resolved_items_current i WHERE i.capture_id=e.entry_id),'[]'::jsonb)))
        ORDER BY e.occurred_at,e.recorded_at,e.entry_id),'[]'::jsonb) INTO result
        FROM __CORE__.v0_meal_entries e WHERE e.subject_day=p_day
        AND NOT EXISTS(SELECT 1 FROM __CORE__.v0_meal_entries n WHERE n.supersedes=e.entry_id);
    RETURN jsonb_build_object('day',p_day,'entries',result);
END $$;
REVOKE ALL ON FUNCTION public.get_v0_meals(date) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.get_v0_meals(date) TO authenticated;

-- Narrow lookup for authenticated Storage downloads; never permits public URLs.
CREATE FUNCTION public.v0_meal_photo_read_allowed(p_bucket text,p_name text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
    SELECT current_setting('role',true)='authenticated'
        AND coalesce(auth.jwt()->>'email','')='joseph.delany21@gmail.com'
        AND p_bucket='captures' AND EXISTS(
            SELECT 1 FROM __CORE__.v0_meal_entries e
            JOIN __CORE__.capture_media_uploads u ON u.capture_id=e.photo_capture_id
            JOIN __CORE__.capture_media_receipts r ON r.capture_id=u.capture_id AND r.sha256=u.sha256
            WHERE u.media_path=p_name AND u.media_kind='photo');
$$;
REVOKE ALL ON FUNCTION public.v0_meal_photo_read_allowed(text,text) FROM PUBLIC,anon;
-- PUBLIC restrictive Storage policies check function ACLs even on inactive branches.
-- Only Storage-facing roles may evaluate this lookup; capture_ingest remains excluded.
-- This boolean lookup returns false unless
-- the invoker role AND verified owner JWT match; it exposes no rows or URLs.
GRANT EXECUTE ON FUNCTION public.v0_meal_photo_read_allowed(text,text)
    TO anon,authenticated,service_role,capture_media_upload,capture_media_reader;
