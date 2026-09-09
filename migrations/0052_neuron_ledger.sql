-- 0052_neuron_ledger.sql — M3: the shared model-call budget (REQ-CAP-035..042; ADR-0063).
--
-- WHY ONE LEDGER. Three consumers will call Cloudflare Workers AI: the Ask planner (B11.2),
-- nutrition resolution (B12) and media transcription (B16). Each was specified separately and
-- each would naturally count its own usage. Three counters against one shared 10,000-neuron
-- daily allowance means none of them knows the real total, and the budget is enforced by
-- whichever happens to run last. One ledger, one sum, one gate.
--
-- WHY THE HARD CAP IS THE $0 MECHANISM. RULE-28 disqualifies a service that bills on overage
-- instead of failing. Workers AI hard-fails at 10,000 neurons/day, and REQ-CAP-042 forbids
-- attaching a payment method — so the enforcement is the vendor's refusal, not our restraint.
-- This table exists so the system stops at 9,000 rather than discovering the ceiling.
--
-- WHY 9,000 AND NOT 10,000. REQ-CAP-039 reserves the 1,000-neuron margin exclusively for
-- re-processing captures deferred on a previous day. Without the reservation a busy day
-- starves yesterday's backlog forever: new work always arrives first and always wins.

CREATE TABLE IF NOT EXISTS __CORE__.neuron_ledger (
    ledger_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capture_id         UUID REFERENCES __CORE__.raw_captures(capture_id),  -- null for a non-capture call
    model_id           TEXT NOT NULL,
    call_kind          TEXT NOT NULL CHECK (call_kind IN
                         ('transcribe','extract','plan','nutrition','verify')),
    estimated_neurons  NUMERIC NOT NULL CHECK (estimated_neurons >= 0),
    -- The reservation lane (REQ-CAP-039). A call re-processing a deferred capture may spend
    -- the 9,000-10,000 margin; a newly arrived one may not.
    is_deferred_retry  BOOLEAN NOT NULL DEFAULT false,
    called_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Recorded BEFORE the response is known, then updated to the observed outcome. A row
    -- exists for a call that failed or timed out, because a call that cost neurons and
    -- returned nothing still spent them.
    outcome            TEXT NOT NULL DEFAULT 'issued'
                         CHECK (outcome IN ('issued','ok','error','refused_budget')),
    egress_id          UUID REFERENCES __OPS__.egress_log(egress_id),
    detail             JSONB
);

-- The gate reads today's sum by UTC day (REQ-CAP-037: "the current UTC day"), so the index
-- matches the query rather than the local calendar.
CREATE INDEX IF NOT EXISTS neuron_ledger_utc_day_idx
    ON __CORE__.neuron_ledger (((called_at AT TIME ZONE 'UTC')::date), call_kind);
CREATE INDEX IF NOT EXISTS neuron_ledger_capture_idx
    ON __CORE__.neuron_ledger (capture_id) WHERE capture_id IS NOT NULL;

COMMENT ON TABLE __CORE__.neuron_ledger IS
  'REQ-CAP-035. One row per Workers AI call, across every consumer. The shared daily sum '
  'is what REQ-CAP-037 gates on; a per-consumer counter cannot see the real total.';
COMMENT ON COLUMN __CORE__.neuron_ledger.is_deferred_retry IS
  'REQ-CAP-039: only a re-processing call may spend the 9,000-10,000 reserved margin.';
COMMENT ON COLUMN __CORE__.neuron_ledger.outcome IS
  'A row is written before the call and updated after. An errored call still spent neurons; '
  'writing the row only on success would make the budget under-count exactly when it matters.';

-- The gate itself lives in SQL so every consumer asks the same question of the same numbers
-- (RULE-12). Returns the spend so far, the ceiling that applies to this call, and whether it
-- may proceed.
CREATE OR REPLACE FUNCTION __CORE__.neuron_budget(p_estimated numeric, p_deferred_retry boolean DEFAULT false)
RETURNS TABLE (spent_today numeric, ceiling numeric, allowed boolean, reason text)
LANGUAGE plpgsql STABLE SET search_path = '' AS $fn$
DECLARE s numeric; c numeric;
BEGIN
    SELECT coalesce(sum(n.estimated_neurons), 0) INTO s
      FROM __CORE__.neuron_ledger n
     WHERE (n.called_at AT TIME ZONE 'UTC')::date = (now() AT TIME ZONE 'UTC')::date
       AND n.outcome <> 'refused_budget';        -- a refused call spent nothing
    -- REQ-CAP-037 gates new work at 9,000; REQ-CAP-039 lets a deferred retry reach 10,000.
    c := CASE WHEN p_deferred_retry THEN 10000 ELSE 9000 END;
    RETURN QUERY SELECT s, c, (s + p_estimated) <= c,
        CASE WHEN (s + p_estimated) <= c THEN NULL
             WHEN p_deferred_retry THEN 'hard_cap_reached'
             ELSE 'soft_ceiling_reached' END;
END $fn$;

COMMENT ON FUNCTION __CORE__.neuron_budget(numeric, boolean) IS
  'REQ-CAP-037/038/039. One gate, one sum, for every consumer. New work stops at 9,000; the '
  'reserved margin to 10,000 is only for re-processing deferred captures.';
