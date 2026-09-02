-- 0027_candidate_status.sql — hypothesis_register learns CANDIDATE (ADR-0039)
--
-- REQ-INF-401 and REQ-TIER-053 REQUIRE generator/scan output to live in
-- hypothesis_register as status='CANDIDATE' (the EXPLORATORY surface's sole
-- source). The built CHECK (0010) predates those requirements and lists only the
-- promoted-and-above states — so this WIDENS the status set to what the spec
-- demands. Not a RULE-00 weakening: no gate/threshold moves; a spec-required
-- member is added, by recorded decision (ADR-0039). The freeze trigger (0012)
-- still rejects any UPDATE to the pre-registration columns; CANDIDATE rows use
-- preregistered_at/confirmation_data_from as scan-run metadata until a real
-- Watch converts them (a NEW row with preregistered_at=now(), per ADR-0038 —
-- CANDIDATE rows are never mutated into registrations).

ALTER TABLE __CORE__.hypothesis_register
    DROP CONSTRAINT hypothesis_register_status_check;
ALTER TABLE __CORE__.hypothesis_register
    ADD CONSTRAINT hypothesis_register_status_check
    CHECK (status IN ('CANDIDATE','PROMOTED','CONFIRMED_OBSERVATIONAL',
                      'EXPERIMENTAL','REFUTED','INSUFFICIENT'));

COMMENT ON CONSTRAINT hypothesis_register_status_check
    ON __CORE__.hypothesis_register IS
  'ADR-0039: CANDIDATE added per REQ-INF-401/REQ-TIER-053 (scan/generator output '
  'lives here; the EXPLORATORY surface renders only this status).';
