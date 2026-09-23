-- REQ-CAP-050/051: private immutable request bound to a saved transcription.
CREATE TABLE __CORE__.capture_extraction_attempts (
    request_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL REFERENCES __CORE__.raw_captures(capture_id),
    transcription_request_id uuid NOT NULL,
    expected_event_id bigint NOT NULL,
    model_id text NOT NULL CHECK (model_id='@cf/meta/llama-3.1-8b-instruct'),
    profile text NOT NULL CHECK (profile='food'),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object'),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
    estimated_neurons numeric NOT NULL CHECK (estimated_neurons > 0 AND estimated_neurons <= 10000),
    processor_version text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(capture_id,request_id),
    UNIQUE(capture_id,expected_event_id),
    FOREIGN KEY(capture_id,transcription_request_id)
        REFERENCES __CORE__.capture_transcription_attempts(capture_id,request_id),
    FOREIGN KEY(capture_id,expected_event_id)
        REFERENCES __CORE__.capture_processing_events(raw_capture_id,event_id)
);
ALTER TABLE __CORE__.capture_extraction_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_extraction_attempts
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_upload,capture_media_reader,service_role;
GRANT SELECT,INSERT ON __CORE__.capture_extraction_attempts TO service_role;
CREATE POLICY service_capture_extraction_attempts ON __CORE__.capture_extraction_attempts
    TO service_role USING(true) WITH CHECK(true);
CREATE TRIGGER capture_extraction_attempts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_extraction_attempts FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

ALTER TABLE __CORE__.capture_processing_events
    DROP CONSTRAINT capture_processing_events_processing_status_check;
ALTER TABLE __CORE__.capture_processing_events ADD CONSTRAINT capture_processing_events_processing_status_check
    CHECK (processing_status IN ('pending_enrichment','deferred_budget','transcribed',
                                'extracted','extraction_quarantined','enriched','failed'));
CREATE TABLE __CORE__.capture_extraction_outcomes (
    request_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL,
    event_id bigint NOT NULL UNIQUE,
    response_sha256 text CHECK (response_sha256 ~ '^[a-f0-9]{64}$'),
    failure_code text CHECK (failure_code IN ('invalid_extraction','prohibited_nutrition',
        'BudgetExceeded','DispatchRefused','DispatchUncertain','PayloadRefused','DispatcherUnavailable')
        OR failure_code ~ '^[345][0-9]{2}$'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(capture_id,request_id),
    CHECK (response_sha256 IS NOT NULL OR failure_code IS NOT NULL),
    FOREIGN KEY(capture_id,request_id) REFERENCES __CORE__.capture_extraction_attempts(capture_id,request_id),
    FOREIGN KEY(capture_id,event_id) REFERENCES __CORE__.capture_processing_events(raw_capture_id,event_id)
);
CREATE TABLE __CORE__.capture_extraction_fields (
    request_id uuid NOT NULL REFERENCES __CORE__.capture_extraction_outcomes(request_id),
    item_index integer NOT NULL CHECK (item_index >= -1),
    name text NOT NULL CHECK (name IN ('name','quantity','quantity_unit','temporal_evidence')),
    value jsonb,
    provenance text NOT NULL CHECK (provenance IN ('extracted','inferred','defaulted')),
    reason text NOT NULL,
    evidence text,
    evidence_start integer CHECK (evidence_start >= 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(request_id,item_index,name),
    CHECK ((item_index=-1) = (name='temporal_evidence')),
    CHECK (reason NOT IN ('span_mismatch','value_not_in_span') OR value IS NULL),
    CHECK (provenance <> 'extracted' OR (evidence IS NOT NULL AND evidence_start IS NOT NULL))
);
ALTER TABLE __CORE__.capture_extraction_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.capture_extraction_fields ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_extraction_outcomes,__CORE__.capture_extraction_fields
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_upload,capture_media_reader,service_role;
GRANT SELECT,INSERT ON __CORE__.capture_extraction_outcomes,__CORE__.capture_extraction_fields TO service_role;
CREATE POLICY service_extraction_outcomes ON __CORE__.capture_extraction_outcomes
    TO service_role USING(true) WITH CHECK(true);
CREATE POLICY service_extraction_fields ON __CORE__.capture_extraction_fields
    TO service_role USING(true) WITH CHECK(true);
CREATE TRIGGER extraction_outcomes_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_extraction_outcomes FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER extraction_fields_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_extraction_fields FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

ALTER TABLE __CORE__.capture_processing_reviews DROP CONSTRAINT capture_processing_reviews_reason_check;
ALTER TABLE __CORE__.capture_processing_reviews ADD CONSTRAINT capture_processing_reviews_reason_check
    CHECK (reason IN ('enrichment_stalled','empty_transcript','extraction_quarantined'));
CREATE FUNCTION public.review_quarantined_extraction(p_capture_id uuid,p_event_id bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='25000';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_capture_id::text,76));
    INSERT INTO __CORE__.capture_processing_reviews
        (raw_capture_id,pending_since,processing_event_id,reason)
    SELECT c.capture_id,e.recorded_at,c.event_id,'extraction_quarantined'
      FROM __CORE__.capture_processing_current c
      JOIN __CORE__.capture_processing_events e ON e.event_id=c.event_id
      JOIN __CORE__.capture_extraction_outcomes o ON o.event_id=c.event_id
     WHERE c.capture_id=p_capture_id AND c.event_id=p_event_id
       AND c.processing_status='extraction_quarantined' AND o.failure_code IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM __CORE__.capture_processing_review_dismissals d
                        WHERE d.raw_capture_id=c.capture_id)
    ON CONFLICT (raw_capture_id,pending_since) DO NOTHING;
END $fn$;
REVOKE ALL ON FUNCTION public.review_quarantined_extraction(uuid,bigint)
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_upload,capture_media_reader;
GRANT EXECUTE ON FUNCTION public.review_quarantined_extraction(uuid,bigint) TO service_role;

CREATE VIEW __CORE__.capture_extraction_current AS
SELECT DISTINCT ON (o.capture_id) o.capture_id,o.request_id,o.event_id,a.transcription_request_id,
    a.model_id,a.processor_version,o.recorded_at
FROM __CORE__.capture_extraction_outcomes o
JOIN __CORE__.capture_extraction_attempts a USING(request_id,capture_id)
JOIN __CORE__.capture_transcription_current t ON t.capture_id=o.capture_id
    AND t.request_id=a.transcription_request_id
JOIN __CORE__.capture_processing_events e ON e.event_id=o.event_id AND e.raw_capture_id=o.capture_id
WHERE e.applied AND o.failure_code IS NULL AND e.processing_status='extracted'
ORDER BY o.capture_id,o.event_id DESC;
REVOKE ALL ON __CORE__.capture_extraction_current
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_upload,capture_media_reader;
GRANT SELECT ON __CORE__.capture_extraction_current TO service_role;

-- Quarantine has no pending age; select its exact active event, respecting dismissal.
CREATE OR REPLACE FUNCTION public.get_capture_processing_reviews() RETURNS jsonb
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
        AND ((r.reason='extraction_quarantined' AND c.processing_status='extraction_quarantined'
              AND c.event_id=r.processing_event_id)
             OR (r.reason<>'extraction_quarantined' AND c.pending_since=r.pending_since))
     WHERE NOT EXISTS (SELECT 1 FROM __CORE__.capture_processing_review_dismissals d
                        WHERE d.raw_capture_id=r.raw_capture_id);
    RETURN result;
END $fn$;
REVOKE ALL ON FUNCTION public.get_capture_processing_reviews() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_capture_processing_reviews() TO authenticated;


-- Resolution preserves the item identity separately from verbatim evidence text.
CREATE TABLE __CORE__.capture_resolved_items (
    item_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL REFERENCES __CORE__.raw_captures(capture_id),
    extraction_request_id uuid NOT NULL,
    item_index integer NOT NULL CHECK(item_index >= 0),
    occurred_at timestamptz NOT NULL,
    subject_day date NOT NULL,
    time_precision __CORE__.time_precision NOT NULL,
    time_provenance __CORE__.provenance NOT NULL,
    time_reason text NOT NULL,
    resolution jsonb NOT NULL CHECK(jsonb_typeof(resolution)='object'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(extraction_request_id,item_index),
    UNIQUE(capture_id,item_id),
    FOREIGN KEY(capture_id,extraction_request_id)
        REFERENCES __CORE__.capture_extraction_outcomes(capture_id,request_id)
);
ALTER TABLE __CORE__.capture_resolved_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_resolved_items
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_upload,capture_media_reader,service_role;
GRANT SELECT,INSERT ON __CORE__.capture_resolved_items TO service_role;
CREATE POLICY service_capture_resolved_items ON __CORE__.capture_resolved_items
    TO service_role USING(true) WITH CHECK(true);
CREATE TRIGGER capture_resolved_items_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_resolved_items FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
ALTER TABLE __CORE__.atoms ADD COLUMN capture_item_id uuid REFERENCES __CORE__.capture_resolved_items(item_id);
ALTER TABLE __CORE__.atoms ADD COLUMN capture_component text NOT NULL DEFAULT 'total'
    CHECK(capture_component IN ('total','whole','fraction'));
ALTER TABLE __CORE__.atoms ADD CONSTRAINT atoms_capture_item_origin
    FOREIGN KEY(raw_capture_id,capture_item_id) REFERENCES __CORE__.capture_resolved_items(capture_id,item_id);
CREATE UNIQUE INDEX atoms_capture_item_metric_original ON __CORE__.atoms(capture_item_id,metric_key,capture_component)
    WHERE capture_item_id IS NOT NULL AND supersedes IS NULL;

CREATE TABLE __CORE__.capture_resolution_outcomes (
    request_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL REFERENCES __CORE__.raw_captures(capture_id),
    extraction_request_id uuid NOT NULL,
    expected_event_id bigint NOT NULL,
    event_id bigint NOT NULL UNIQUE,
    result jsonb NOT NULL CHECK(jsonb_typeof(result)='object'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(capture_id,extraction_request_id)
        REFERENCES __CORE__.capture_extraction_outcomes(capture_id,request_id),
    FOREIGN KEY(capture_id,event_id) REFERENCES __CORE__.capture_processing_events(raw_capture_id,event_id),
    FOREIGN KEY(capture_id,expected_event_id) REFERENCES __CORE__.capture_processing_events(raw_capture_id,event_id)
);
ALTER TABLE __CORE__.capture_resolution_outcomes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_resolution_outcomes
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_upload,capture_media_reader,service_role;
GRANT SELECT,INSERT ON __CORE__.capture_resolution_outcomes TO service_role;
CREATE POLICY service_capture_resolution_outcomes ON __CORE__.capture_resolution_outcomes
    TO service_role USING(true) WITH CHECK(true);
CREATE TRIGGER capture_resolution_outcomes_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_resolution_outcomes FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

-- Private resolution capabilities; no model-egress role obtains food/capture reads.
GRANT SELECT ON __CORE__.metric_registry TO service_role;
CREATE POLICY service_capture_metric_read ON __CORE__.metric_registry
    FOR SELECT TO service_role USING(true);
CREATE POLICY service_capture_atom_read ON __CORE__.atoms
    FOR SELECT TO service_role USING(capture_item_id IS NOT NULL);
CREATE POLICY service_capture_atom_insert ON __CORE__.atoms
    FOR INSERT TO service_role WITH CHECK(capture_item_id IS NOT NULL);
GRANT SELECT,INSERT ON __CORE__.foods_cache,__CORE__.food_aliases,__CORE__.unresolved_items TO service_role;
GRANT SELECT ON __CORE__.portions,__CORE__.portion_aliases TO service_role;
GRANT SELECT ON config.nutrition_interval_widths,config.strings,config.egress_allowlist TO service_role;
DO $role$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='reference_egress') THEN
        CREATE ROLE reference_egress NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $role$;
GRANT USAGE ON SCHEMA config,__OPS__ TO reference_egress;
GRANT SELECT ON config.egress_allowlist TO reference_egress;
GRANT SELECT,INSERT ON __OPS__.egress_log TO reference_egress;
GRANT UPDATE(response_bytes,detail) ON __OPS__.egress_log TO reference_egress;

-- Keep event-time provenance separate from inferred nutrient-value provenance.
ALTER TABLE __CORE__.atoms ADD COLUMN event_time_provenance __CORE__.provenance;
ALTER TABLE __CORE__.atoms ADD COLUMN quantity_provenance __CORE__.provenance;
CREATE FUNCTION __CORE__.stamp_capture_atom_time() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
BEGIN
    IF NEW.capture_item_id IS NULL THEN
        NEW.event_time_provenance := NULL;
        NEW.quantity_provenance := NULL;
    ELSE
        SELECT i.time_provenance,i.time_precision,i.occurred_at,i.subject_day
          INTO NEW.event_time_provenance,NEW.time_precision,NEW.occurred_at,NEW.subject_day
          FROM __CORE__.capture_resolved_items i
         WHERE i.item_id=NEW.capture_item_id AND i.capture_id=NEW.raw_capture_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'capture item origin required'; END IF;
        SELECT CASE WHEN NEW.capture_component='total' THEN i.resolution->>'quantity_provenance'
                    ELSE (SELECT c->>'quantity_provenance' FROM jsonb_array_elements(i.resolution->'components') c
                           WHERE c->>'component'=NEW.capture_component) END
            INTO NEW.quantity_provenance
            FROM __CORE__.capture_resolved_items i WHERE i.item_id=NEW.capture_item_id;
        IF NEW.quantity_provenance IS NULL THEN RAISE EXCEPTION 'capture quantity provenance required'; END IF;
    END IF;
    RETURN NEW;
END $fn$;
CREATE TRIGGER stamp_capture_atom_time BEFORE INSERT ON __CORE__.atoms
    FOR EACH ROW EXECUTE FUNCTION __CORE__.stamp_capture_atom_time();
CREATE OR REPLACE VIEW __CORE__.atoms_current AS
    SELECT a.* FROM __CORE__.atoms a
    WHERE NOT EXISTS (SELECT 1 FROM __CORE__.atoms s WHERE s.supersedes=a.id);

CREATE OR REPLACE FUNCTION analysis.f_atom_rows(p_as_of date, p_known_at timestamptz)
RETURNS TABLE (subject_day date, metric text, device text, value numeric,
               valid_interval tstzrange, atom_id uuid)
LANGUAGE sql STABLE AS $$
  SELECT a.subject_day, a.metric_key, analysis._atom_device(a.evidence_span),
         a.value_point, a.valid_interval, a.id
    FROM __CORE__.atoms a
   WHERE a.metric_key IS NOT NULL AND a.presence='observed'
     AND a.event_time_provenance IS DISTINCT FROM 'defaulted'
     AND a.quantity_provenance IS DISTINCT FROM 'defaulted' AND a.provenance<>'defaulted'
     AND a.subject_day<=p_as_of AND a.recorded_at<=p_known_at
     AND NOT EXISTS (SELECT 1 FROM __CORE__.atoms s
                      WHERE s.supersedes=a.id AND s.recorded_at<=p_known_at)
$$;

ALTER TABLE __CORE__.unresolved_items ADD COLUMN extraction_request_id uuid;
ALTER TABLE __CORE__.unresolved_items ADD COLUMN capture_item_index integer;
ALTER TABLE __CORE__.unresolved_items ADD CONSTRAINT unresolved_capture_item_identity
    CHECK ((extraction_request_id IS NULL AND capture_item_index IS NULL)
           OR (extraction_request_id IS NOT NULL AND capture_item_index IS NOT NULL
               AND capture_item_index>=0 AND raw_capture_id IS NOT NULL));
ALTER TABLE __CORE__.unresolved_items ADD CONSTRAINT unresolved_capture_extraction_origin
    FOREIGN KEY(raw_capture_id,extraction_request_id)
    REFERENCES __CORE__.capture_extraction_outcomes(capture_id,request_id);
CREATE UNIQUE INDEX unresolved_capture_item_open ON __CORE__.unresolved_items(extraction_request_id,capture_item_index)
    WHERE extraction_request_id IS NOT NULL AND resolved_at IS NULL;
GRANT UPDATE(resolved_at,resolved_by) ON __CORE__.unresolved_items TO service_role;
