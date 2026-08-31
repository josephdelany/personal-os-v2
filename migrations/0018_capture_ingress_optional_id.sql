-- 0018_capture_ingress_optional_id.sql — make capture_id server-defaulted (ADR-0034)
--
-- iOS Shortcuts has no native UUID action, so requiring the client to supply capture_id
-- (0017) makes the Shortcut hard for a non-engineer. Default it server-side. Idempotency
-- (ON CONFLICT dedupe) is preserved when a client DOES supply an id — automated feeds
-- will — while a one-tap manual capture, which never retries, needs no id. Trailing
-- DEFAULT so PostgREST callers may omit it.

DROP FUNCTION IF EXISTS public.ingest_capture(uuid,timestamptz,text,jsonb);

CREATE OR REPLACE FUNCTION public.ingest_capture(
    p_captured_at timestamptz,
    p_source      text,
    p_payload     jsonb,
    p_capture_id  uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
DECLARE v_id uuid;
BEGIN
    IF p_source NOT IN ('shortcut_voice','shortcut_photo','shortcut_text','pwa_text') THEN
        RAISE EXCEPTION 'ingest_capture: source % not permitted on the public capture path', p_source;
    END IF;
    IF p_payload IS NULL OR p_payload = 'null'::jsonb THEN
        RAISE EXCEPTION 'ingest_capture: payload is required';
    END IF;
    v_id := coalesce(p_capture_id, pg_catalog.gen_random_uuid());
    INSERT INTO __CORE__.raw_captures
        (capture_id, captured_at, source, trust_level, payload, processing_status)
    VALUES (v_id, p_captured_at, p_source::__CORE__.capture_source,
            'trusted'::__CORE__.trust_level, p_payload, 'received')
    ON CONFLICT (capture_id) DO NOTHING;
    RETURN v_id;
END
$fn$;

REVOKE ALL ON FUNCTION public.ingest_capture(timestamptz,text,jsonb,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.ingest_capture(timestamptz,text,jsonb,uuid) TO anon, authenticated;

COMMENT ON FUNCTION public.ingest_capture(timestamptz,text,jsonb,uuid) IS
  'ADR-0034: write-only capture ingress. anon appends a self-authored capture; capture_id '
  'is server-generated when omitted. Third-party feeds are ETL-ingested, not via this path.';
