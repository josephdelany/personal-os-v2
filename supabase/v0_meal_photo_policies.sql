-- Activation only after approval; requires0081 storage policy artifact and0092.
-- Owner downloads use their authenticated JWT; bucket remains private.
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='captures' AND public=false) THEN
        RAISE EXCEPTION 'private captures bucket required';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='storage.objects'::regclass) THEN
        RAISE EXCEPTION 'Storage RLS required';
    END IF;
END $$;
GRANT USAGE ON SCHEMA storage TO authenticated;
GRANT SELECT ON storage.objects TO authenticated;
ALTER POLICY captures_private_guard ON storage.objects
    USING(bucket_id <> 'captures' OR current_user::text IN ('capture_media_upload','capture_media_reader')
        OR CASE WHEN current_user::text='authenticated'
            THEN public.v0_meal_photo_read_allowed(bucket_id,name) ELSE false END)
    WITH CHECK(bucket_id <> 'captures' OR current_user::text IN ('capture_media_upload','capture_media_reader'));
CREATE POLICY v0_meal_photo_read ON storage.objects FOR SELECT TO authenticated
    USING(public.v0_meal_photo_read_allowed(bucket_id,name));
CREATE POLICY v0_meal_photo_read_scope ON storage.objects AS RESTRICTIVE FOR SELECT TO authenticated
    USING(bucket_id <> 'captures' OR public.v0_meal_photo_read_allowed(bucket_id,name));
-- Preserve unrelated storage policies while refusing all owner writes to captures.
CREATE POLICY v0_meal_photo_no_insert ON storage.objects AS RESTRICTIVE FOR INSERT TO authenticated
    WITH CHECK(bucket_id <> 'captures');
CREATE POLICY v0_meal_photo_no_update ON storage.objects AS RESTRICTIVE FOR UPDATE TO authenticated
    USING(bucket_id <> 'captures') WITH CHECK(bucket_id <> 'captures');
CREATE POLICY v0_meal_photo_no_delete ON storage.objects AS RESTRICTIVE FOR DELETE TO authenticated
    USING(bucket_id <> 'captures');
