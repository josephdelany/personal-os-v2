-- V0 deployment inventory only. No owner RPC is invoked (reads may persist results).
-- Run privately with psql's normal connection configuration after credential repair:
-- psql -X -v ON_ERROR_STOP=1 -f ops/preflight/v0_backend.sql
BEGIN TRANSACTION READ ONLY;
SELECT current_setting('server_version') AS server_version;
WITH required(signature) AS (VALUES
 ('public.save_v0_checkin(jsonb)'), ('public.get_v0_checkins(date)'),
 ('public.save_v0_meal(jsonb)'), ('public.get_v0_meals(date)'),
 ('public.save_v0_workout(jsonb)'), ('public.get_v0_workouts(date)'),
 ('public.get_v0_day(date)'), ('public.get_v0_visits(date)'),
 ('public.get_v0_card_activity(uuid,date,date)'),
 ('public.review_v0_card_row(jsonb)'),
 ('public.ingest_location_batch(jsonb)'), ('public.refresh_v0_visits()')
)
SELECT signature, to_regprocedure(signature) IS NOT NULL AS installed,
       md5(pg_get_functiondef(to_regprocedure(signature))) AS definition_fingerprint
FROM required ORDER BY signature;
-- Actual effective grants, including grants inherited from PUBLIC.
SELECT n.nspname AS schema_name,p.proname AS function_name,
       pg_get_function_identity_arguments(p.oid) AS arguments,
       r.rolname AS role_name,has_function_privilege(r.oid,p.oid,'EXECUTE') AS can_execute,
       p.prosecdef AS security_definer,p.proconfig AS function_settings
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
CROSS JOIN pg_roles r
WHERE n.nspname IN ('public','core')
  AND (p.proname LIKE '%v0%' OR p.proname IN ('ingest_location','ingest_location_batch'))
  AND r.rolname IN ('anon','authenticated','service_role','capture_ingest','model_egress',
     'reference_egress','capture_media_upload','capture_media_reader')
ORDER BY p.proname,arguments,r.rolname;
SELECT n.nspname AS schema_name,c.relname AS relation_name,
       r.rolname AS role_name,
       has_table_privilege(r.oid,c.oid,'SELECT') AS can_select,
       has_table_privilege(r.oid,c.oid,'INSERT') AS can_insert,
       has_table_privilege(r.oid,c.oid,'UPDATE') AS can_update,
       has_table_privilege(r.oid,c.oid,'DELETE') AS can_delete
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN pg_roles r
WHERE c.relkind IN ('r','p')
 AND n.nspname IN ('core','restricted')
 AND (c.relname LIKE 'v0_%' OR c.relname IN ('location_receipts','raw_captures','atoms'))
 AND r.rolname IN ('anon','authenticated','service_role','capture_ingest','model_egress',
     'reference_egress','capture_media_upload','capture_media_reader')
ORDER BY n.nspname,c.relname,r.rolname;
SELECT schemaname,tablename,policyname,roles,cmd,permissive,qual,with_check
FROM pg_policies WHERE schemaname='storage' AND tablename='objects'
ORDER BY policyname;
ROLLBACK;
