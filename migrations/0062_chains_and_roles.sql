-- 0062_chains_and_roles.sql — chains across lenses and the lever/context distinction
-- (REQ-INF-560..565, REQ-TIER-046; ADR-0102). The arithmetic is in tools/engines/chains.py;
-- this is where the graph is STORED and where the one distinction the graph must not invent
-- is DECLARED.
--
-- WHY `role` LIVES IN THE REGISTRY AND NOT IN THE CHAIN. REQ-INF-565 forbids auto-promoting a
-- `context` metric to `lever` on the basis of a discovered association. If the chain engine
-- decided what was actionable, that rule would be enforced by the very code with an incentive
-- to break it: a chain starting at something Joe can change is a more interesting chain. So
-- the distinction is DATA in `metric_registry`, written by a human, and the engine reads it.
--
-- The default is 'context'. The safe answer to "may Joe act on this?" is no, and a metric
-- nobody has classified is exactly the case where nobody has thought about it. Defaulting to
-- 'lever' would make every new metric actionable the moment it appeared.

ALTER TABLE __CORE__.metric_registry
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'context'
        CHECK (role IN ('lever', 'context'));

COMMENT ON COLUMN __CORE__.metric_registry.role IS
  'REQ-INF-565. `lever` is something Joe can decide to change; `context` is something that '
  'merely covaries — the weather, the day of the week, a resting heart rate. Discovering an '
  'association involving a context metric is NOT a licence to reclassify it, and no engine '
  'may write this column. Defaults to `context`: the safe answer to "may Joe act on this?" '
  'is no, and an unclassified metric is precisely one nobody has considered.';

-- PostgreSQL forbids a subquery inside a CHECK, and both of the invariants below are
-- statements about the CONTENTS of an array. They are expressed as IMMUTABLE functions
-- instead, which a CHECK may call. Immutable is honest here: both depend only on their
-- argument, read no table and no setting.
CREATE OR REPLACE FUNCTION analysis.f_all_distinct(p_items text[])
RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT cardinality(p_items) = (SELECT count(DISTINCT x) FROM unnest(p_items) AS x)
$$;

-- RULE-16's ladder, weakest first. Kept in ONE place: the engine has the same order in Python
-- and the two would drift if this were written inline at each use.
CREATE OR REPLACE FUNCTION analysis.f_tier_rank(p_tier text)
RETURNS int LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT array_position(ARRAY['INSUFFICIENT','DESCRIPTIVE','CANDIDATE','PROMOTED',
                              'CONFIRMED_OBSERVATIONAL','EXPERIMENTAL'], p_tier)
$$;

CREATE OR REPLACE FUNCTION analysis.f_weakest_tier(p_tiers text[])
RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT t FROM unnest(p_tiers) AS t ORDER BY analysis.f_tier_rank(t) LIMIT 1
$$;

-- REQ-INF-563. The pruned map. Storing the PRUNED set rather than the full graph is the point:
-- an unrendered edge is not evidence anybody weighed, and keeping the unpruned graph alongside
-- would invite a later surface to read it "just for context" and undo the pruning.
CREATE TABLE IF NOT EXISTS analysis.chains (
    chain_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    as_of              DATE NOT NULL,
    path               TEXT[] NOT NULL,          -- metric keys, head first
    hypothesis_ids     TEXT[] NOT NULL,          -- one per edge, same order as `path` pairs
    tiers              TEXT[] NOT NULL,          -- one per edge
    chain_tier         TEXT NOT NULL
                         CHECK (chain_tier IN ('DESCRIPTIVE','CANDIDATE','PROMOTED',
                                               'CONFIRMED_OBSERVATIONAL','EXPERIMENTAL',
                                               'INSUFFICIENT')),
    attenuated_effect  NUMERIC NOT NULL,
    rank_score         NUMERIC NOT NULL,
    actionable         BOOLEAN NOT NULL,
    what_would_firm_it_up TEXT NOT NULL,
    code_version       TEXT NOT NULL,
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- REQ-INF-561: a node appears at most once per path, enforced here as well as in the
    -- engine. A cycle that reached storage would compose an effect with itself and report the
    -- square of a correlation as a discovery, and the engine is not the only possible writer.
    CONSTRAINT path_has_no_repeated_node CHECK (analysis.f_all_distinct(path)),
    -- A path of k nodes has exactly k-1 edges. Without this, `tiers` and `path` could drift
    -- and REQ-TIER-046's "tier of the weakest edge" would be computed over the wrong set.
    CONSTRAINT one_edge_between_each_pair
        CHECK (cardinality(hypothesis_ids) = cardinality(path) - 1
               AND cardinality(tiers) = cardinality(path) - 1),
    -- REQ-INF-560/562: a chain is at least two edges. One edge is the hypothesis itself, and
    -- `get_findings` already surfaces it; storing it again double-counts one piece of evidence.
    CONSTRAINT a_chain_is_at_least_two_edges CHECK (cardinality(path) >= 3),
    -- REQ-TIER-046: the stored tier must actually BE the weakest of the stored edge tiers.
    -- Computing it correctly in Python and storing something else is a defect this table can
    -- refuse, so it does.
    CONSTRAINT chain_tier_is_the_weakest_edge
        CHECK (analysis.f_weakest_tier(tiers) = chain_tier)
);

CREATE INDEX IF NOT EXISTS chains_as_of_rank ON analysis.chains (as_of, rank_score DESC);

COMMENT ON TABLE analysis.chains IS
  'REQ-INF-560..565, REQ-TIER-046. The PRUNED cross-lens map. `attenuated_effect` is the '
  'multiplicative composition — two edges of 0.3 compose to ~0.09 — and it is the only '
  'magnitude a chain may report, because stating the first edge''s strength at the end of a '
  'chain invites the reader to carry it all the way through. `chain_tier` is the weakest '
  'edge''s tier, enforced by CHECK: a chain is a conjunction, and one CONFIRMED link must '
  'never launder two guesses.';

REVOKE ALL ON analysis.chains FROM anon, authenticated;
