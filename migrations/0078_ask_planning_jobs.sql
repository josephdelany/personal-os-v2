-- ADR0147: private preparation/consumption persists across an isolated model call.
CREATE TABLE __CORE__.ask_planning_jobs (
    job_id uuid PRIMARY KEY,
    question text NOT NULL CHECK (length(question)>0),
    as_of date NOT NULL,
    known_at timestamptz NOT NULL,
    operations jsonb NOT NULL,
    metrics jsonb NOT NULL,
    fallback jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE __CORE__.ask_planning_attempts (
    request_id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES __CORE__.ask_planning_jobs(job_id),
    attempt_no integer NOT NULL CHECK (attempt_no BETWEEN 1 AND 5),
    model_id text NOT NULL,
    call_kind text NOT NULL CHECK (call_kind='plan'),
    estimated_neurons numeric NOT NULL CHECK (estimated_neurons > 0 AND estimated_neurons <= 9000),
    payload jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(job_id,attempt_no)
);
CREATE TABLE __CORE__.ask_planning_outcomes (
    request_id uuid PRIMARY KEY REFERENCES __CORE__.ask_planning_attempts(request_id),
    response_sha256 text NOT NULL CHECK (response_sha256 ~ '^[a-f0-9]{64}$'),
    result jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE __CORE__.ask_planning_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.ask_planning_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.ask_planning_outcomes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.ask_planning_jobs, __CORE__.ask_planning_attempts,
    __CORE__.ask_planning_outcomes FROM PUBLIC, anon, authenticated, model_egress, capture_ingest;
GRANT SELECT,INSERT ON __CORE__.ask_planning_jobs, __CORE__.ask_planning_attempts,
    __CORE__.ask_planning_outcomes TO service_role;
CREATE TRIGGER ask_planning_jobs_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.ask_planning_jobs FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER ask_planning_attempts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.ask_planning_attempts FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER ask_planning_outcomes_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.ask_planning_outcomes FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

-- The provider's response must be bound BEFORE a private consumer accepts it.
CREATE TABLE __CORE__.model_call_results (
    request_id uuid PRIMARY KEY REFERENCES __CORE__.model_call_reservations(request_id),
    response_sha256 text CHECK (response_sha256 ~ '^[a-f0-9]{64}$'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE __CORE__.model_call_results ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.model_call_results FROM PUBLIC,anon,authenticated,model_egress,capture_ingest;
GRANT SELECT ON __CORE__.model_call_results, __CORE__.model_call_reservations,
    __CORE__.neuron_ledger TO service_role;
CREATE POLICY service_model_results ON __CORE__.model_call_results FOR SELECT TO service_role USING(true);
CREATE POLICY service_model_reservations ON __CORE__.model_call_reservations FOR SELECT TO service_role USING(true);
CREATE POLICY service_ask_jobs ON __CORE__.ask_planning_jobs TO service_role USING(true) WITH CHECK(true);
CREATE POLICY service_ask_attempts ON __CORE__.ask_planning_attempts TO service_role USING(true) WITH CHECK(true);
CREATE POLICY service_ask_outcomes ON __CORE__.ask_planning_outcomes TO service_role USING(true) WITH CHECK(true);
CREATE TRIGGER model_call_results_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.model_call_results FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

CREATE FUNCTION public.settle_model_call(p_request_id uuid,p_outcome text,p_response_bytes integer,
                                        p_response_sha256 text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE previous text;
BEGIN
    IF (p_outcome='ok' AND (p_response_sha256 IS NULL OR p_response_sha256 !~ '^[a-f0-9]{64}$'))
       OR (p_outcome='error' AND p_response_sha256 IS NOT NULL) THEN
        RAISE EXCEPTION 'response digest required for successful settlement' USING ERRCODE='22023';
    END IF;
    -- Existing settlement owns the row lock; digest insert/verification is atomic with it.
    PERFORM public.settle_model_call(p_request_id,p_outcome,p_response_bytes);
    SELECT response_sha256 INTO previous FROM __CORE__.model_call_results WHERE request_id=p_request_id;
    IF FOUND THEN
        IF previous IS DISTINCT FROM p_response_sha256 THEN
            RAISE EXCEPTION 'conflicting response digest' USING ERRCODE='22023';
        END IF;
    ELSE
        INSERT INTO __CORE__.model_call_results(request_id,response_sha256)
            VALUES(p_request_id,p_response_sha256);
    END IF;
END $fn$;
REVOKE ALL ON FUNCTION public.settle_model_call(uuid,text,integer) FROM model_egress;
REVOKE ALL ON FUNCTION public.settle_model_call(uuid,text,integer,text)
    FROM PUBLIC,anon,authenticated,service_role,capture_ingest;
GRANT EXECUTE ON FUNCTION public.settle_model_call(uuid,text,integer,text) TO model_egress;

-- Trusted private worker can call the owner-checked executor; model role cannot.
GRANT EXECUTE ON FUNCTION public.ask(text,date,timestamptz) TO service_role;
GRANT USAGE ON SCHEMA config TO service_role;
GRANT SELECT ON config.operations, __CORE__.metric_registry TO service_role;
