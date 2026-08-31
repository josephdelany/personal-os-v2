-- 0017_capture_ingress_rpc.sql — the write-only capture ingress (ADR-0034)
--
-- A Shortcut lands a capture by calling public.ingest_capture(...) via PostgREST.
-- The function is SECURITY DEFINER (runs as owner, which holds INSERT on raw_captures)
-- but grants `anon` EXECUTE and NOTHING ELSE: the public credential can append a
-- self-authored capture and cannot read a row, reach the core schema, touch another
-- table, or mutate. This is ADR-0020's read/egress separation applied to ingress.
--   search_path='' + fully-qualified names: hardens the SECURITY DEFINER against
--     search-path hijacking.
--   source allow-list: only self-authored Shortcut/PWA sources; third-party feeds
--     (email_receipt, healthkit_workout, location) are untrusted-lane, ETL-only.
--   trust_level forced 'trusted'; recorded_at forced by the existing trigger.
--   ON CONFLICT DO NOTHING on the client-supplied capture_id: a retried POST is safe.

CREATE OR REPLACE FUNCTION public.ingest_capture(
    p_capture_id  uuid,
    p_captured_at timestamptz,
    p_source      text,
    p_payload     jsonb
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
BEGIN
    IF p_source NOT IN ('shortcut_voice','shortcut_photo','shortcut_text','pwa_text') THEN
        RAISE EXCEPTION 'ingest_capture: source % not permitted on the public capture path', p_source;
    END IF;
    IF p_payload IS NULL OR p_payload = 'null'::jsonb THEN
        RAISE EXCEPTION 'ingest_capture: payload is required';
    END IF;
    INSERT INTO __CORE__.raw_captures
        (capture_id, captured_at, source, trust_level, payload, processing_status)
    VALUES
        (p_capture_id, p_captured_at, p_source::__CORE__.capture_source,
         'trusted'::__CORE__.trust_level, p_payload, 'received')
    ON CONFLICT (capture_id) DO NOTHING;
    RETURN p_capture_id;
END
$fn$;

-- Narrow the grant: no one gets it by default; anon/authenticated get EXECUTE only.
REVOKE ALL ON FUNCTION public.ingest_capture(uuid,timestamptz,text,jsonb) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.ingest_capture(uuid,timestamptz,text,jsonb) TO anon, authenticated;

COMMENT ON FUNCTION public.ingest_capture(uuid,timestamptz,text,jsonb) IS
  'ADR-0034: write-only capture ingress. anon may append a self-authored Shortcut/PWA '
  'capture and nothing else. Third-party feeds are ETL-ingested, not via this path.';
