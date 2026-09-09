-- 0055_get_reconstruction.sql — B14R step 5: the registered lineage interface for a
-- reconstructed event (REQ-REC-014, REQ-REC-007, REQ-REC-008, REQ-REC-010..013).
--
-- Depends on 0054 (core.inferred_events) and mirrors public.get_computation from 0049: the
-- same owner check, the same SECURITY DEFINER with an empty search_path, the same shape of
-- contract. A reconstruction is provenance, so it is read the way provenance is read.
--
-- WHY THIS IS NOT JUST `SELECT * FROM inferred_events`. Four things are true of the row that
-- are not visible in it:
--   1. Independent support is DISTINCT ORIGIN GROUPS, not the number of evidence rows
--      (REQ-REC-008). The raw row cannot tell you a receipt was copied twice.
--   2. Contradicting evidence must arrive with the supporting kind, in the same object, or a
--      caller that forgets to ask for it renders a one-sided story (REQ-REC-007).
--   3. Uncertainty must be labelled UNQUANTIFIED when there is no calibration, rather than
--      handing out a bare `rule_score` a caller could format as a percentage (REQ-REC-010).
--   4. A superseded interpretation must announce that it is superseded, and by what, or a
--      cached event_id keeps answering after Joe corrected it (REQ-REC-011).
--
-- RULE-15: no model is involved. This function is the deterministic answer.

CREATE OR REPLACE FUNCTION public.get_reconstruction(p_event_id uuid)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE e record; result jsonb; ev jsonb; ind record; history jsonb; superseded_by uuid;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;

    SELECT * INTO e FROM __CORE__.inferred_events WHERE event_id = p_event_id;
    IF e.event_id IS NULL THEN
        RETURN jsonb_build_object('event_id', p_event_id, 'found', false);
    END IF;

    -- REQ-REC-008. Rows AND origins, both named, so a caller cannot mistake one for the
    -- other. Two copies of one receipt are two rows and one origin.
    SELECT * INTO ind FROM __CORE__.v_event_independence WHERE event_id = p_event_id;

    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'ref', coalesce(x.atom_id::text, x.external_ref),
               'stance', x.stance, 'origin_group', x.origin_group,
               'recorded_at', x.recorded_at, 'note', x.note)
             ORDER BY x.stance, x.origin_group), '[]'::jsonb)
      INTO ev FROM __CORE__.event_evidence x WHERE x.event_id = p_event_id;

    -- REQ-REC-011/012. The revision chain, oldest first, so "what did the system say then"
    -- is answerable and a human correction is visibly a human correction.
    WITH RECURSIVE chain AS (
        SELECT i.event_id, i.supersedes, i.author, i.knowledge_time, i.tier, i.presence, 0 AS depth
          FROM __CORE__.inferred_events i WHERE i.event_id = p_event_id
        UNION ALL
        SELECT p.event_id, p.supersedes, p.author, p.knowledge_time, p.tier, p.presence, c.depth + 1
          FROM __CORE__.inferred_events p JOIN chain c ON p.event_id = c.supersedes
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'event_id', c.event_id, 'author', c.author, 'knowledge_time', c.knowledge_time,
               'tier', c.tier, 'presence', c.presence) ORDER BY c.depth DESC), '[]'::jsonb)
      INTO history FROM chain c;

    SELECT s.event_id INTO superseded_by
      FROM __CORE__.inferred_events s WHERE s.supersedes = p_event_id LIMIT 1;

    result := jsonb_build_object(
        'event_id', e.event_id, 'found', true,
        'event_family', e.event_family,
        'method', jsonb_build_object('key', e.method_key, 'version', e.method_version),
        -- Two clocks, never merged (RULE-04, INV-4).
        'event_time', jsonb_build_array(e.event_time_from, e.event_time_to),
        'subject_day', e.subject_day, 'knowledge_time', e.knowledge_time,
        'tier', e.tier, 'presence', e.presence,
        'evidence', ev,
        'support', jsonb_build_object(
            'rows', coalesce(ind.supporting_rows, 0),
            'independent_origins', coalesce(ind.independent_support, 0)),
        'contradiction', jsonb_build_object(
            'rows', coalesce(ind.contradicting_rows, 0),
            'independent_origins', coalesce(ind.independent_contradiction, 0)),
        'alternatives', e.alternatives,
        'no_alternative_generator', e.no_alternative_generator,
        'unresolved_ambiguity', e.unresolved_ambiguity,
        -- REQ-REC-010. The uncertainty says what KIND it is. A bare rule_score handed to a
        -- caller is a number that will eventually be rendered with a percent sign.
        'uncertainty', CASE
            WHEN e.probability IS NOT NULL THEN jsonb_build_object(
                'kind', 'calibrated_probability', 'probability', e.probability,
                'calibration_ref', e.calibration_ref)
            WHEN e.rule_score IS NOT NULL THEN jsonb_build_object(
                'kind', 'unquantified', 'rule_score', e.rule_score,
                'note', 'an uncalibrated ranking, not a probability; it orders '
                        'reconstructions against each other and states no chance of anything')
            ELSE jsonb_build_object('kind', 'unquantified',
                'note', 'no score applies to this reconstruction') END,
        'superseded_by', superseded_by,
        'is_current', (superseded_by IS NULL),
        'revision_history', history,
        'deterministic', true);
    RETURN result;
END $fn$;
REVOKE ALL ON FUNCTION public.get_reconstruction(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_reconstruction(uuid) TO authenticated;
