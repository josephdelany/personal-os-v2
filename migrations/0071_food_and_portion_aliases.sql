-- 0071_food_and_portion_aliases.sql — the two alias tables the requirements name by name
-- (REQ-NUT-001 step 1, REQ-NUT-002, REQ-NUT-004, REQ-NUT-018). Requested by the nutrition
-- worker's handoff §3a/§3b; DDL is theirs, the numbers are allocated here.
--
-- WHY THIS IS NOT MERELY A MISSING TABLE. `food_aliases` is not an implementation detail the
-- resolver may satisfy any way it likes. The requirements name it three times and give it a
-- specific job:
--
--   REQ-NUT-001  resolution order step (1) is a `food_aliases` exact match
--   REQ-NUT-002  on that match, read nutrients from `foods_cache` AND ISSUE NO NETWORK REQUEST
--   REQ-NUT-004  on any network resolution, insert a `food_aliases` row mapping the spoken
--                phrase AS UTTERED to the resolved canonical_name
--
-- REQ-NUT-002 only makes sense if the alias and the nutrients are two different rows in two
-- different tables: it says to follow the alias TO the cache. Neither table existed, so the
-- resolver wrote an alias as a SECOND `foods_cache` row carrying `raw->>'alias_of'`. That
-- works, it is tested, and the worker flagged it as a defect waiting to happen rather than
-- leaving it to be found later: REQ-NUT-008 requires re-fetching a stale Branded or OFF entry
-- after 365 days, and a re-fetch would have to update both rows or silently disagree with
-- itself. One fact, two rows, one of them updated.
--
-- THE PHRASE AS UTTERED IS KEPT SEPARATELY FROM THE MATCHING KEY. REQ-NUT-004 says "as
-- uttered", and a lowercased matching key is not that. `alias` is what lookup compares;
-- `verbatim` is what Joe actually said. Storing only the folded form would quietly destroy the
-- evidence that a correction is a correction of something.

-- REQ-NUT-002 / REQ-NUT-004.
CREATE TABLE IF NOT EXISTS __CORE__.food_aliases (
    alias_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alias      TEXT NOT NULL,                       -- lowercased; the matching key
    verbatim   TEXT NOT NULL,                       -- the phrase AS UTTERED, unnormalised
    food_id    UUID NOT NULL REFERENCES __CORE__.foods_cache(food_id) ON DELETE CASCADE,
    source     TEXT NOT NULL
               CHECK (source IN ('usda_branded','usda_foundation','off_product','joe')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (alias, food_id)
);
CREATE INDEX IF NOT EXISTS food_aliases_alias_idx ON __CORE__.food_aliases (alias);

COMMENT ON TABLE __CORE__.food_aliases IS
    'REQ-NUT-001 step (1), REQ-NUT-002, REQ-NUT-004. Maps a spoken phrase to a cached food. A '
    'hit here must serve nutrients from foods_cache WITHOUT a network request. `alias` is the '
    'lowercased matching key; `verbatim` is the phrase as uttered, which REQ-NUT-004 requires '
    'and a folded key destroys.';

-- The mechanical backfill from the bridge rows. A no-op against production, where
-- `core.foods_cache` holds 0 rows at this revision (checked, not assumed); it is here so that
-- any environment which DID resolve a food keeps its aliases across the change.
--
-- THE BRIDGE ROWS ARE NOT DELETED HERE, AND THAT IS SEQUENCING, NOT TIMIDITY. The resolver
-- still reads them. Deleting them before the read path moves would break lookup between two
-- migrations. The order is: this migration (additive, nothing breaks) -> the resolver reads
-- `food_aliases` (nutrition worker owns that code) -> a later migration removes the bridge rows
-- and adds a CHECK so `foods_cache` can never carry `alias_of` again. Until then the bridge row
-- remains a valid cache row; it is redundant, not wrong.
INSERT INTO __CORE__.food_aliases (alias, verbatim, food_id, source)
SELECT lower(a.canonical_name),
       COALESCE(a.raw->>'phrase_as_uttered', a.canonical_name),
       c.food_id, a.source
  FROM __CORE__.foods_cache a
  JOIN __CORE__.foods_cache c
    ON c.canonical_name = a.raw->>'alias_of'
   AND c.source = a.source
   AND c.source_id IS NOT DISTINCT FROM a.source_id
 WHERE a.raw ? 'alias_of'
ON CONFLICT DO NOTHING;

-- REQ-NUT-018. Named by the requirement, present in no migration until now.
--
-- `core.portions` (0050) is a DIFFERENT THING and is deliberately left alone: it keys on
-- `canonical_name` — one portion per named food — while REQ-NUT-018 keys on
-- `(food_class, phrase)`, so that "a handful" resolves differently for nuts than for crisps.
-- It also has no `n_corrections`. Folding one into the other would silently change what a
-- stored portion means, which is the ADR-0089 mistake.
CREATE TABLE IF NOT EXISTS __CORE__.portion_aliases (
    food_class    TEXT NOT NULL,
    phrase        TEXT NOT NULL,
    grams         NUMERIC NOT NULL CHECK (grams > 0),
    n_corrections INTEGER NOT NULL DEFAULT 0 CHECK (n_corrections >= 0),
    source        TEXT NOT NULL DEFAULT 'joe' CHECK (source IN ('joe','portion_table')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (food_class, phrase)
);

COMMENT ON TABLE __CORE__.portion_aliases IS
    'REQ-NUT-018. Keyed on (food_class, phrase) so a vernacular portion can differ by food '
    'class. Distinct from core.portions (0050), which keys on canonical_name and carries no '
    'correction count. n_corrections is how often Joe has corrected this phrase; RULE-10 makes '
    'his correction permanent.';

REVOKE ALL ON __CORE__.food_aliases, __CORE__.portion_aliases FROM anon, authenticated;
