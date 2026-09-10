-- 0068_derivation_refusal.sql — an uncatalogued derivation is refused, never approximated
-- (REQ-REC-003, REQ-REC-004; INTENT_COVERAGE R7).
--
-- THE SCENARIO THIS EXISTS FOR. Browser history has visit timestamps and no session
-- instrumentation. Asked for "screen hours", a helpful system computes something from visit
-- counts and labels it screen hours. The number is then wrong in a way nobody can see: it is
-- not a bad estimate of screen time, it is a COUNT OF VISITS WEARING THE WRONG UNIT. Every
-- downstream comparison, trend and correlation inherits the mislabel, and nothing about the
-- stored row records that a substitution happened.
--
-- `config.derivation_catalogue` (0053) already records what each supported derived measure is
-- made of. What was missing was the refusal: the path taken when the answer is "this system
-- cannot derive that", which until now was a query returning zero rows and a caller free to
-- improvise.
--
-- WHY THERE IS NO "RELATED MEASURE" SUGGESTION. The first draft of this function returned
-- name-similar measures as orientation. That is a guess, inside a function whose entire purpose
-- is refusing to guess — and it does not even work: "screen_hours" and "browser_visits" are
-- related by SOURCE, not by name, and share no substring. For an uncatalogued measure this
-- system knows nothing about its inputs, so it cannot say what a substitute would be. What it
-- can state as fact is the complete set of derivations it DOES support, so the caller can see
-- the boundary rather than be nudged toward one side of it.
--
-- `substitute` is present, always null, and named in the payload. A field that is always null
-- is doing work here: it is the difference between a caller finding no substitute and a caller
-- not thinking to look for one.

CREATE OR REPLACE FUNCTION public.derivation_support(p_measure text)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE m text; row_c record; known boolean; near text[];
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    m := btrim(coalesce(p_measure, ''));
    IF m = '' THEN
        RETURN jsonb_build_object('supported', false, 'reason', 'no_measure_named',
                                  'substitute', NULL);
    END IF;

    SELECT * INTO row_c FROM config.derivation_catalogue d WHERE d.measure = m;
    IF FOUND THEN
        -- REQ-REC-004. The whole derivation travels with the answer: a caller that has the
        -- number and not the missingness rule cannot tell a real zero from an absent day.
        RETURN jsonb_build_object(
            'supported', true, 'measure', row_c.measure, 'method', row_c.method,
            'method_version', row_c.method_version, 'unit', row_c.unit,
            'time_specification', row_c.time_specification,
            'missingness_rule', row_c.missingness_rule,
            'input_fields', to_jsonb(row_c.input_fields),
            'earliest_supported_event_date', row_c.earliest_supported_event_date,
            'analytical_consumers', to_jsonb(row_c.analytical_consumers),
            'owner', row_c.owner);
    END IF;

    SELECT EXISTS (SELECT 1 FROM __CORE__.metric_registry r WHERE r.metric_key = m) INTO known;

    -- Everything this system CAN derive. A fact, not a suggestion.
    SELECT coalesce(array_agg(d.measure ORDER BY d.measure), '{}')
      INTO near FROM config.derivation_catalogue d;

    RETURN jsonb_build_object(
        'supported', false,
        -- REQ-REC-003's dispositions, distinguishing "we know this measure and have not built
        -- its derivation" from "we have never heard of it". They have different owners.
        'reason', CASE WHEN known THEN 'registered_metric_without_a_catalogued_derivation'
                       ELSE 'unknown_measure' END,
        'measure', m,
        -- Always null, and deliberately present. A caller that finds no `substitute` key might
        -- improvise one; a caller that finds it null has been answered.
        'substitute', NULL,
        'supported_derivations', to_jsonb(coalesce(near, '{}'::text[])),
        'note', 'This system does not derive ' || m || '. None of the supported derivations '
                || 'is a stand-in for it: a different measure may not be relabelled as this '
                || 'one, and a count of visits is not a duration whatever unit is attached to '
                || 'it. Record the gap (REQ-REC-003) rather than approximating it.');
END $fn$;

REVOKE ALL ON FUNCTION public.derivation_support(text) FROM anon;
GRANT EXECUTE ON FUNCTION public.derivation_support(text) TO authenticated;

COMMENT ON FUNCTION public.derivation_support(text) IS
 'REQ-REC-003/004, INTENT_COVERAGE R7. Returns the catalogued derivation for a measure, or an '
 'explicit refusal naming why it is unsupported. Never returns a substitute measure.';
