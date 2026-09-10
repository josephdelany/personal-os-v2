-- 0064_watch_wear_method.sql — the first registered reconstruction method (REQ-REC-004..010;
-- ADR-0134). `config.reconstruction_methods` has existed since 0054 and has been EMPTY, which
-- meant the reconstruction engine could conclude nothing: the schema was deployed and the
-- capability was not.
--
-- WHY THIS METHOD FIRST. It runs on evidence that already exists in production — 33,355 atoms
-- across 25 metric keys — and it answers a question the system already knows it needs: the Watch
-- stopped in five stages ending 2026-08-21, and every metric that came from it went with it.
--
-- WHY THE EVENT IS "A NON-WEAR EPISODE OCCURRED" AND NOT "THE WATCH WAS WORN". The engine has
-- deliberately no code path from missing evidence to `did_not_occur` (REQ-REC-009): absence of a
-- record is never absence of the event, and that is the single most tempting error in the whole
-- feature. So the event this method reconstructs is the NON-WEAR ITSELF, and the evidence
-- SUPPORTS it having happened. The three-valued presence then falls out correctly rather than
-- being asserted.
--
-- WHY IT REQUIRES PHONE CAPTURE. A day with no Watch data and no phone data says nothing about
-- the Watch — capture as a whole was down, and the honest answer is `unknown`. A day with phone
-- data and no Watch data is different in kind: the pipeline demonstrably worked and the Watch
-- specifically produced nothing. Requiring `phone_capture_present` is what makes that
-- distinction structural instead of a comment, and REQ-REC-009 then returns `unknown` for the
-- first case without anybody writing a branch for it.
--
-- WHAT IT MAY NOT CONCLUDE. Nothing about Joe. A Watch that was not worn is a fact about a
-- device, and it is NOT evidence that he did not sleep, did not walk, or did not train. The
-- permissible_outputs list is the enforcement: this method may say a non-wear episode occurred,
-- or that it does not know. It has no vocabulary for anything else.

INSERT INTO config.reconstruction_methods
    (method_key, method_version, event_family, required_evidence, permissible_outputs,
     temporal_specification, note)
VALUES (
    'watch_non_wear', 1, 'device_state',
    -- Both, or the method does not run. The second is the one that makes the first informative.
    ARRAY['phone_capture_present', 'watch_capture_absent'],
    -- REQ-REC-006. `did_not_occur` is deliberately absent: this method has no way to establish
    -- that a non-wear episode did NOT happen, so it may not claim to.
    ARRAY['occurred'],
    'subject_day',
    'REQ-REC-004. Reconstructs a Watch non-wear episode for a subject day on which the phone '
    'captured and the Watch did not. It is a fact about a DEVICE and is never evidence about '
    'Joe: a Watch that was not worn does not mean he did not sleep, walk or train. A day on '
    'which neither source captured yields `unknown`, because capture as a whole was down and '
    'that says nothing about the Watch specifically.'
)
ON CONFLICT (method_key, method_version) DO NOTHING;

-- REQ-REC-013. The measure a downstream analysis reads to know an input is reconstructed rather
-- than measured. Registered here rather than in the catalogue rebuild because a derived measure
-- with no atoms yet is exactly the row `build_catalogue.py` cannot regenerate (ADR-0101).
INSERT INTO __CORE__.metric_registry
    (metric_key, display_name, family, unit, state_class, expected_cadence, max_staleness_days)
VALUES ('watch_non_wear_day', 'Watch non-wear day', 'device', 'boolean', 'measurement',
        'daily', 2)
ON CONFLICT (metric_key) DO NOTHING;
