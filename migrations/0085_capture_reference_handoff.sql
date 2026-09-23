-- Private immutable binding for isolated source requests and cache publication.
CREATE TABLE __CORE__.capture_reference_attempts (
    request_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL,
    extraction_request_id uuid NOT NULL,
    item_index integer NOT NULL CHECK(item_index>=0),
    source text NOT NULL CHECK(source IN ('usda_foundation','usda_branded','off_search')),
    expected_event_id bigint NOT NULL,
    attempt_no integer NOT NULL CHECK(attempt_no>0),
    payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
    payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[a-f0-9]{64}$'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(capture_id,extraction_request_id,item_index,source,attempt_no),
    FOREIGN KEY(capture_id,extraction_request_id)
        REFERENCES __CORE__.capture_extraction_outcomes(capture_id,request_id),
    FOREIGN KEY(capture_id,expected_event_id)
        REFERENCES __CORE__.capture_processing_events(raw_capture_id,event_id)
);
CREATE TABLE __CORE__.capture_reference_outcomes (
    request_id uuid PRIMARY KEY REFERENCES __CORE__.capture_reference_attempts(request_id),
    response_sha256 text CHECK(response_sha256 ~ '^[a-f0-9]{64}$'),
    receipt_outcome text NOT NULL CHECK(receipt_outcome IN ('settled','uncertain')),
    CHECK((receipt_outcome='settled')=(response_sha256 IS NOT NULL)),
    CHECK(receipt_outcome<>'uncertain' OR status IN ('deferred','stale')),
    status text NOT NULL CHECK(status IN ('resolved','unresolved','deferred','stale')),
    applied boolean NOT NULL,
    food_id uuid REFERENCES __CORE__.foods_cache(food_id),
    reason text CHECK(reason ~ '^[a-z0-9_]{1,128}$'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK((status='resolved')=(food_id IS NOT NULL)),
    CHECK(applied=(status<>'stale'))
);
ALTER TABLE __CORE__.capture_reference_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.capture_reference_outcomes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_reference_attempts,__CORE__.capture_reference_outcomes
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,reference_egress,service_role;
GRANT SELECT,INSERT ON __CORE__.capture_reference_attempts,__CORE__.capture_reference_outcomes TO service_role;
CREATE POLICY service_capture_reference_attempts ON __CORE__.capture_reference_attempts
    TO service_role USING(true) WITH CHECK(true);
CREATE POLICY service_capture_reference_outcomes ON __CORE__.capture_reference_outcomes
    TO service_role USING(true) WITH CHECK(true);
CREATE TRIGGER capture_reference_attempts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_reference_attempts FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER capture_reference_outcomes_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_reference_outcomes FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

-- Recovery must work for a lone queued item, without a new provider request.
-- The live dispatcher holds this same lock through settlement; acquiring it
-- therefore waits for that owner before deciding that a reservation is orphaned.
CREATE FUNCTION public.reconcile_reference_call(p_request_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_request __OPS__.reference_requests; v_now timestamptz;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED required';
    END IF;
    PERFORM pg_advisory_xact_lock(791554);
    SELECT * INTO v_request FROM __OPS__.reference_requests WHERE request_id=p_request_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'reference reservation required'; END IF;
    IF EXISTS(SELECT 1 FROM __OPS__.reference_results WHERE request_id=p_request_id) THEN
        RETURN;
    END IF;
    v_now := clock_timestamp();
    INSERT INTO __OPS__.reference_results(request_id,outcome,recorded_at)
        VALUES(p_request_id,'uncertain',v_now);
    UPDATE __OPS__.egress_log SET detail=detail||jsonb_build_object('state','uncertain')
        WHERE egress_id=v_request.egress_id;
    IF v_request.source LIKE 'usda_%' THEN
        INSERT INTO __OPS__.rate_limit_cooldowns(meter,blocked_until,reason,set_at)
        VALUES('usda',v_now+interval '60 minutes','dispatch_uncertain',v_now)
        ON CONFLICT(meter) DO UPDATE SET
            blocked_until=greatest(__OPS__.rate_limit_cooldowns.blocked_until,EXCLUDED.blocked_until),
            reason='dispatch_uncertain',set_at=EXCLUDED.set_at;
    END IF;
END $$;
REVOKE ALL ON FUNCTION public.reconcile_reference_call(uuid)
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,reference_egress;
GRANT EXECUTE ON FUNCTION public.reconcile_reference_call(uuid) TO service_role;

-- Source workers can publish a response through the narrow settlement RPC but
-- cannot retrieve historical bodies. Private consumers recover independently of
-- stdout delivery. Text preserves the exact bytes used by the receipt digest.
CREATE TABLE __OPS__.reference_response_bodies (
    request_id uuid PRIMARY KEY REFERENCES __OPS__.reference_results(request_id),
    response_body text NOT NULL CHECK(octet_length(response_body) BETWEEN 1 AND 4194304),
    CHECK(jsonb_typeof(response_body::jsonb)='object')
);
CREATE TRIGGER reference_response_bodies_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __OPS__.reference_response_bodies FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
REVOKE ALL ON __OPS__.reference_response_bodies
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,reference_egress,service_role;
GRANT SELECT ON __OPS__.reference_response_bodies TO service_role;

CREATE FUNCTION public.settle_reference_response(p_request_id uuid,p_body text,p_status integer DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_sha text; v_old text;
BEGIN
    IF p_body IS NULL OR octet_length(p_body) NOT BETWEEN 1 AND 4194304
        OR jsonb_typeof(p_body::jsonb)<>'object' THEN
        RAISE EXCEPTION 'invalid reference response body';
    END IF;
    v_sha := encode(sha256(convert_to(p_body,'UTF8')),'hex');
    -- Existing settlement validates identity/status and serializes on791554.
    -- A failing body insert rolls back the receipt as part of this statement.
    PERFORM public.settle_reference_call(p_request_id,v_sha,octet_length(p_body),p_status);
    SELECT response_body INTO v_old FROM __OPS__.reference_response_bodies WHERE request_id=p_request_id;
    IF FOUND THEN
        IF v_old IS DISTINCT FROM p_body THEN RAISE EXCEPTION 'reference response identity reused'; END IF;
        RETURN;
    END IF;
    INSERT INTO __OPS__.reference_response_bodies(request_id,response_body) VALUES(p_request_id,p_body);
END $$;
REVOKE ALL ON FUNCTION public.settle_reference_response(uuid,text,integer)
    FROM PUBLIC,anon,authenticated,service_role,capture_ingest,model_egress;
GRANT EXECUTE ON FUNCTION public.settle_reference_response(uuid,text,integer) TO reference_egress;
-- The source role must not bypass durable body publication via0084's old RPC.
REVOKE EXECUTE ON FUNCTION public.settle_reference_call(uuid,text,integer,integer) FROM reference_egress;
