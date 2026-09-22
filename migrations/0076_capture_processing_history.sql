-- ADR-0144 / REQ-CAP-025..027. Outcomes append; raw evidence never changes.
CREATE TABLE __CORE__.capture_processing_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_capture_id uuid NOT NULL REFERENCES __CORE__.raw_captures(capture_id),
    attempt_id uuid NOT NULL,
    expected_event_id bigint,
    processing_status text NOT NULL CHECK (processing_status IN
        ('pending_enrichment','deferred_budget','enriched','failed')),
    last_error text CHECK (last_error IS NULL OR last_error ~ '^[A-Za-z0-9_.:-]{1,120}$'),
    processor_version text NOT NULL CHECK (length(btrim(processor_version)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    applied boolean NOT NULL,
    UNIQUE (raw_capture_id, attempt_id),
    UNIQUE (raw_capture_id, event_id),
    FOREIGN KEY (raw_capture_id, expected_event_id)
        REFERENCES __CORE__.capture_processing_events(raw_capture_id, event_id),
    CHECK (processing_status NOT IN ('pending_enrichment','failed') OR last_error IS NOT NULL),
    CHECK (processing_status <> 'enriched' OR last_error IS NULL)
);
CREATE INDEX capture_processing_head_idx
    ON __CORE__.capture_processing_events(raw_capture_id, event_id DESC) WHERE applied;
ALTER TABLE __CORE__.capture_processing_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_processing_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON __CORE__.capture_processing_events TO service_role;
CREATE TRIGGER capture_processing_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.capture_processing_events
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE FUNCTION __CORE__.capture_processing_stamp() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $stamp$
BEGIN
    NEW.recorded_at := clock_timestamp();
    RETURN NEW;
END $stamp$;
CREATE TRIGGER capture_processing_recorded_at
    BEFORE INSERT ON __CORE__.capture_processing_events
    FOR EACH ROW EXECUTE FUNCTION __CORE__.capture_processing_stamp();

CREATE FUNCTION public.record_capture_processing(
    p_capture_id uuid, p_attempt_id uuid, p_expected_event_id bigint,
    p_status text, p_error text, p_processor_version text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE head_id bigint; previous __CORE__.capture_processing_events; outcome __CORE__.capture_processing_events;
BEGIN
    -- The head SELECT must see the commit that released the advisory lock.
    -- A repeatable snapshot can remain stale after waiting and admit two heads.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'capture processing requires READ COMMITTED isolation'
            USING ERRCODE='25000';
    END IF;
    -- Serializes outcomes for one capture; a hash collision only adds waiting.
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_capture_id::text, 76));
    SELECT * INTO previous FROM __CORE__.capture_processing_events
      WHERE raw_capture_id=p_capture_id AND attempt_id=p_attempt_id;
    IF FOUND THEN
        IF previous.expected_event_id IS DISTINCT FROM p_expected_event_id
            OR previous.processing_status IS DISTINCT FROM p_status
            OR previous.last_error IS DISTINCT FROM p_error
            OR previous.processor_version IS DISTINCT FROM p_processor_version THEN
            RAISE EXCEPTION 'attempt identity reused with different outcome' USING ERRCODE='22023';
        END IF;
        RETURN jsonb_build_object('event_id', previous.event_id, 'applied', previous.applied,
                                  'duplicate', true);
    END IF;
    SELECT max(event_id) INTO head_id FROM __CORE__.capture_processing_events
      WHERE raw_capture_id=p_capture_id AND applied;
    INSERT INTO __CORE__.capture_processing_events
        (raw_capture_id, attempt_id, expected_event_id, processing_status,
         last_error, processor_version, applied)
    VALUES (p_capture_id, p_attempt_id, p_expected_event_id, p_status,
            p_error, p_processor_version, head_id IS NOT DISTINCT FROM p_expected_event_id)
    RETURNING * INTO outcome;
    -- Stale outcomes are retained as evidence but cannot overwrite the current state.
    RETURN jsonb_build_object('event_id', outcome.event_id, 'applied', outcome.applied,
                              'duplicate', false);
END $fn$;
REVOKE ALL ON FUNCTION public.record_capture_processing(uuid,uuid,bigint,text,text,text)
    FROM PUBLIC, anon, authenticated, capture_ingest;
GRANT EXECUTE ON FUNCTION public.record_capture_processing(uuid,uuid,bigint,text,text,text)
    TO service_role;

CREATE VIEW __CORE__.capture_processing_current AS
SELECT r.capture_id, r.captured_at, r.source,
    coalesce(head.processing_status, r.processing_status) AS processing_status,
    CASE WHEN head.event_id IS NULL THEN r.last_error ELSE head.last_error END AS last_error,
    head.event_id, head.attempt_id, head.processor_version,
    coalesce(head.recorded_at, r.recorded_at) AS status_recorded_at,
    CASE WHEN coalesce(head.processing_status, r.processing_status)
          IN ('pending_enrichment','deferred_budget')
      THEN coalesce(
        CASE WHEN r.processing_status='pending_enrichment' AND reset.event_id IS NULL
          THEN r.recorded_at END,
        pending.since)
      ELSE NULL END AS pending_since
FROM __CORE__.raw_captures r
LEFT JOIN LATERAL (
    SELECT * FROM __CORE__.capture_processing_events e
    WHERE e.raw_capture_id=r.capture_id AND e.applied ORDER BY e.event_id DESC LIMIT 1
) head ON true
LEFT JOIN LATERAL (
    SELECT max(e.event_id) AS event_id FROM __CORE__.capture_processing_events e
    WHERE e.raw_capture_id=r.capture_id AND e.applied
      AND e.processing_status IN ('enriched','failed')
) reset ON true
LEFT JOIN LATERAL (
    SELECT min(e.recorded_at) AS since FROM __CORE__.capture_processing_events e
    WHERE e.raw_capture_id=r.capture_id AND e.applied
      AND e.processing_status='pending_enrichment'
      AND (reset.event_id IS NULL OR e.event_id > reset.event_id)
) pending ON true;
REVOKE ALL ON __CORE__.capture_processing_current FROM PUBLIC, anon, authenticated, capture_ingest;
GRANT SELECT ON __CORE__.capture_processing_current TO service_role;

-- A review is a persisted queue entry, not a delivered prompt. One per unresolved
-- episode; dismissal is permanent for the capture, including later episodes.
CREATE TABLE __CORE__.capture_processing_reviews (
    review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_capture_id uuid NOT NULL REFERENCES __CORE__.raw_captures(capture_id),
    pending_since timestamptz NOT NULL,
    processing_event_id bigint,
    reason text NOT NULL DEFAULT 'enrichment_stalled' CHECK (reason='enrichment_stalled'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(raw_capture_id, pending_since),
    FOREIGN KEY(raw_capture_id, processing_event_id)
        REFERENCES __CORE__.capture_processing_events(raw_capture_id, event_id)
);
CREATE TABLE __CORE__.capture_processing_review_dismissals (
    raw_capture_id uuid PRIMARY KEY REFERENCES __CORE__.raw_captures(capture_id),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE __CORE__.capture_processing_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.capture_processing_review_dismissals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_processing_reviews,
    __CORE__.capture_processing_review_dismissals FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON __CORE__.capture_processing_reviews,
    __CORE__.capture_processing_review_dismissals TO service_role;
CREATE TRIGGER capture_reviews_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.capture_processing_reviews
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER capture_review_dismissals_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.capture_processing_review_dismissals
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

CREATE FUNCTION public.enqueue_stalled_capture_reviews(p_now timestamptz)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE cid uuid; inserted integer; total integer := 0;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'capture review requires READ COMMITTED isolation' USING ERRCODE='25000';
    END IF;
    IF p_now IS NULL THEN
        RAISE EXCEPTION 'review clock is required' USING ERRCODE='22004';
    END IF;
    FOR cid IN SELECT capture_id FROM __CORE__.capture_processing_current
        WHERE p_now - pending_since > interval '72 hours' ORDER BY capture_id
    LOOP
        PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(cid::text,76));
        -- Re-read after the lock: another transaction may have completed/dismissed it.
        INSERT INTO __CORE__.capture_processing_reviews
            (raw_capture_id, pending_since, processing_event_id)
        SELECT c.capture_id, c.pending_since, c.event_id
          FROM __CORE__.capture_processing_current c
         WHERE c.capture_id=cid AND p_now - c.pending_since > interval '72 hours'
           AND NOT EXISTS (SELECT 1 FROM __CORE__.capture_processing_review_dismissals d
                            WHERE d.raw_capture_id=cid)
        ON CONFLICT (raw_capture_id,pending_since) DO NOTHING;
        GET DIAGNOSTICS inserted = ROW_COUNT;
        total := total + inserted;
    END LOOP;
    RETURN total;
END $fn$;
REVOKE ALL ON FUNCTION public.enqueue_stalled_capture_reviews(timestamptz)
    FROM PUBLIC, anon, authenticated, capture_ingest;
GRANT EXECUTE ON FUNCTION public.enqueue_stalled_capture_reviews(timestamptz) TO service_role;

CREATE FUNCTION public.get_capture_processing_reviews() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $fn$
DECLARE result jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'review_id',r.review_id,'capture_id',r.raw_capture_id,'reason',r.reason,
        'pending_since',r.pending_since,'recorded_at',r.recorded_at,
        'captured_at',c.captured_at,'source',c.source,'processing_status',c.processing_status,
        'last_error',c.last_error,'processing_event_id',c.event_id)
        ORDER BY r.pending_since,r.raw_capture_id),'[]'::jsonb)
      INTO result FROM __CORE__.capture_processing_reviews r
      JOIN __CORE__.capture_processing_current c ON c.capture_id=r.raw_capture_id
        AND c.pending_since=r.pending_since
     WHERE NOT EXISTS (SELECT 1 FROM __CORE__.capture_processing_review_dismissals d
                        WHERE d.raw_capture_id=r.raw_capture_id);
    RETURN result;
END $fn$;
REVOKE ALL ON FUNCTION public.get_capture_processing_reviews() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_capture_processing_reviews() TO authenticated;

CREATE FUNCTION public.dismiss_capture_processing_review(p_capture_id uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_capture_id::text,76));
    INSERT INTO __CORE__.capture_processing_review_dismissals(raw_capture_id)
        SELECT p_capture_id WHERE EXISTS (SELECT 1 FROM __CORE__.capture_processing_reviews
                                          WHERE raw_capture_id=p_capture_id)
    ON CONFLICT (raw_capture_id) DO NOTHING;
    RETURN EXISTS (SELECT 1 FROM __CORE__.capture_processing_review_dismissals
                    WHERE raw_capture_id=p_capture_id);
END $fn$;
REVOKE ALL ON FUNCTION public.dismiss_capture_processing_review(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dismiss_capture_processing_review(uuid) TO authenticated;

-- Queue write, counts and heartbeat share one bound schema. No caller-selected
-- schema knobs can point the receipt at a different database component.
CREATE FUNCTION public.maintain_capture_processing(p_now timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE added integer; counts jsonb; summary jsonb;
BEGIN
    added := public.enqueue_stalled_capture_reviews(p_now);
    SELECT coalesce(jsonb_object_agg(processing_status,n),'{}'::jsonb) INTO counts
      FROM (SELECT processing_status,count(*) AS n FROM __CORE__.capture_processing_current
             GROUP BY processing_status) grouped;
    summary := jsonb_build_object('code_version','capture-processing-v1',
        'reviews_added',added,'capture_counts',counts,'enrichment_attempts',0,
        'scope','review_maintenance_only');
    INSERT INTO __OPS__.runs(job_name,finished_at,status,rows_written,detail)
        VALUES ('capture_processing_maintenance',clock_timestamp(),'ok',added,summary);
    RETURN summary;
END $fn$;
REVOKE ALL ON FUNCTION public.maintain_capture_processing(timestamptz)
    FROM PUBLIC, anon, authenticated, capture_ingest;
GRANT EXECUTE ON FUNCTION public.maintain_capture_processing(timestamptz) TO service_role;

CREATE FUNCTION public.fail_capture_processing_maintenance(p_error_type text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
BEGIN
    IF p_error_type IS NULL OR p_error_type !~ '^[A-Za-z_][A-Za-z0-9_]{0,99}$' THEN
        RAISE EXCEPTION 'error class required' USING ERRCODE='22023';
    END IF;
    INSERT INTO __OPS__.runs(job_name,finished_at,status,rows_written,detail)
        VALUES ('capture_processing_maintenance',clock_timestamp(),'error',0,
          jsonb_build_object('code_version','capture-processing-v1','error_type',p_error_type));
END $fn$;
REVOKE ALL ON FUNCTION public.fail_capture_processing_maintenance(text)
    FROM PUBLIC, anon, authenticated, capture_ingest;
GRANT EXECUTE ON FUNCTION public.fail_capture_processing_maintenance(text) TO service_role;
