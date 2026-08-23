-- 0013_review_fixes.sql
-- Forward-only corrections from the session-end adversarial review, applied while
-- the tables are still empty (cheapest window). Strengthens invariants only —
-- never weakens (RULE-00).

-- M1: `atoms_value_has_lane` guarded only value_point, so an interval estimate with
-- value_low/value_high set but value_point NULL (the RULE-08 nutrition leading case)
-- could be stored with NO estimate_method lane and NO state_class — exactly the
-- laneless value RULE-05 forbids. Re-key the constraint on ANY value column.
ALTER TABLE __CORE__.atoms DROP CONSTRAINT atoms_value_has_lane;
ALTER TABLE __CORE__.atoms ADD CONSTRAINT atoms_value_has_lane CHECK (
    (value_low IS NULL AND value_point IS NULL AND value_high IS NULL)
    OR (estimate_method IS NOT NULL AND state_class IS NOT NULL));

-- m8: the *_current views were plain (non-security_invoker) views owned by postgres.
-- If Phase 3 later grants an app role SELECT on atoms_current (the natural "current
-- beliefs" read path), a plain view executes with the owner's rights and would
-- bypass any RLS policy later added to the base table. security_invoker=true makes
-- the view run with the querying role's rights. Cheap to fix now, a footgun later.
CREATE OR REPLACE VIEW __CORE__.atoms_current WITH (security_invoker = true) AS
    SELECT a.* FROM __CORE__.atoms a
    WHERE NOT EXISTS (SELECT 1 FROM __CORE__.atoms s WHERE s.supersedes = a.id);

CREATE OR REPLACE VIEW __CORE__.entities_current WITH (security_invoker = true) AS
    SELECT e.* FROM __CORE__.entities e
    WHERE NOT EXISTS (SELECT 1 FROM __CORE__.entities s WHERE s.supersedes = e.id);

CREATE OR REPLACE VIEW __CORE__.links_current WITH (security_invoker = true) AS
    SELECT l.* FROM __CORE__.links l
    WHERE NOT EXISTS (SELECT 1 FROM __CORE__.links s WHERE s.supersedes = l.id);
