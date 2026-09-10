-- 0069_discriminating_evidence.sql — what would settle it is part of the answer
-- (REQ-REC-015; INTENT_COVERAGE R8; ADR-0135).
--
-- THE GAP. `tools/engines/reconstruct.py` has computed `discriminating_evidence` since B14R and
-- there has never been a column to put it in. `evaluate` returned it, `to_row` dropped it, and
-- `get_reconstruction` could not show it. REQ-REC-015 requires the backend to return the missing
-- evidence that would distinguish competing interpretations, OR to state explicitly that none has
-- been identified — and the second half is the part that keeps the first honest.
--
-- WHY AN EXPLICIT FLAG RATHER THAN AN EMPTY ARRAY. An empty array is ambiguous: it means either
-- "nothing would settle this" or "nobody looked". Those are different answers and only one of
-- them is a finding. The same shape is already used for `no_alternative_generator` in 0054, for
-- the same reason, and using it twice makes the rule legible rather than local.
--
-- WHY IT MATTERS THAT THIS IS STORED AND NOT COMPUTED AT READ TIME. The evidence that would have
-- settled a question is a fact about WHAT WAS KNOWN THEN. Recomputing it later against today's
-- data would answer a different question — and would quietly make past uncertainty look
-- resolvable in hindsight, which is the INV-4 failure wearing a different hat.

ALTER TABLE __CORE__.inferred_events
    ADD COLUMN IF NOT EXISTS discriminating_evidence text[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS no_discriminating_evidence boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN __CORE__.inferred_events.discriminating_evidence IS
    'REQ-REC-015. Observations that would distinguish the recorded alternatives. Empty with '
    'no_discriminating_evidence = true means none was identified — which is an answer, not a gap.';

-- REQ-REC-015. Silence about what would settle it is not permitted, exactly as silence about
-- alternatives is not permitted (0054). A row carrying alternatives must say either what would
-- distinguish them or that nothing identified would.
ALTER TABLE __CORE__.inferred_events
    ADD CONSTRAINT discrimination_is_addressed
    CHECK (jsonb_array_length(alternatives) = 0
           OR cardinality(discriminating_evidence) > 0
           OR no_discriminating_evidence);

-- get_reconstruction, replaced to surface the two new fields. It is re-created HERE rather than
-- edited in 0055 because 0055 runs before this column exists; editing it would break the chain
-- from empty, which is the one property that makes these files trustworthy.
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
        -- REQ-REC-015. What would settle it is part of the answer. The flag is what keeps the
        -- array honest: an empty list alone cannot distinguish "nothing would resolve this"
        -- from "nobody looked", and only one of those is a finding.
        'discriminating_evidence', to_jsonb(e.discriminating_evidence),
        'no_discriminating_evidence', e.no_discriminating_evidence,
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
