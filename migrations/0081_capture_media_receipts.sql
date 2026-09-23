-- Private media upload identity precedes raw capture acknowledgement.
-- Storage policies are a separate platform activation artifact; no bucket is created here.
DO $roles$ BEGIN
    CREATE ROLE capture_media_upload NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    CREATE ROLE capture_media_reader NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticator') THEN
        GRANT capture_media_upload,capture_media_reader TO authenticator;
    END IF;
END $roles$;
CREATE TABLE __CORE__.capture_media_uploads (
    capture_id uuid PRIMARY KEY,
    media_kind text NOT NULL CHECK (media_kind IN ('voice','photo')),
    media_path text NOT NULL UNIQUE,
    sha256 text NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes BETWEEN 1 AND 52428800),
    content_type text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(capture_id,sha256),
    CHECK (media_path=capture_id::text || '/' || CASE media_kind WHEN 'voice' THEN 'audio' ELSE 'photo' END)
);
CREATE TABLE __CORE__.capture_media_receipts (
    capture_id uuid PRIMARY KEY,
    sha256 text NOT NULL,
    verification_method text NOT NULL CHECK (verification_method IN ('upload_response','private_hash_check')),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(capture_id,sha256) REFERENCES __CORE__.capture_media_uploads(capture_id,sha256)
);
ALTER TABLE __CORE__.capture_media_uploads ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.capture_media_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.capture_media_uploads,__CORE__.capture_media_receipts
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_upload,capture_media_reader,service_role;
GRANT SELECT ON __CORE__.capture_media_uploads,__CORE__.capture_media_receipts TO service_role;
CREATE POLICY service_media_uploads ON __CORE__.capture_media_uploads FOR SELECT TO service_role USING(true);
CREATE POLICY service_media_receipts ON __CORE__.capture_media_receipts FOR SELECT TO service_role USING(true);
CREATE TRIGGER media_uploads_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_media_uploads FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER media_receipts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.capture_media_receipts FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

CREATE FUNCTION public.begin_capture_media_upload(p_capture_id uuid,p_kind text,p_sha256 text,p_size bigint,p_content_type text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE old __CORE__.capture_media_uploads; path text; duplicate boolean;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='25000';
    END IF;
    IF p_capture_id IS NULL OR p_capture_id::text !~ '^[a-f0-9]{8}-[a-f0-9]{4}-7[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$'
       OR p_kind IS NULL OR p_kind NOT IN ('voice','photo')
       OR p_sha256 IS NULL OR p_sha256 !~ '^[a-f0-9]{64}$'
       OR p_size IS NULL OR p_size NOT BETWEEN 1 AND 52428800
       OR p_content_type IS NULL
       OR NOT ((p_kind='voice' AND p_content_type ~ '^audio/[a-z0-9.+-]+$')
               OR (p_kind='photo' AND p_content_type IN ('image/jpeg','image/png'))) THEN
        RAISE EXCEPTION 'invalid media upload metadata' USING ERRCODE='22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_capture_id::text,81));
    SELECT * INTO old FROM __CORE__.capture_media_uploads WHERE capture_id=p_capture_id;
    duplicate := FOUND;
    path := p_capture_id::text || '/' || CASE p_kind WHEN 'voice' THEN 'audio' ELSE 'photo' END;
    IF duplicate THEN
        IF (old.media_kind,old.sha256,old.size_bytes,old.content_type)
           IS DISTINCT FROM (p_kind,p_sha256,p_size,p_content_type) THEN
            RAISE EXCEPTION 'media identity reused with different content' USING ERRCODE='22023';
        END IF;
    ELSE
        INSERT INTO __CORE__.capture_media_uploads(capture_id,media_kind,media_path,sha256,size_bytes,content_type)
            VALUES(p_capture_id,p_kind,path,p_sha256,p_size,p_content_type);
    END IF;
    RETURN jsonb_build_object('capture_id',p_capture_id,'media_path',path,'media_sha256',p_sha256,
        'size_bytes',p_size,'duplicate',duplicate,'status',CASE WHEN EXISTS (
            SELECT 1 FROM __CORE__.capture_media_receipts WHERE capture_id=p_capture_id)
            THEN 'available' ELSE 'awaiting_upload' END);
END $fn$;
REVOKE ALL ON FUNCTION public.begin_capture_media_upload(uuid,text,text,bigint,text)
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_reader;
GRANT EXECUTE ON FUNCTION public.begin_capture_media_upload(uuid,text,text,bigint,text) TO capture_media_upload;

CREATE FUNCTION __CORE__.complete_capture_media(p_capture_id uuid,p_sha256 text,p_method text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$
DECLARE media __CORE__.capture_media_uploads;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='25000';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_capture_id::text,81));
    SELECT * INTO media FROM __CORE__.capture_media_uploads WHERE capture_id=p_capture_id;
    IF NOT FOUND OR media.sha256 IS DISTINCT FROM p_sha256 THEN
        RAISE EXCEPTION 'matching media upload required' USING ERRCODE='22023';
    END IF;
    INSERT INTO __CORE__.capture_media_receipts(capture_id,sha256,verification_method)
        VALUES(p_capture_id,p_sha256,p_method) ON CONFLICT(capture_id) DO NOTHING;
    RETURN jsonb_build_object('capture_id',p_capture_id,'media_path',media.media_path,
        'media_sha256',media.sha256,'size_bytes',media.size_bytes,'status','available');
END $fn$;
REVOKE ALL ON FUNCTION __CORE__.complete_capture_media(uuid,text,text) FROM PUBLIC;
CREATE FUNCTION public.complete_capture_media_upload(p_capture_id uuid,p_sha256 text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path='' AS $fn$
    SELECT __CORE__.complete_capture_media(p_capture_id,p_sha256,'upload_response');
$fn$;
CREATE FUNCTION public.reconcile_capture_media_upload(p_capture_id uuid,p_sha256 text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path='' AS $fn$
    SELECT __CORE__.complete_capture_media(p_capture_id,p_sha256,'private_hash_check');
$fn$;
REVOKE ALL ON FUNCTION public.complete_capture_media_upload(uuid,text),public.reconcile_capture_media_upload(uuid,text)
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,capture_media_reader,capture_media_upload,service_role;
GRANT EXECUTE ON FUNCTION public.complete_capture_media_upload(uuid,text) TO capture_media_upload;
GRANT EXECUTE ON FUNCTION public.reconcile_capture_media_upload(uuid,text) TO service_role;

-- Storage RLS calls only these narrow lookups; neither role reads private tables.
CREATE FUNCTION public.capture_media_upload_allowed(p_bucket text,p_name text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $fn$
    SELECT p_bucket='captures' AND EXISTS(SELECT 1 FROM __CORE__.capture_media_uploads u
        WHERE u.media_path=p_name AND NOT EXISTS(SELECT 1 FROM __CORE__.capture_media_receipts r WHERE r.capture_id=u.capture_id));
$fn$;
CREATE FUNCTION public.capture_media_read_allowed(p_bucket text,p_name text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $fn$
    SELECT p_bucket='captures' AND EXISTS(SELECT 1 FROM __CORE__.capture_media_uploads WHERE media_path=p_name);
$fn$;
REVOKE ALL ON FUNCTION public.capture_media_upload_allowed(text,text),public.capture_media_read_allowed(text,text)
    FROM PUBLIC,anon,authenticated,capture_ingest,model_egress,service_role,capture_media_upload,capture_media_reader;
GRANT EXECUTE ON FUNCTION public.capture_media_upload_allowed(text,text) TO capture_media_upload;
GRANT EXECUTE ON FUNCTION public.capture_media_read_allowed(text,text) TO capture_media_reader;
