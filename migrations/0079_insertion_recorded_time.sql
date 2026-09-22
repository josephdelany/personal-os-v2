-- ADR0149 / RULE03/04: transaction start can precede facts learned inside it.
-- Preserve server-forced timestamps and immutable existing rows; correct future inserts.
CREATE OR REPLACE FUNCTION __CORE__.force_recorded_at() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
    NEW.recorded_at := clock_timestamp();
    RETURN NEW;
END;
$$;

-- Current reads use the statement's clock; explicit replay cutoffs remain unchanged.
-- Reuse the latest installed bodies instead of copying the large Ask implementation.
DO $repair$
DECLARE signature text; proc regprocedure; definition text;
BEGIN
    FOREACH signature IN ARRAY ARRAY[
        'public.ask(text,date,timestamp with time zone)',
        'analysis.f_daily_panel(date)',
        'analysis.f_panel_provenance(text,date,date,date,timestamp with time zone)',
        'analysis.f_domain_status(date,timestamp with time zone)',
        'public.search_record(text,integer)',
        'public.search_record(text,integer,timestamp with time zone)'
    ] LOOP
        proc := to_regprocedure(signature);
        IF proc IS NULL THEN RAISE EXCEPTION 'missing current-read owner: %',signature; END IF;
        definition := pg_get_functiondef(proc);
        IF position('now()' IN definition)=0 THEN
            RAISE EXCEPTION 'current-read clock contract changed: %',signature;
        END IF;
        EXECUTE replace(definition,'now()','statement_timestamp()');
    END LOOP;
END $repair$;
