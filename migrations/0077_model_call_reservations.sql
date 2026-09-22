-- ADR-0146. One serialized budget reservation; caller must COMMIT before dispatch.
-- This RPC receipt alone is not evidence that the reservation is durable.
-- No password is provisioned by migration; deployment supplies it through secrets.
CREATE ROLE model_egress LOGIN PASSWORD NULL NOINHERIT NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE TABLE __CORE__.model_call_reservations (
    request_id uuid PRIMARY KEY,
    ledger_id uuid NOT NULL UNIQUE REFERENCES __CORE__.neuron_ledger(ledger_id),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE __CORE__.model_call_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.model_call_reservations FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER model_call_reservations_immutable
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.model_call_reservations
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

-- Internal eligibility owner: the public RPC always supplies its server clock.
CREATE FUNCTION __CORE__.model_retry_budget_eligible(p_capture_id uuid,p_kind text,p_now timestamptz)
RETURNS boolean LANGUAGE sql STABLE SET search_path='' AS $fn$
    SELECT p_kind <> 'plan' AND c.processing_status='deferred_budget' AND EXISTS (
            SELECT 1 FROM __CORE__.capture_processing_events ev
             WHERE ev.raw_capture_id=c.capture_id AND ev.applied
               AND ev.processing_status='deferred_budget'
               AND (ev.recorded_at AT TIME ZONE 'UTC')::date < (p_now AT TIME ZONE 'UTC')::date
               AND NOT EXISTS (
                   SELECT 1 FROM __CORE__.capture_processing_events terminal
                    WHERE terminal.raw_capture_id=c.capture_id AND terminal.applied
                      AND terminal.event_id > ev.event_id
                      AND terminal.processing_status IN ('enriched','failed'))
        ) FROM __CORE__.capture_processing_current c WHERE c.capture_id=p_capture_id;
$fn$;
REVOKE ALL ON FUNCTION __CORE__.model_retry_budget_eligible(uuid,text,timestamptz) FROM PUBLIC;

CREATE FUNCTION public.reserve_model_call(
    p_request_id uuid, p_model text, p_kind text, p_estimated numeric,
    p_capture_id uuid, p_request_bytes integer, p_payload_sha256 text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE previous record; spent numeric; ceiling numeric := 9000;
        ledger uuid; egress uuid; call_time timestamptz; deferred boolean := false;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='25001';
    END IF;
    IF p_request_id IS NULL OR p_model IS NULL OR p_model !~ '^@cf/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$'
       OR p_kind IS NULL OR p_kind NOT IN ('transcribe','extract','plan','nutrition','verify')
       OR p_estimated IS NULL OR p_estimated::text IN ('NaN','Infinity','-Infinity')
       OR p_estimated <= 0 OR p_estimated > 10000
       OR p_request_bytes IS NULL OR p_request_bytes <= 0
       OR p_payload_sha256 IS NULL OR p_payload_sha256 !~ '^[a-f0-9]{64}$' THEN
        RAISE EXCEPTION 'invalid model reservation' USING ERRCODE='22023';
    END IF;
    -- One lock across all consumers and UTC days. Take the clock AFTER waiting.
    PERFORM pg_catalog.pg_advisory_xact_lock(770035);
    call_time := clock_timestamp();
    SELECT n.*, r.payload_sha256, e.request_bytes INTO previous
      FROM __CORE__.model_call_reservations r
      JOIN __CORE__.neuron_ledger n USING (ledger_id)
      JOIN __OPS__.egress_log e USING (egress_id)
     WHERE r.request_id=p_request_id;
    IF FOUND THEN
        IF previous.model_id IS DISTINCT FROM p_model OR previous.call_kind IS DISTINCT FROM p_kind
           OR previous.estimated_neurons IS DISTINCT FROM p_estimated
           OR previous.capture_id IS DISTINCT FROM p_capture_id
           OR previous.request_bytes IS DISTINCT FROM p_request_bytes
           OR previous.payload_sha256 IS DISTINCT FROM p_payload_sha256 THEN
            RAISE EXCEPTION 'request identity reused with different content' USING ERRCODE='22023';
        END IF;
        -- A duplicate must NEVER authorize another send: the first send may have happened.
        RETURN jsonb_build_object('allowed',false,'duplicate',true,'reason','already_reserved');
    END IF;
    IF p_capture_id IS NOT NULL THEN
        SELECT __CORE__.model_retry_budget_eligible(p_capture_id,p_kind,call_time)
          INTO deferred;
        IF deferred IS NULL THEN
            RAISE EXCEPTION 'capture unavailable' USING ERRCODE='22023';
        END IF;
    END IF;
    IF deferred THEN ceiling := 10000; END IF;
    SELECT coalesce(sum(estimated_neurons),0) INTO spent FROM __CORE__.neuron_ledger
     WHERE (called_at AT TIME ZONE 'UTC')::date=(call_time AT TIME ZONE 'UTC')::date
       AND outcome <> 'refused_budget';
    IF spent+p_estimated > ceiling THEN
        RETURN jsonb_build_object('allowed',false,'duplicate',false,'spent',spent,
            'ceiling',ceiling,'reason',CASE WHEN deferred THEN 'hard_cap_reached' ELSE 'soft_ceiling_reached' END);
    END IF;
    INSERT INTO __OPS__.egress_log(occurred_at,destination,purpose,request_bytes,detail)
        VALUES(call_time,'api.cloudflare.com',p_kind,p_request_bytes,
               jsonb_build_object('state','reserved','model_id',p_model,'call_kind',p_kind))
        RETURNING egress_id INTO egress;
    INSERT INTO __CORE__.neuron_ledger(ledger_id,capture_id,model_id,call_kind,estimated_neurons,
            is_deferred_retry,called_at,outcome,egress_id)
        VALUES(p_request_id,p_capture_id,p_model,p_kind,p_estimated,deferred,call_time,'issued',egress)
        RETURNING ledger_id INTO ledger;
    INSERT INTO __CORE__.model_call_reservations(request_id,ledger_id,payload_sha256)
        VALUES(p_request_id,ledger,p_payload_sha256);
    RETURN jsonb_build_object('allowed',true,'duplicate',false,'request_id',p_request_id,
                             'spent',spent,'ceiling',ceiling,'reserved_at',call_time,
                             'valid_before',((call_time AT TIME ZONE 'UTC')::date + 1)::timestamp
                                             AT TIME ZONE 'UTC');
END $fn$;
REVOKE ALL ON FUNCTION public.reserve_model_call(uuid,text,text,numeric,uuid,integer,text)
    FROM PUBLIC, anon, authenticated, capture_ingest, service_role;
GRANT EXECUTE ON FUNCTION public.reserve_model_call(uuid,text,text,numeric,uuid,integer,text) TO model_egress;

CREATE FUNCTION public.settle_model_call(p_request_id uuid,p_outcome text,p_response_bytes integer)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE entry record;
BEGIN
    IF p_outcome IS NULL OR p_outcome NOT IN ('ok','error')
       OR p_response_bytes < 0 THEN
        RAISE EXCEPTION 'invalid model settlement' USING ERRCODE='22023';
    END IF;
    SELECT n.* INTO entry FROM __CORE__.model_call_reservations r
      JOIN __CORE__.neuron_ledger n USING (ledger_id)
     WHERE r.request_id=p_request_id FOR UPDATE OF n;
    IF NOT FOUND THEN RAISE EXCEPTION 'reservation unavailable' USING ERRCODE='22023'; END IF;
    IF entry.outcome <> 'issued' THEN
        IF entry.outcome <> p_outcome THEN
            RAISE EXCEPTION 'conflicting model settlement' USING ERRCODE='22023';
        END IF;
        RETURN;
    END IF;
    UPDATE __CORE__.neuron_ledger SET outcome=p_outcome WHERE ledger_id=entry.ledger_id;
    UPDATE __OPS__.egress_log SET response_bytes=p_response_bytes,
        detail=detail || jsonb_build_object('state',p_outcome) WHERE egress_id=entry.egress_id;
END $fn$;
REVOKE ALL ON FUNCTION public.settle_model_call(uuid,text,integer)
    FROM PUBLIC, anon, authenticated, capture_ingest, service_role;
GRANT EXECUTE ON FUNCTION public.settle_model_call(uuid,text,integer) TO model_egress;
