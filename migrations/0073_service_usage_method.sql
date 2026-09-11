-- 0073_service_usage_method.sql — the fourth registered method: did Joe USE the thing he keeps
-- paying for? (REQ-FIN-110..116, REQ-REC-004/005/009/013; INTENT_COVERAGE R4; ADR-0140)
--
-- WHAT R4 ASKS FOR, AND THE ONE SENTENCE IT TURNS ON. A recurring charge plus activity evidence,
-- with a logging outage in the middle: *"used/unused/unknown follows the finance rules; an
-- OUTAGE IS NOT PROOF OF NONUSE."*
--
-- THE DEFECT THIS CLOSES WAS LIVE IN THE ENGINE. `tools/engines/usage_status.from_evidence`
-- returned 'unused' whenever the newest usage evidence was older than `unused_after_days`, with
-- no concept of whether anything had been watching in the meantime. Stale evidence has two
-- entirely different causes and it read them identically:
--
--     the source kept capturing and recorded no visit    -> 'unused' is supported
--     the source stopped capturing                       -> nothing was watching; 'unknown'
--
-- That is not a hypothetical in this system. The Watch stopped in five stages ending
-- 2026-08-21 and the bank CSV export died 2026-05-13, so the largest silences on record are its
-- own instruments failing. Reading those as 'unused' accuses Joe of not going to the gym on the
-- strength of a broken logger, which is precisely what REQ-FIN-112's banned vocabulary exists to
-- prevent and what REQ-REC-009 forbids: absence of a record is absence of capture.
--
-- HOW THE OUTAGE IS ENFORCED STRUCTURALLY RATHER THAN BY DISCIPLINE. `usage_observation_window`
-- is REQUIRED EVIDENCE. The gatherer emits it only when the usage source produced something
-- after the last recorded use — that is, only when there WAS a window in which a visit could
-- have been seen. When the source is dead the citation is simply absent, and the engine's
-- existing REQ-REC-009 path returns `unknown` with the missing input named. There is no branch
-- anywhere that can turn a dead sensor into a conclusion, because the conclusion depends on a
-- citation a dead sensor cannot produce.
--
-- PERMISSIBLE OUTPUTS IS `occurred` ALONE, AND 'unused' IS DELIBERATELY NOT AN EVENT. A stored
-- inferred event asserts that something happened. "Joe did not use his gym membership" is not an
-- event, it is the absence of a class of events over a window, and `core.inferred_events` is the
-- wrong shape for it -- storing one row per un-used service per window would fill the table with
-- rows asserting nothing, the same mistake `watch_non_wear` made with 404 `unknown` days.
-- The three-tier used/unused/unknown status REQ-FIN-110 requires is computed and displayed by
-- `tools/service_usage.py`; only a positive usage event is stored here.
INSERT INTO config.reconstruction_methods
    (method_key, method_version, event_family, required_evidence, permissible_outputs,
     temporal_specification, note)
VALUES (
    'service_usage', 1, 'service_usage',
    -- Three inputs, and the middle one is the whole point.
    ARRAY['recurring_charge_stream', 'usage_observation_window', 'usage_evidence'],
    ARRAY['occurred'],
    'subject_day',
    'REQ-REC-004/005/009, REQ-FIN-110..116. Concludes that a recurring service was USED on a '
    'subject day. `usage_observation_window` is required and is emitted only when the usage '
    'source produced something after the last recorded use, so a logging outage removes a '
    'required input and the engine returns unknown with that input named -- an outage can never '
    'become evidence of nonuse (INTENT_COVERAGE R4). It may not conclude did_not_occur: nonuse '
    'is the absence of a class of events over a window, not an event, and it is reported as a '
    'REQ-FIN-110 tier by tools/service_usage.py rather than stored here.'
)
ON CONFLICT (method_key, method_version) DO NOTHING;
