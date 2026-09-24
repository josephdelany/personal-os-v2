-- REQ-CAP-014 / RULE-02/03/10; ADR-0161. Private owner authority is
-- separate from actor metadata and automated service capabilities.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='capture_owner') THEN
        CREATE ROLE capture_owner NOLOGIN;
    END IF;
END $$;

CREATE TABLE __CORE__.capture_owner_corrections (
    request_id uuid PRIMARY KEY,
    capture_id uuid NOT NULL,
    expected_item_id uuid NOT NULL,
    actor text NOT NULL CHECK(actor='joe'),
    operation text NOT NULL CHECK(operation IN ('replace','remove')),
    food_id uuid REFERENCES __CORE__.foods_cache(food_id),
    quantity_kind text CHECK(quantity_kind IN ('grams','servings','item_count')),
    quantity numeric CHECK(quantity>0 AND quantity<'Infinity'::numeric),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(capture_id,expected_item_id)
        REFERENCES __CORE__.capture_resolved_items(capture_id,item_id),
    CHECK (
        (operation='replace' AND food_id IS NOT NULL
            AND quantity_kind IS NOT NULL AND quantity IS NOT NULL)
        OR (operation='remove' AND food_id IS NULL
            AND quantity_kind IS NULL AND quantity IS NULL)
    )
);
ALTER TABLE __CORE__.capture_owner_corrections ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_owner_corrections FROM PUBLIC,anon,authenticated,
    service_role,model_egress,reference_egress,capture_ingest;
GRANT USAGE ON SCHEMA __CORE__ TO capture_owner;
GRANT SELECT ON __CORE__.metric_registry TO capture_owner;
CREATE POLICY owner_capture_metric_read ON __CORE__.metric_registry
    FOR SELECT TO capture_owner USING(true);
GRANT SELECT ON __CORE__.raw_captures,__CORE__.foods_cache,__CORE__.portions,
    __CORE__.capture_extraction_current TO capture_owner;
CREATE POLICY owner_capture_raw_read ON __CORE__.raw_captures
    FOR SELECT TO capture_owner USING(true);
CREATE POLICY owner_capture_food_read ON __CORE__.foods_cache
    FOR SELECT TO capture_owner USING(true);
CREATE POLICY owner_capture_portion_read ON __CORE__.portions
    FOR SELECT TO capture_owner USING(true);
GRANT USAGE ON SCHEMA config TO capture_owner;
GRANT SELECT ON config.nutrition_interval_widths TO capture_owner;
GRANT SELECT,INSERT ON __CORE__.capture_owner_corrections TO capture_owner;
GRANT SELECT ON __CORE__.capture_owner_corrections TO service_role;
CREATE POLICY owner_capture_corrections ON __CORE__.capture_owner_corrections
    TO capture_owner USING(true) WITH CHECK(true);
CREATE POLICY service_read_capture_corrections ON __CORE__.capture_owner_corrections
    FOR SELECT TO service_role USING(true);
CREATE TRIGGER capture_owner_corrections_immutable
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.capture_owner_corrections
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER capture_owner_corrections_recorded_at
    BEFORE INSERT ON __CORE__.capture_owner_corrections
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

-- One original item per extracted position; later versions form a single chain.
ALTER TABLE __CORE__.capture_resolved_items
    DROP CONSTRAINT capture_resolved_items_extraction_request_id_item_index_key;
ALTER TABLE __CORE__.capture_resolved_items
    ADD COLUMN supersedes_item_id uuid UNIQUE REFERENCES __CORE__.capture_resolved_items(item_id),
    ADD COLUMN correction_request_id uuid UNIQUE REFERENCES __CORE__.capture_owner_corrections(request_id),
    ADD CONSTRAINT capture_item_correction_pair CHECK
        ((supersedes_item_id IS NULL) = (correction_request_id IS NULL));
CREATE UNIQUE INDEX capture_item_original_position
    ON __CORE__.capture_resolved_items(extraction_request_id,item_index)
    WHERE supersedes_item_id IS NULL;
GRANT SELECT,INSERT ON __CORE__.capture_resolved_items TO capture_owner;
CREATE POLICY owner_capture_resolved_items ON __CORE__.capture_resolved_items
    TO capture_owner USING(true) WITH CHECK(correction_request_id IS NOT NULL);

CREATE FUNCTION __CORE__.validate_capture_item_correction() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE prior __CORE__.capture_resolved_items; request __CORE__.capture_owner_corrections;
BEGIN
    IF NEW.correction_request_id IS NULL THEN RETURN NEW; END IF;
    IF NOT pg_has_role(current_user,'capture_owner','USAGE') THEN
        RAISE EXCEPTION 'private owner capability required' USING ERRCODE='42501';
    END IF;
    SELECT * INTO request FROM __CORE__.capture_owner_corrections
        WHERE request_id=NEW.correction_request_id;
    IF NOT FOUND OR request.capture_id<>NEW.capture_id
        OR request.expected_item_id IS DISTINCT FROM NEW.supersedes_item_id THEN
        RAISE EXCEPTION 'correction request does not identify predecessor';
    END IF;
    SELECT * INTO prior FROM __CORE__.capture_resolved_items WHERE item_id=NEW.supersedes_item_id;
    IF NOT FOUND OR ROW(prior.capture_id,prior.extraction_request_id,prior.item_index,
        prior.occurred_at,prior.subject_day,prior.time_precision,prior.time_provenance,prior.time_reason)
        IS DISTINCT FROM ROW(NEW.capture_id,NEW.extraction_request_id,NEW.item_index,
        NEW.occurred_at,NEW.subject_day,NEW.time_precision,NEW.time_provenance,NEW.time_reason) THEN
        RAISE EXCEPTION 'correction must preserve capture, extracted position and event time';
    END IF;
    -- The UNIQUE predecessor constraint also rejects concurrent forks.
    IF EXISTS(SELECT 1 FROM __CORE__.capture_resolved_items
              WHERE supersedes_item_id=NEW.supersedes_item_id) THEN
        RAISE EXCEPTION 'stale correction predecessor';
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION __CORE__.validate_capture_item_correction() FROM PUBLIC;
CREATE TRIGGER validate_capture_item_correction BEFORE INSERT ON __CORE__.capture_resolved_items
    FOR EACH ROW EXECUTE FUNCTION __CORE__.validate_capture_item_correction();
CREATE TRIGGER capture_item_recorded_at BEFORE INSERT ON __CORE__.capture_resolved_items
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();
CREATE VIEW __CORE__.capture_resolved_items_current WITH(security_invoker=true) AS
    SELECT i.* FROM __CORE__.capture_resolved_items i
    WHERE NOT EXISTS(SELECT 1 FROM __CORE__.capture_resolved_items s WHERE s.supersedes_item_id=i.item_id);
REVOKE ALL ON __CORE__.capture_resolved_items_current FROM PUBLIC,anon,authenticated;
GRANT SELECT ON __CORE__.capture_resolved_items_current TO service_role,capture_owner;

ALTER TABLE __CORE__.atoms
    ADD COLUMN correction_request_id uuid REFERENCES __CORE__.capture_owner_corrections(request_id),
    ADD COLUMN is_retraction boolean NOT NULL DEFAULT false,
    ADD CONSTRAINT capture_retraction_shape CHECK (NOT is_retraction OR
        (correction_request_id IS NOT NULL AND capture_item_id IS NOT NULL
         AND supersedes IS NOT NULL AND presence='unknown'
         AND value_low IS NULL AND value_point IS NULL AND value_high IS NULL
         AND valid_interval IS NULL));
CREATE UNIQUE INDEX capture_atom_single_successor ON __CORE__.atoms(supersedes)
    WHERE capture_item_id IS NOT NULL AND supersedes IS NOT NULL;
GRANT SELECT,INSERT ON __CORE__.atoms TO capture_owner;
CREATE POLICY owner_capture_atoms ON __CORE__.atoms TO capture_owner
    USING(capture_item_id IS NOT NULL) WITH CHECK(capture_item_id IS NOT NULL AND correction_request_id IS NOT NULL);

CREATE FUNCTION __CORE__.validate_capture_atom_correction() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE prior __CORE__.atoms; item __CORE__.capture_resolved_items;
        request __CORE__.capture_owner_corrections;
BEGIN
    IF NEW.capture_item_id IS NOT NULL THEN
        SELECT * INTO item FROM __CORE__.capture_resolved_items WHERE item_id=NEW.capture_item_id;
    END IF;
    IF NEW.correction_request_id IS NULL THEN
        IF item.correction_request_id IS NOT NULL THEN
            RAISE EXCEPTION 'corrected item requires correction authority';
        END IF;
        IF NEW.capture_item_id IS NOT NULL AND EXISTS(
            SELECT 1 FROM __CORE__.capture_resolved_items
            WHERE supersedes_item_id=NEW.capture_item_id) THEN
            RAISE EXCEPTION 'superseded item cannot receive automatic atoms';
        END IF;
        IF NEW.supersedes IS NOT NULL AND EXISTS(SELECT 1 FROM __CORE__.atoms
            WHERE id=NEW.supersedes AND capture_item_id IS NOT NULL) THEN
            RAISE EXCEPTION 'capture atom supersession requires correction authority';
        END IF;
        RETURN NEW;
    END IF;
    IF NOT pg_has_role(current_user,'capture_owner','USAGE') THEN
        RAISE EXCEPTION 'private owner capability required' USING ERRCODE='42501';
    END IF;
    SELECT * INTO request FROM __CORE__.capture_owner_corrections
        WHERE request_id=NEW.correction_request_id;
    IF NOT FOUND OR request.capture_id IS DISTINCT FROM NEW.raw_capture_id
        OR NEW.capture_item_id IS NULL THEN
        RAISE EXCEPTION 'correction capture identity required';
    END IF;
    IF NEW.is_retraction THEN
        IF NEW.capture_item_id<>request.expected_item_id THEN
            RAISE EXCEPTION 'retraction must retain original item';
        END IF;
    ELSE
        IF item.correction_request_id IS DISTINCT FROM NEW.correction_request_id
            OR request.operation<>'replace' THEN
            RAISE EXCEPTION 'replacement atom requires corrected item';
        END IF;
    END IF;
    IF NEW.supersedes IS NOT NULL THEN
        SELECT * INTO prior FROM __CORE__.atoms WHERE id=NEW.supersedes;
        IF NOT FOUND OR prior.is_retraction OR prior.capture_item_id IS DISTINCT FROM request.expected_item_id
            OR ROW(prior.raw_capture_id,prior.metric_key,prior.capture_component,prior.kind)
             IS DISTINCT FROM ROW(NEW.raw_capture_id,NEW.metric_key,NEW.capture_component,NEW.kind) THEN
            RAISE EXCEPTION 'correction atom lineage mismatch';
        END IF;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION __CORE__.validate_capture_atom_correction() FROM PUBLIC;
CREATE TRIGGER validate_capture_atom_correction BEFORE INSERT ON __CORE__.atoms
    FOR EACH ROW EXECUTE FUNCTION __CORE__.validate_capture_atom_correction();
CREATE OR REPLACE VIEW __CORE__.atoms_current WITH(security_invoker=true) AS
    SELECT a.* FROM __CORE__.atoms a WHERE NOT a.is_retraction
    AND NOT EXISTS(SELECT 1 FROM __CORE__.atoms s WHERE s.supersedes=a.id);
GRANT SELECT ON __CORE__.atoms_current TO capture_owner;

CREATE TABLE __CORE__.capture_correction_outcomes (
    request_id uuid PRIMARY KEY REFERENCES __CORE__.capture_owner_corrections(request_id),
    result jsonb NOT NULL CHECK(jsonb_typeof(result)='object'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE __CORE__.capture_correction_outcomes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_correction_outcomes FROM PUBLIC,anon,authenticated,
    service_role,model_egress,reference_egress,capture_ingest;
GRANT SELECT,INSERT ON __CORE__.capture_correction_outcomes TO capture_owner;
GRANT SELECT ON __CORE__.capture_correction_outcomes TO service_role;
CREATE POLICY owner_capture_correction_outcomes ON __CORE__.capture_correction_outcomes
    TO capture_owner USING(true) WITH CHECK(true);
CREATE POLICY service_read_capture_correction_outcomes ON __CORE__.capture_correction_outcomes
    FOR SELECT TO service_role USING(true);
CREATE TRIGGER capture_correction_outcomes_immutable
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.capture_correction_outcomes
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER capture_correction_outcomes_recorded_at
    BEFORE INSERT ON __CORE__.capture_correction_outcomes
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

-- A model retry cannot replace the transcript/extraction underlying resolved
-- items. Keep its outcome as unapplied history so mailbox retirement still works.
CREATE FUNCTION __CORE__.preserve_resolved_capture_history() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    IF NEW.applied AND EXISTS(SELECT 1 FROM __CORE__.capture_resolved_items
        WHERE capture_id=NEW.raw_capture_id)
        AND (EXISTS(SELECT 1 FROM __CORE__.capture_extraction_attempts
            WHERE request_id=NEW.attempt_id AND capture_id=NEW.raw_capture_id)
          OR EXISTS(SELECT 1 FROM __CORE__.capture_transcription_attempts
            WHERE request_id=NEW.attempt_id AND capture_id=NEW.raw_capture_id)) THEN
        NEW.applied := false;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION __CORE__.preserve_resolved_capture_history() FROM PUBLIC;
CREATE TRIGGER preserve_resolved_capture_history BEFORE INSERT ON __CORE__.capture_processing_events
    FOR EACH ROW EXECUTE FUNCTION __CORE__.preserve_resolved_capture_history();
