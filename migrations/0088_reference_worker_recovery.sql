-- The reference-only supervisor calls this after its acknowledged child has
-- terminated. Keep private capture access outside the outbound process.
CREATE FUNCTION public.reconcile_stopped_reference_call(p_request_id uuid)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_outcome text;
BEGIN
    PERFORM public.reconcile_reference_call(p_request_id);
    SELECT outcome INTO v_outcome FROM __OPS__.reference_results WHERE request_id=p_request_id;
    RETURN v_outcome;
END $$;
REVOKE ALL ON FUNCTION public.reconcile_stopped_reference_call(uuid)
    FROM PUBLIC,anon,authenticated,service_role,capture_ingest,model_egress;
GRANT EXECUTE ON FUNCTION public.reconcile_stopped_reference_call(uuid) TO reference_egress;
