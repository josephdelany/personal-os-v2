-- 0012_grants_and_immutability.sql
-- RULE-02 enforcement (ADR-0010). Two layers:
--   1. GRANT level — revoke UPDATE/DELETE on the append-only tables from every
--      APP role (anon, authenticated, service_role). Supabase default-grants
--      these, so an explicit REVOKE is required.
--   2. TRIGGER level — a BEFORE UPDATE OR DELETE trigger that RAISEs, catching
--      even the table owner (postgres), whose implicit privileges cannot be
--      revoked. This is the "owner bypass" ADR-0010 names: grants stop app roles,
--      the trigger stops everyone.
--
-- NOTE ON THE RULE-02 CI QUERY (flagged for Joe, ADR-0010): the constitution's
-- literal RULE-02 query counts UPDATE/DELETE grants with no grantee filter. On
-- Postgres the OWNER always has implicit UPDATE/DELETE and it surfaces in
-- information_schema as a self-grant that cannot be revoked, so the literal query
-- returns >=2 no matter what. REQ-CAP-012 scopes immutability to "every role used
-- by the ingest endpoint, the resolution job and the PWA" — the APP roles, not the
-- migration/owner role. The CI check (tools/check_invariants.py) therefore scopes
-- to app roles; the owner is proven blocked by the trigger behavioural test. This
-- is a correction of the query to its stated purpose, not a weakening (RULE-00) —
-- it needs Joe's ratification and a constitution-text update.

-- ---- Layer 1: grants -------------------------------------------------------
-- Personal data: anon/authenticated get NO access to the spine — not even schema
-- USAGE (RLS is a second layer, not the only one).
REVOKE ALL ON ALL TABLES IN SCHEMA __CORE__ FROM anon, authenticated;
REVOKE USAGE ON SCHEMA __CORE__ FROM anon, authenticated;

-- service_role is the future ingest/ETL identity (ADR-0010): it may reach the
-- schema and read/append, but NOT mutate the append-only tables. Granting reach
-- is deliberate — it is what makes the RULE-02 probe test the *table* privilege
-- rather than being masked by a schema-level denial.
GRANT USAGE ON SCHEMA __CORE__ TO service_role;
GRANT USAGE ON SCHEMA __OPS__  TO service_role;
GRANT SELECT, INSERT ON __CORE__.atoms        TO service_role;
GRANT SELECT, INSERT ON __CORE__.raw_captures TO service_role;
-- Append-only tables: no UPDATE/DELETE for any app role (RULE-02 / REQ-CAP-012).
REVOKE UPDATE, DELETE ON __CORE__.atoms        FROM anon, authenticated, service_role;
REVOKE UPDATE, DELETE ON __CORE__.raw_captures FROM anon, authenticated, service_role;

-- ---- Layer 2: RLS -----------------------------------------------------------
-- Belt-and-suspenders. With RLS enabled and no policy, anon/authenticated (already
-- fully revoked above) are default-denied. The owner and service_role are governed
-- by the grants above, not by RLS (the owner bypasses RLS; no policies are defined
-- this phase). This layer is a second lock on anon/authenticated, not the primary
-- control — that is the grant revoke.
ALTER TABLE __CORE__.atoms              ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.raw_captures       ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.entities           ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.links              ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.metric_registry    ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.findings           ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.predictions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.prompt_dispatch    ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.hypothesis_register ENABLE ROW LEVEL SECURITY;

-- ---- Layer 3: mutation-rejecting trigger (ADR-0010) ------------------------
-- STATEMENT-level (not row-level) so it fires even against an EMPTY table — an
-- UPDATE/DELETE/TRUNCATE affecting zero rows still raises. This is deliberate: it
-- lets the invariant check prove the trigger BEHAVIOURALLY (as the owner, whose
-- grant cannot be revoked) without inserting a fabricated row (RULE-01). A
-- row-level trigger would never fire on an empty table and so could not be proven.
CREATE OR REPLACE FUNCTION __CORE__.reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
      'RULE-02: % on % is forbidden; the table is append-only. Corrections supersede, never edit.',
      TG_OP, TG_TABLE_NAME
      USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE TRIGGER atoms_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.atoms
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

CREATE TRIGGER raw_captures_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON __CORE__.raw_captures
    FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();

-- ---- Layer 4: system-set columns are forced at INSERT (ADR-0002, review B1) --
-- recorded_at is the transaction-time anchor and MUST be system-set, never
-- client-set. A DEFAULT is bypassable by naming the column in the INSERT, so a
-- BEFORE INSERT ROW trigger overwrites it unconditionally. Without this, the
-- service_role INSERT grant would let a caller backdate recorded_at and defeat
-- bitemporality / INV-4 with no UPDATE to catch it.
CREATE OR REPLACE FUNCTION __CORE__.force_recorded_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.recorded_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER atoms_force_recorded_at
    BEFORE INSERT ON __CORE__.atoms
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE TRIGGER raw_captures_force_recorded_at
    BEFORE INSERT ON __CORE__.raw_captures
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

-- ---- hypothesis_register: freeze the pre-registration columns (REQ-INF-103) --
CREATE OR REPLACE FUNCTION __CORE__.reject_prereg_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.exposure_metric        IS DISTINCT FROM OLD.exposure_metric
    OR NEW.outcome_metric         IS DISTINCT FROM OLD.outcome_metric
    OR NEW.lag_days               IS DISTINCT FROM OLD.lag_days
    OR NEW.direction              IS DISTINCT FROM OLD.direction
    OR NEW.transformation         IS DISTINCT FROM OLD.transformation
    OR NEW.adjustment_set         IS DISTINCT FROM OLD.adjustment_set
    OR NEW.test_statistic         IS DISTINCT FROM OLD.test_statistic
    OR NEW.preregistered_at       IS DISTINCT FROM OLD.preregistered_at
    OR NEW.confirmation_data_from IS DISTINCT FROM OLD.confirmation_data_from
    OR NEW.resolution_rule        IS DISTINCT FROM OLD.resolution_rule THEN
        RAISE EXCEPTION
          'REQ-INF-103: pre-registration columns are frozen after insert (only status may change).'
          USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER hypothesis_register_freeze
    BEFORE UPDATE ON __CORE__.hypothesis_register
    FOR EACH ROW EXECUTE FUNCTION __CORE__.reject_prereg_change();
