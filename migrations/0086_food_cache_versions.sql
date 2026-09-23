-- REQ-NUT-008: refreshed reference data is a new version, not a mutation of
-- the row an existing nutrition atom identifies.
ALTER TABLE __CORE__.foods_cache
    DROP CONSTRAINT foods_cache_canonical_name_source_source_id_key;
ALTER TABLE __CORE__.foods_cache ADD CONSTRAINT foods_cache_version_key
    UNIQUE(canonical_name,source,source_id,fetched_at);
CREATE INDEX foods_cache_identity_versions
    ON __CORE__.foods_cache(canonical_name,source,source_id,fetched_at DESC);

-- The review queue is a current projection. Preserve its earlier reason and
-- knowledge time when source attempts change an operational hold to no-match.
ALTER TABLE __CORE__.unresolved_items ADD COLUMN tried_recorded_at timestamptz;
UPDATE __CORE__.unresolved_items SET tried_recorded_at=seen_at;
ALTER TABLE __CORE__.unresolved_items ALTER COLUMN tried_recorded_at SET NOT NULL;
ALTER TABLE __CORE__.unresolved_items ALTER COLUMN tried_recorded_at SET DEFAULT clock_timestamp();
CREATE TABLE __CORE__.unresolved_item_history (
    history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id uuid NOT NULL REFERENCES __CORE__.unresolved_items(item_id),
    tried jsonb NOT NULL,
    recorded_at timestamptz NOT NULL
);
REVOKE ALL ON __CORE__.unresolved_item_history FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON __CORE__.unresolved_item_history TO service_role;
CREATE TRIGGER unresolved_item_history_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.unresolved_item_history FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE FUNCTION __CORE__.preserve_unresolved_review_history()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NEW.tried IS DISTINCT FROM OLD.tried THEN
        INSERT INTO __CORE__.unresolved_item_history(item_id,tried,recorded_at)
            VALUES(OLD.item_id,OLD.tried,OLD.tried_recorded_at);
        NEW.tried_recorded_at := clock_timestamp();
    ELSE
        NEW.tried_recorded_at := OLD.tried_recorded_at;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION __CORE__.preserve_unresolved_review_history() FROM PUBLIC;
CREATE TRIGGER unresolved_review_history BEFORE UPDATE OF tried ON __CORE__.unresolved_items
    FOR EACH ROW EXECUTE FUNCTION __CORE__.preserve_unresolved_review_history();
GRANT UPDATE(tried) ON __CORE__.unresolved_items TO service_role;
