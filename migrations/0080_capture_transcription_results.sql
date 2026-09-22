-- ADR0148: immutable transcript evidence and correlated processing attempts.
ALTER TABLE __CORE__.capture_processing_events
    DROP CONSTRAINT capture_processing_events_processing_status_check;
ALTER TABLE __CORE__.capture_processing_events ADD CONSTRAINT capture_processing_events_processing_status_check
    CHECK (processing_status IN ('pending_enrichment','deferred_budget','transcribed','enriched','failed'));

CREATE TABLE __CORE__.capture_transcription_attempts (
    request_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL REFERENCES __CORE__.raw_captures(capture_id),
    expected_event_id bigint,
    model_id text NOT NULL CHECK (model_id='@cf/openai/whisper-large-v3-turbo'),
    call_kind text NOT NULL CHECK (call_kind='transcribe'),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
    duration_seconds numeric NOT NULL CHECK (duration_seconds > 0 AND duration_seconds < 'Infinity'::numeric),
    estimated_neurons numeric NOT NULL CHECK (estimated_neurons > 0 AND estimated_neurons <= 10000),
    processor_version text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(capture_id,request_id),
    FOREIGN KEY(capture_id,expected_event_id)
        REFERENCES __CORE__.capture_processing_events(raw_capture_id,event_id)
);
CREATE TABLE __CORE__.capture_transcription_outcomes (
    request_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL,
    event_id bigint NOT NULL UNIQUE,
    response_sha256 text CHECK (response_sha256 ~ '^[a-f0-9]{64}$'),
    transcript text,
    segments jsonb,
    failure_code text,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(capture_id,request_id) REFERENCES __CORE__.capture_transcription_attempts(capture_id,request_id),
    FOREIGN KEY(capture_id,event_id) REFERENCES __CORE__.capture_processing_events(raw_capture_id,event_id),
    CHECK ((transcript IS NULL AND segments IS NULL) OR
           (transcript IS NOT NULL AND segments IS NOT NULL AND jsonb_typeof(segments)='array')),
    CHECK (transcript IS NULL OR response_sha256 IS NOT NULL),
    CHECK (failure_code IS NOT NULL OR transcript IS NOT NULL)
);
ALTER TABLE __CORE__.capture_transcription_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.capture_transcription_outcomes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_transcription_attempts,__CORE__.capture_transcription_outcomes
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,service_role;
GRANT SELECT,INSERT ON __CORE__.capture_transcription_attempts,__CORE__.capture_transcription_outcomes TO service_role;
CREATE POLICY service_transcription_attempts ON __CORE__.capture_transcription_attempts
    TO service_role USING(true) WITH CHECK(true);
CREATE POLICY service_transcription_outcomes ON __CORE__.capture_transcription_outcomes
    TO service_role USING(true) WITH CHECK(true);
CREATE TRIGGER transcription_attempts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_transcription_attempts FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER transcription_outcomes_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_transcription_outcomes FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

-- An extraction failure must not discard its usable transcript. Stale or invalid
-- transcription results never become current, even if received later.
CREATE VIEW __CORE__.capture_transcription_current AS
SELECT DISTINCT ON (o.capture_id) o.capture_id,o.request_id,o.event_id,o.transcript,o.segments,
    a.model_id,a.processor_version,o.recorded_at
FROM __CORE__.capture_transcription_outcomes o
JOIN __CORE__.capture_transcription_attempts a USING(request_id,capture_id)
JOIN __CORE__.capture_processing_events e ON e.event_id=o.event_id AND e.raw_capture_id=o.capture_id
WHERE e.applied AND o.failure_code IS NULL AND e.processing_status='transcribed'
ORDER BY o.capture_id,o.event_id DESC;
REVOKE ALL ON __CORE__.capture_transcription_current FROM PUBLIC,anon,authenticated,capture_ingest,model_egress;
GRANT SELECT ON __CORE__.capture_transcription_current TO service_role;

-- Private voice preparation needs the original duration/media reference.
CREATE POLICY service_voice_capture_read ON __CORE__.raw_captures
    FOR SELECT TO service_role USING (source='shortcut_voice');

-- REQ-CAP-045 is immediate; it must not wait for the 72-hour maintenance path.
ALTER TABLE __CORE__.capture_processing_reviews DROP CONSTRAINT capture_processing_reviews_reason_check;
ALTER TABLE __CORE__.capture_processing_reviews ADD CONSTRAINT capture_processing_reviews_reason_check
    CHECK (reason IN ('enrichment_stalled','empty_transcript'));
CREATE FUNCTION public.review_empty_transcript(p_capture_id uuid,p_event_id bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='25000';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_capture_id::text,76));
    INSERT INTO __CORE__.capture_processing_reviews
        (raw_capture_id,pending_since,processing_event_id,reason)
    SELECT c.capture_id,c.pending_since,c.event_id,'empty_transcript'
      FROM __CORE__.capture_processing_current c
      JOIN __CORE__.capture_transcription_outcomes o ON o.event_id=c.event_id
     WHERE c.capture_id=p_capture_id AND c.event_id=p_event_id
       AND c.processing_status='pending_enrichment' AND c.last_error='empty_transcript'
       AND o.failure_code='empty_transcript'
       AND NOT EXISTS (SELECT 1 FROM __CORE__.capture_processing_review_dismissals d
                        WHERE d.raw_capture_id=c.capture_id)
    ON CONFLICT (raw_capture_id,pending_since) DO NOTHING;
END $fn$;
REVOKE ALL ON FUNCTION public.review_empty_transcript(uuid,bigint)
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress;
GRANT EXECUTE ON FUNCTION public.review_empty_transcript(uuid,bigint) TO service_role;

-- Keep only bounded HTTP status metadata, never provider response/error bodies.
CREATE TABLE __CORE__.model_http_failures (
    request_id uuid PRIMARY KEY REFERENCES __CORE__.model_call_results(request_id),
    http_status integer NOT NULL CHECK (http_status BETWEEN 300 AND 599),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE __CORE__.model_http_failures ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.model_http_failures FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,service_role;
GRANT SELECT ON __CORE__.model_http_failures TO service_role;
CREATE POLICY service_model_http_failures ON __CORE__.model_http_failures FOR SELECT TO service_role USING(true);
CREATE TRIGGER model_http_failures_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.model_http_failures FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE FUNCTION public.record_model_http_failure(p_request_id uuid,p_http_status integer)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE prior integer;
BEGIN
    -- Settlement already owns the ledger lock in the dispatch transaction.
    PERFORM 1 FROM __CORE__.model_call_reservations r
      JOIN __CORE__.neuron_ledger n USING(ledger_id)
      JOIN __CORE__.model_call_results s USING(request_id)
     WHERE r.request_id=p_request_id AND n.outcome='error' AND s.response_sha256 IS NULL
     FOR UPDATE OF n;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'settled failed request required' USING ERRCODE='22023';
    END IF;
    INSERT INTO __CORE__.model_http_failures(request_id,http_status)
        VALUES (p_request_id,p_http_status) ON CONFLICT(request_id) DO NOTHING;
    SELECT http_status INTO prior FROM __CORE__.model_http_failures WHERE request_id=p_request_id;
    IF prior IS DISTINCT FROM p_http_status THEN
        RAISE EXCEPTION 'failure identity reused' USING ERRCODE='22023';
    END IF;
END $fn$;
REVOKE ALL ON FUNCTION public.record_model_http_failure(uuid,integer)
    FROM PUBLIC,anon,authenticated,service_role,capture_ingest;
GRANT EXECUTE ON FUNCTION public.record_model_http_failure(uuid,integer) TO model_egress;
