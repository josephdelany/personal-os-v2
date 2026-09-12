-- 0074_the_alias_bridge_is_gone.sql — remove the bridge rows and make them unwritable again
-- (REQ-NUT-002, REQ-NUT-004, REQ-NUT-008; completes 0071).
--
-- THE SEQUENCE THIS COMPLETES, AND WHY IT WAS THREE STEPS RATHER THAN ONE.
--
--   0071   CREATE food_aliases, backfill from the bridge rows.        additive; nothing breaks
--   ----   the resolver reads and writes food_aliases instead.        nutrition worker, 6897583
--   0074   DELETE the bridge rows, and forbid new ones.               this file
--
-- Doing the delete in 0071 would have removed rows the resolver was still reading, breaking
-- lookup between two migrations. Doing it without the CHECK would have been worse than doing
-- nothing: a delete alone lets the very next resolution recreate a bridge row, so the tree
-- would look clean and drift straight back.
--
-- WHY THE BRIDGE WAS A DEFECT RATHER THAN AN INELEGANCE. An alias used to be written as a
-- SECOND `foods_cache` row carrying `raw->>'alias_of'`. It worked. But REQ-NUT-008 requires
-- re-fetching a Branded or Open Food Facts entry when `fetched_at` passes 365 days, and a
-- re-fetch would have had to update BOTH rows or let one silently disagree with the other —
-- one fact, two rows, one of them stale. The nutrition worker reported it as "a defect waiting
-- to happen" rather than leaving it to be found by a wrong number a year from now.
--
-- SAFETY OF THE DELETE, checked rather than assumed:
--
--   * Production `core.foods_cache` holds ZERO rows at this revision, so this is a no-op there.
--   * 0071's backfill points every new `food_aliases` row at the CANONICAL row's `food_id`
--     (`c.food_id` in its INSERT), never at the bridge row's. So the ON DELETE CASCADE on
--     `food_aliases.food_id` cannot take a real alias with it when the bridge rows go.
--   * No code path writes `alias_of` any more — verified across the tree, not asserted:
--     `remember_alias` inserts into `food_aliases` and `lookup_cached` reads it.
--
-- The CHECK is `NOT VALID`-free on purpose: the table is empty of offenders by the statement
-- above it, so a full validation is instant and a constraint that has never been validated is
-- a constraint nobody can rely on.

DELETE FROM __CORE__.foods_cache WHERE raw ? 'alias_of';

ALTER TABLE __CORE__.foods_cache
    ADD CONSTRAINT foods_cache_is_not_an_alias_bridge
    CHECK (raw IS NULL OR NOT (raw ? 'alias_of'));

COMMENT ON CONSTRAINT foods_cache_is_not_an_alias_bridge ON __CORE__.foods_cache IS
    'REQ-NUT-004. An alias belongs in core.food_aliases, which is what REQ-NUT-001 step (1) '
    'searches and what REQ-NUT-002 follows to the nutrients. A second foods_cache row standing '
    'in for an alias made one fact into two rows, and REQ-NUT-008''s 365-day re-fetch would '
    'have updated one of them. Enforced in the schema because the resolver is not the only '
    'possible writer.';
