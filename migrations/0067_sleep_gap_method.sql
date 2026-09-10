-- 0067_sleep_gap_method.sql — the second registered method, and the first that reasons from
-- this system's OWN conclusions (REQ-REC-004..010, REQ-REC-016; ADR-0135).
--
-- WHY A SECOND METHOD AT ALL. REQ-REC-016 requires acceptance across MULTIPLE event families
-- before release, precisely so that a single worked example is not mistaken for a working
-- capability. With one registered method in one family, that requirement could not be executed;
-- it could only be asserted. A second family makes it a test.
--
-- WHAT IT CONCLUDES. That a night with no sleep record is EXPLAINED by a Watch non-wear episode
-- rather than unexplained. The event belongs to the family `data_coverage` and it is a fact
-- about THE RECORD, not about Joe. This distinction is the entire point of the method:
--
--   "no sleep record"        is not   "Joe did not sleep"
--   "explained by non-wear"  is not   "Joe slept"
--
-- The method says only which of the two kinds of gap this is. Missing is not zero, and an
-- explained gap is still missing — it is simply no longer mysterious, which is what stops an
-- analysis from treating the night as a zero or as an anomaly worth investigating.
--
-- WHY ITS INPUT IS AN INFERENCE. `watch_non_wear` is a conclusion, not a measurement, and this
-- method consumes it. That makes it the first place inferred-input propagation is real rather
-- than hypothetical: 0066 caps the tier of anything resting on a conclusion at DESCRIPTIVE, so
-- this method can never reach EXPLORATORY however many nights corroborate it. Two inferences
-- agreeing is not two independent sources; it is one method's opinion, twice.

INSERT INTO config.reconstruction_methods
    (method_key, method_version, event_family, required_evidence, permissible_outputs,
     temporal_specification, note)
VALUES (
    'sleep_gap_explained', 1, 'data_coverage',
    -- One measured input and one INFERRED input. The inferred one is what caps the tier.
    ARRAY['sleep_record_absent', 'watch_non_wear_inferred'],
    -- REQ-REC-006. It cannot establish that a gap is UNEXPLAINED — absence of a known cause is
    -- not evidence of no cause — so `did_not_occur` is absent here for the same reason it is
    -- absent from `watch_non_wear`.
    ARRAY['occurred'],
    'subject_day',
    'REQ-REC-004. Concludes that a night with no sleep record is explained by an inferred Watch '
    'non-wear episode on the same subject day. A fact about the RECORD: "no sleep record" is not '
    '"Joe did not sleep", and "explained" is not "Joe slept". The gap remains missing and is '
    'never a zero. Rests on a conclusion rather than a measurement, so REQ-REC-016 propagation '
    'caps it at DESCRIPTIVE however many nights agree.'
)
ON CONFLICT (method_key, method_version) DO NOTHING;
