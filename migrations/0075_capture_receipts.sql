-- ADR-0143: service-only atomic capture receipt. Legacy ingest_capture is retained
-- until an explicitly approved device cutover; it does NOT meet the new contract.
DO $role$ BEGIN
    -- Forward-only: refuse a name collision instead of adopting unknown grants,
    -- memberships or elevated attributes from a pre-existing role.
    CREATE ROLE capture_ingest NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB
        NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
        GRANT capture_ingest TO authenticator;
    END IF;
END $role$;
-- PUBLIC privileges are inherited even by NOINHERIT roles. Earlier migrations
-- omitted PUBLIC revocation on these application functions (0065 recreated its
-- two-argument wrapper). Keep intended owner/ETL APIs, close ambient execution.
REVOKE ALL ON FUNCTION public.checkin_mirror_to_spine() FROM PUBLIC;
REVOKE ALL ON FUNCTION public._ask_strip_range_words(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public._ask_unsupported_shape(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public._ask_drop_shape_words(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.search_record(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.derivation_support(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_record(text, integer),
    public.derivation_support(text) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public._ask_strip_range_words(text),
    public._ask_unsupported_shape(text), public._ask_drop_shape_words(text)
    TO service_role;
CREATE TABLE __OPS__.ingest_rejections (
    rejection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    raw_body text NOT NULL,
    reason text NOT NULL
);
ALTER TABLE __OPS__.ingest_rejections ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __OPS__.ingest_rejections FROM PUBLIC, anon, authenticated;
GRANT SELECT ON __OPS__.ingest_rejections TO service_role;
CREATE TRIGGER ingest_rejections_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __OPS__.ingest_rejections
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

CREATE FUNCTION public.receive_capture(p_raw_body text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    body jsonb;
    reason text;
    cid uuid;
    occurred timestamptz;
    inserted_id uuid;
BEGIN
    -- Preserve the exact authenticated body, including malformed JSON, on rejection.
    IF p_raw_body IS NULL THEN
        RAISE EXCEPTION 'raw body required' USING ERRCODE = '22004';
    END IF;
    BEGIN
        body := p_raw_body::jsonb;
    EXCEPTION WHEN invalid_text_representation OR untranslatable_character
        OR numeric_value_out_of_range THEN
        reason := 'invalid_json';
    END;
    IF reason IS NULL THEN
        IF jsonb_typeof(body) IS DISTINCT FROM 'object' THEN
            reason := 'invalid_envelope';
        ELSIF coalesce(body->>'capture_id', '') = ''
           OR coalesce(body->>'captured_at', '') = '' THEN
            reason := 'missing_identity_fields';
        ELSIF jsonb_typeof(body->'capture_id') IS DISTINCT FROM 'string'
           OR (body->>'capture_id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
            reason := 'invalid_capture_id';
        ELSIF jsonb_typeof(body->'captured_at') IS DISTINCT FROM 'string'
           OR (body->>'captured_at') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
            reason := 'invalid_captured_at';
        ELSIF body->>'source' IS NULL OR body->>'source' NOT IN
            ('shortcut_voice','shortcut_photo','shortcut_text','pwa_text') THEN
            reason := 'invalid_source';
        ELSIF body->'payload' IS NULL OR body->'payload' = 'null'::jsonb THEN
            reason := 'missing_payload';
        END IF;
    END IF;
    IF reason IS NULL THEN
        cid := (body->>'capture_id')::uuid;
        BEGIN
            occurred := (body->>'captured_at')::timestamptz;
        EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
            reason := 'invalid_captured_at';
        END;
    END IF;
    IF reason IS NOT NULL THEN
        INSERT INTO __OPS__.ingest_rejections(raw_body, reason)
        VALUES (p_raw_body, reason);
        RETURN jsonb_build_object('status', 'rejected', 'error', reason);
    END IF;
    INSERT INTO __CORE__.raw_captures
        (capture_id, captured_at, source, trust_level, payload, processing_status)
    VALUES (cid, occurred, (body->>'source')::__CORE__.capture_source,
            'trusted'::__CORE__.trust_level, body->'payload', 'received')
    ON CONFLICT (capture_id) DO NOTHING
    RETURNING capture_id INTO inserted_id;
    -- Only the INSERT result decides this; an earlier existence snapshot races.
    RETURN jsonb_build_object('status', CASE WHEN inserted_id IS NULL
        THEN 'duplicate' ELSE 'created' END, 'capture_id', cid);
END
$fn$;
REVOKE ALL ON FUNCTION public.receive_capture(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.receive_capture(text) TO capture_ingest, service_role;
