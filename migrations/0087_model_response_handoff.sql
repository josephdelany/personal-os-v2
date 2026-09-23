-- Durable model-to-private handoff; stdout is delivery, not the only copy.
CREATE TABLE __OPS__.model_response_bodies (
    request_id uuid PRIMARY KEY REFERENCES __CORE__.model_call_results(request_id),
    response_body text NOT NULL CHECK(octet_length(response_body) BETWEEN 1 AND 2097152),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER model_response_bodies_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __OPS__.model_response_bodies FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
REVOKE ALL ON __OPS__.model_response_bodies
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,reference_egress,service_role;
GRANT SELECT ON __OPS__.model_response_bodies TO service_role;

CREATE FUNCTION public.settle_model_response(p_request_id uuid,p_outcome text,p_body text,p_status integer DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_sha text; v_old text;
BEGIN
    IF p_outcome IS NULL OR p_outcome NOT IN ('ok','error')
       OR (p_outcome='ok' AND (p_body IS NULL OR octet_length(p_body) NOT BETWEEN 1 AND 2097152))
       OR (p_outcome='error' AND p_body IS NOT NULL)
       OR (p_status IS NOT NULL AND (p_outcome<>'error' OR p_status NOT BETWEEN 300 AND 599)) THEN
        RAISE EXCEPTION 'invalid model response settlement';
    END IF;
    IF p_outcome='ok' THEN
        PERFORM p_body::jsonb;
        v_sha := encode(sha256(convert_to(p_body,'UTF8')),'hex');
    END IF;
    PERFORM public.settle_model_call(p_request_id,p_outcome,octet_length(p_body),v_sha);
    IF p_status IS NOT NULL THEN
        PERFORM public.record_model_http_failure(p_request_id,p_status);
    END IF;
    IF p_outcome='ok' THEN
        SELECT response_body INTO v_old FROM __OPS__.model_response_bodies WHERE request_id=p_request_id;
        IF FOUND THEN
            IF v_old IS DISTINCT FROM p_body THEN RAISE EXCEPTION 'model response identity reused'; END IF;
        ELSE
            INSERT INTO __OPS__.model_response_bodies(request_id,response_body) VALUES(p_request_id,p_body);
        END IF;
    END IF;
END $$;
REVOKE ALL ON FUNCTION public.settle_model_response(uuid,text,text,integer)
    FROM PUBLIC,anon,authenticated,service_role,capture_ingest,reference_egress;
GRANT EXECUTE ON FUNCTION public.settle_model_response(uuid,text,text,integer) TO model_egress;
REVOKE EXECUTE ON FUNCTION public.settle_model_call(uuid,text,integer,text) FROM model_egress;
REVOKE EXECUTE ON FUNCTION public.record_model_http_failure(uuid,integer) FROM model_egress;

-- Only the isolated model supervisor may call this, after observing its child's
-- newly committed reservation AND terminating/reaping that exact child. Neither
-- a private poller nor an elapsed deadline alone supplies that ownership proof.
CREATE FUNCTION public.reconcile_stopped_model_call(p_request_id uuid)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_outcome text;
BEGIN
    SELECT n.outcome INTO v_outcome FROM __CORE__.model_call_reservations r
        JOIN __CORE__.neuron_ledger n USING(ledger_id)
        WHERE r.request_id=p_request_id FOR UPDATE OF n;
    IF NOT FOUND THEN RAISE EXCEPTION 'model reservation required'; END IF;
    IF v_outcome='issued' THEN
        PERFORM public.settle_model_response(p_request_id,'error',NULL,NULL);
        RETURN 'error';
    END IF;
    RETURN v_outcome;
END $$;
REVOKE ALL ON FUNCTION public.reconcile_stopped_model_call(uuid)
    FROM PUBLIC,anon,authenticated,service_role,capture_ingest,reference_egress;
GRANT EXECUTE ON FUNCTION public.reconcile_stopped_model_call(uuid) TO model_egress;
