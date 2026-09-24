-- ADR0164 / CAP014/066: explicit owner time, no nutrient recomputation.
ALTER TABLE __CORE__.capture_owner_corrections
    DROP CONSTRAINT capture_owner_corrections_operation_check,
    DROP CONSTRAINT capture_owner_corrections_check,
    ADD COLUMN corrected_occurred_at timestamptz CHECK(isfinite(corrected_occurred_at)),
    ADD COLUMN corrected_time_precision __CORE__.time_precision,
    ADD COLUMN corrected_subject_day date,
    ADD CONSTRAINT capture_correction_operation CHECK(operation IN ('replace','remove','retime')),
    ADD CONSTRAINT capture_correction_value_shape CHECK(
        (operation='replace' AND food_id IS NOT NULL AND quantity_kind IS NOT NULL AND quantity IS NOT NULL)
        OR (operation IN ('remove','retime') AND food_id IS NULL AND quantity_kind IS NULL AND quantity IS NULL)),
    ADD CONSTRAINT capture_correction_time_shape CHECK(
        (operation='retime' AND corrected_occurred_at IS NOT NULL
            AND corrected_time_precision IS NOT NULL AND corrected_subject_day IS NOT NULL)
        OR (operation<>'retime' AND corrected_occurred_at IS NULL
            AND corrected_time_precision IS NULL AND corrected_subject_day IS NULL));

CREATE OR REPLACE FUNCTION __CORE__.validate_capture_item_correction() RETURNS trigger
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
    IF NOT FOUND OR ROW(prior.capture_id,prior.extraction_request_id,prior.item_index)
        IS DISTINCT FROM ROW(NEW.capture_id,NEW.extraction_request_id,NEW.item_index) THEN
        RAISE EXCEPTION 'correction must preserve capture and extracted position';
    END IF;
    IF request.operation='retime' THEN
        IF ROW(NEW.occurred_at,NEW.subject_day,NEW.time_precision)
            IS DISTINCT FROM ROW(request.corrected_occurred_at,request.corrected_subject_day,
                                 request.corrected_time_precision)
            OR NEW.time_provenance<>'extracted' OR NEW.time_reason<>'owner_correction'
            OR (NEW.resolution-'owner_correction') IS DISTINCT FROM (prior.resolution-'owner_correction') THEN
            RAISE EXCEPTION 'time correction must match owner request and preserve resolution';
        END IF;
    ELSIF ROW(prior.occurred_at,prior.subject_day,prior.time_precision,prior.time_provenance,prior.time_reason)
        IS DISTINCT FROM ROW(NEW.occurred_at,NEW.subject_day,NEW.time_precision,NEW.time_provenance,NEW.time_reason) THEN
        RAISE EXCEPTION 'non-time correction must preserve event time';
    END IF;
    -- The UNIQUE predecessor constraint also rejects concurrent forks.
    IF EXISTS(SELECT 1 FROM __CORE__.capture_resolved_items
              WHERE supersedes_item_id=NEW.supersedes_item_id) THEN
        RAISE EXCEPTION 'stale correction predecessor';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION __CORE__.validate_capture_atom_correction() RETURNS trigger
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
            OR request.operation NOT IN ('replace','retime') THEN
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
    IF request.operation='retime' THEN
        IF NEW.is_retraction OR NEW.supersedes IS NULL OR prior.valid_interval IS NOT NULL
            OR (to_jsonb(NEW)-ARRAY['id','recorded_at','occurred_at','subject_day','time_precision',
                                  'event_time_provenance','capture_item_id','correction_request_id','supersedes'])
               IS DISTINCT FROM
               (to_jsonb(prior)-ARRAY['id','recorded_at','occurred_at','subject_day','time_precision',
                                    'event_time_provenance','capture_item_id','correction_request_id','supersedes']) THEN
            RAISE EXCEPTION 'time correction must preserve point atom values and provenance';
        END IF;
    END IF;
    RETURN NEW;
END $$;
