-- Platform activation artifact, NOT a core migration. Execute transactionally only
-- after explicit deployment approval and private bucket creation through Storage API.
-- Requires0081. Existing unrelated buckets/policies are preserved.
DO $preflight$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM storage.buckets WHERE id='captures' AND public=false
                   AND file_size_limit IS NOT NULL AND file_size_limit <= 52428800) THEN
        RAISE EXCEPTION 'private captures bucket with <=50MiB limit required';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='storage.objects'::regclass) THEN
        RAISE EXCEPTION 'Storage objects RLS must already be enabled';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c,
        LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
        WHERE c.oid='storage.objects'::regclass AND a.grantee=0
          AND a.privilege_type IN ('TRUNCATE','TRIGGER','REFERENCES')) THEN
        RAISE EXCEPTION 'Storage PUBLIC privileges bypass RLS; review before activation';
    END IF;
END $preflight$;
GRANT USAGE ON SCHEMA storage TO capture_media_upload,capture_media_reader;
REVOKE ALL ON storage.objects FROM capture_media_upload,capture_media_reader;
GRANT INSERT ON storage.objects TO capture_media_upload;
GRANT SELECT ON storage.objects TO capture_media_reader;

-- A permissive policy inherited through PUBLIC must not expose the new bucket.
CREATE POLICY captures_private_guard ON storage.objects AS RESTRICTIVE FOR ALL TO PUBLIC
    USING(bucket_id <> 'captures' OR current_user::text IN ('capture_media_upload','capture_media_reader'))
    WITH CHECK(bucket_id <> 'captures' OR current_user::text IN ('capture_media_upload','capture_media_reader'));
CREATE POLICY captures_upload ON storage.objects FOR INSERT TO capture_media_upload
    WITH CHECK(public.capture_media_upload_allowed(bucket_id,name));
CREATE POLICY captures_read ON storage.objects FOR SELECT TO capture_media_reader
    USING(public.capture_media_read_allowed(bucket_id,name));
-- Restrictive role bounds also contain existing broader PUBLIC policies/grants.
CREATE POLICY captures_upload_scope ON storage.objects AS RESTRICTIVE FOR INSERT TO capture_media_upload
    WITH CHECK(public.capture_media_upload_allowed(bucket_id,name));
CREATE POLICY captures_read_scope ON storage.objects AS RESTRICTIVE FOR SELECT TO capture_media_reader
    USING(public.capture_media_read_allowed(bucket_id,name));
CREATE POLICY captures_upload_no_read ON storage.objects AS RESTRICTIVE FOR SELECT TO capture_media_upload USING(false);
CREATE POLICY captures_reader_no_insert ON storage.objects AS RESTRICTIVE FOR INSERT TO capture_media_reader WITH CHECK(false);
CREATE POLICY captures_no_update ON storage.objects AS RESTRICTIVE FOR UPDATE TO capture_media_upload,capture_media_reader
    USING(false) WITH CHECK(false);
CREATE POLICY captures_no_delete ON storage.objects AS RESTRICTIVE FOR DELETE TO capture_media_upload,capture_media_reader USING(false);
