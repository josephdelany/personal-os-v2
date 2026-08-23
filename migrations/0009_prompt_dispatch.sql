-- 0009_prompt_dispatch.sql
-- SHAPE LOCKED. ADR-0017 (Decision 3): non-response is a row. One row per prompt
-- ISSUED, so a missingness mechanism can be classified (you cannot tell MCAR from
-- MNAR without the denominator of which prompts were issued).
--
-- This is a DIFFERENT AXIS from RULE-07 presence: presence is about the value of
-- a fact; response_state is about the lifecycle of a question. `never_scheduled`
-- is the ABSENCE of a row for a slot the schedule defines — derivable, no row.
-- Wired when prompts exist (Phase 3+).

CREATE TABLE __CORE__.prompt_dispatch (
    dispatch_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject         TEXT NOT NULL,               -- what the prompt is about (RULE-27: one per subject per day)
    scheduled_for   TIMESTAMPTZ NOT NULL,
    delivered_at    TIMESTAMPTZ,
    responded_at    TIMESTAMPTZ,
    response_state  TEXT NOT NULL DEFAULT 'pending'
                      CHECK (response_state IN
                        ('pending','answered','seen_declined','delivered_unseen','partial','expired')),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (delivered_at IS NULL OR delivered_at >= scheduled_for),
    CHECK (responded_at IS NULL OR delivered_at IS NOT NULL)
);

CREATE INDEX prompt_dispatch_subject_sched_idx ON __CORE__.prompt_dispatch (subject, scheduled_for);

COMMENT ON TABLE __CORE__.prompt_dispatch IS
  'ADR-0017: prompt lifecycle for joint missingness modelling. Distinct axis from '
  'RULE-07 presence. never_scheduled = absence of a row.';
