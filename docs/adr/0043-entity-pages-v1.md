# ADR-0043: Entity pages in v1 are keyed by (type, key) over the legacy tables

## Status
Accepted

## Date
2026-09-02

## Decision
`public.get_entity(p_type, p_key)` (migration 0037) renders the SOURCES module-8
tap-through — a merchant, a category, a site, a channel, an exercise — as first seen,
last seen, how often, how much, when in the week and day, and the twenty most recent
rows. **In v1 an entity is `(type, key)` derived from `public.transactions`,
`public.events` and `core.atoms_current`, not a `core.entities` id**: `core.entities`
is shape-only (ADR-0004) and entity resolution is Phase 4. When resolution ships,
`get_entity` gains an `entity_id` field; nothing here is renamed (README rule 7).
`place` **delegates to `get_place` (B5) and returns the REQ-ASK-003 refusal string
with a note until B5 is live.** An unknown type returns the refusal plus the six
tracked types. An unknown key returns `n: 0` with a note and nothing else
(REQ-INF-505). Every recent row carries `src` + `row_id`, and the page carries one
`trace` naming its table and key (REQ-ASK-011). Nothing after `as_of` is counted
(REQ-INF-109).

The exercise key is `evidence_span`, the same expression B2's module 8 uses
(ADR-0041 (c)); each per-attribute atom of a set repeats it, so the exercise page's
`n` counts atoms (three per set) — co-occurrence and per-set grouping are not built.

## Not built in v1
- No `core.entities` linkage (Phase 4).
- `place` deferred to B5.
- Co-occurrence (what else happens on this entity's days) not built.
- Merchant keys are the raw bank strings; no normalisation (a merchant that appears
  under two spellings is two entities until resolution).
