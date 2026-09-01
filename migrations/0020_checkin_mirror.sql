-- 0020_checkin_mirror.sql — bridge: public.checkins -> core.raw_captures (ADR-0035)
--
-- The phone's morning/night shortcuts POST to the OLD Edge Function (ingest-checkin),
-- which writes public.checkins. Rather than editing the phone or redeploying the
-- function, this trigger mirrors every check-in submission into the trustworthy
-- spine's capture table, so the existing shortcuts feed the new system with zero
-- device changes. The mirror is append-only-friendly: an upsert re-submission fires
-- a fresh capture row (a correction that supersedes by recorded_at, never an edit).
--
-- trust_level='trusted' (self-authored, from Joe's own shortcut — ADR-0020).
-- source='shortcut_text' (the capture arrived via an iOS shortcut, REQ-CAP-006).
-- SECURITY DEFINER + empty search_path: the writer role of public.checkins
-- (service_role via the Edge Function) does hold INSERT on core.raw_captures, but
-- definer-rights makes the mirror independent of future grant changes.

-- FAIL-OPEN (reviewer M3): a mirror must never break the primary. If the spine-side
-- INSERT fails for any reason, the exception is caught and logged as a WARNING and
-- the check-in write itself succeeds — the OLD system's working ingest is never
-- coupled to the spine's health. The cost, named: a mirror failure drops that
-- capture from the spine silently at write time; the extract job's ops.runs
-- heartbeat plus a checkins-vs-captures count comparison is the detection path.
CREATE OR REPLACE FUNCTION public.checkin_mirror_to_spine() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
BEGIN
    INSERT INTO __CORE__.raw_captures (capture_id, captured_at, source, trust_level, payload)
    VALUES (
        pg_catalog.gen_random_uuid(),
        NEW.ts,
        'shortcut_text'::__CORE__.capture_source,
        'trusted'::__CORE__.trust_level,
        pg_catalog.jsonb_strip_nulls(pg_catalog.jsonb_build_object(
            'kind',            'checkin',
            'type',            NEW.type,
            'checkin_date',    NEW.checkin_date,
            'restored',        NEW.restored,
            'energy',          NEW.energy,
            'mood',            NEW.mood,
            'mental_clarity',  NEW.mental_clarity,
            'drive',           NEW.drive,
            'sleep_feel',      NEW.sleep_feel,
            'stress',          NEW.stress,
            'mental_sharpness',NEW.mental_sharpness,
            'day_rating',      NEW.day_rating,
            'note',            NEW.note,
            'meta',            NEW.meta
        ))
    );
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'checkin_mirror_to_spine failed (check-in still saved): %', SQLERRM;
    RETURN NEW;
END
$fn$;

CREATE OR REPLACE TRIGGER checkins_mirror_to_spine
    AFTER INSERT OR UPDATE ON public.checkins
    FOR EACH ROW EXECUTE FUNCTION public.checkin_mirror_to_spine();

-- One-time mirror of the check-ins that already exist (real rows, real provenance —
-- ingest of live operational data, not the deferred Parquet legacy load of ADR-0028
-- and not fabrication). captured_at = the original submission instant.
INSERT INTO __CORE__.raw_captures (capture_id, captured_at, source, trust_level, payload)
SELECT pg_catalog.gen_random_uuid(),
       c.ts,
       'shortcut_text'::__CORE__.capture_source,
       'trusted'::__CORE__.trust_level,
       pg_catalog.jsonb_strip_nulls(pg_catalog.jsonb_build_object(
           'kind','checkin','type',c.type,'checkin_date',c.checkin_date,
           'restored',c.restored,'energy',c.energy,'mood',c.mood,
           'mental_clarity',c.mental_clarity,'drive',c.drive,'sleep_feel',c.sleep_feel,
           'stress',c.stress,'mental_sharpness',c.mental_sharpness,'day_rating',c.day_rating,
           'note',c.note,'meta',c.meta,'mirror','backfill_0020'))
FROM public.checkins c
WHERE NOT EXISTS (
    SELECT 1 FROM __CORE__.raw_captures rc
     WHERE rc.payload->>'mirror' = 'backfill_0020'
       AND rc.payload->>'checkin_date' = c.checkin_date::text
       AND rc.payload->>'type' = c.type);

COMMENT ON FUNCTION public.checkin_mirror_to_spine() IS
  'ADR-0035: every check-in submission (old Edge Function -> public.checkins) is '
  'mirrored as an immutable spine capture. Zero phone changes; corrections append.';
