# ADR-0004: Entity and link table shape (resolution algorithm deferred)

## Status

Accepted for the **table shape only**. The resolution algorithm — blocking keys,
match thresholds, the review queue, the human-adjudication invariant — is Phase 4
and is deliberately **not** decided here. (This ADR was reserved for "entity
resolution"; this session authors only the shape, because Joe added `entities`/
`links` to the Phase-2 spine table list.)

## Date

2026-08-23

## Context

The Phase-2 spine needs `entities` (merchants, places, foods, people) and `links`
(edges among atoms and entities) as real tables. Two facts shaped this:

1. **No spec defines them.** The ontology spec is unwritten (OQ-16); the surviving
   specs are capture, finance, reasoning only. So creating these tables *is* a
   shape decision, and a decision not already specified must be an ADR (CLAUDE.md
   rule 5) — hence this one, rather than inventing a shape silently.
2. **`public.entities` already exists** (old cron stack, still running under
   OQ-17). The new tables therefore live in the dedicated `core` schema
   (ADR-0013), never touching the old one.

## Decision

Create `core.entities` and `core.links` with a conservative, bitemporal,
provenance-carrying shape:

- **`entities`**: `id`, `entity_type` (open TEXT pending the ontology spec),
  `canonical_name`, `attributes JSONB`, provenance (`extracted/inferred/defaulted/
  human`, `confidence`, `code_version`), transaction time (`recorded_at`, plus
  `supersedes`; currency **derived** from the supersedes graph via
  `entities_current`, **not** a stored `expired_at` — same INV-2 reasoning as
  ADR-0019's atoms correction), and **`corrected_by_human BOOLEAN`** — because
  RULE-10 says a human correction outranks every automated layer permanently, so a
  correction is a first-class superseding row, never an edit.
- **`links`**: a subject endpoint and an object endpoint, each exactly one of
  (atom, entity) enforced by CHECK; a `predicate`; provenance + bitemporal +
  `corrected_by_human`.

**Explicitly deferred to Phase 4:** how entities are *resolved* (blocking keys,
match thresholds, the review queue) and how links are *inferred*. This ADR fixes
the columns those algorithms will write to; it does not choose the algorithms.

## Consequences

**Good.** The spine is complete enough for Phase-3 capture to reference entities;
corrections have a home that honours RULE-10; the bitemporal shape matches atoms.

**Bad / flagged.** `entity_type` is open TEXT, not a closed taxonomy, because the
ontology spec that would close it is unwritten (OQ-16). A CHECK/enum is added when
that spec is authored — the same latent gap as `atoms.kind`. The resolution
algorithm's absence means these tables are shape-only until Phase 4; nothing
populates them before then.

## Alternatives considered

- **Defer `entities`/`links` entirely to Phase 4.** Rejected: Joe put them in the
  Phase-2 spine scope, and creating the shape now (non-retrofittable) while
  deferring the algorithm (retrofittable) is the right split.
- **A graph database.** Rejected (NON-GOALS): entity count ~80 fits one Postgres
  table; a graph DB is unjustified cost and complexity.
