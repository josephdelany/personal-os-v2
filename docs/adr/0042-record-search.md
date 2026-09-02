# ADR-0042: Record search is trigram `ILIKE` over the record's text columns

## Status
Accepted

## Date
2026-09-02

## Decision
`public.search_record(p_q, p_limit)` (migration 0036) is THE RECORD's search: a
case-insensitive substring (`ILIKE`) match over the text columns of `public.events`
(chrome `title`/`domain`, youtube `title`/`channel`, calendar `summary`/`title`),
`public.transactions` (`merchant`, `category`), `public.checkins` (`note`) and
`core.atoms_current` (`evidence_span`), accelerated by `pg_trgm` GIN expression indexes.
**No ranking model; recency order.** Hits use the `get_timeline` row shape
(`day, at, kind, text, src, row_id`) so a hit is its own trace (REQ-ASK-011) and taps
through to `get_timeline(day)`. `by_month` counts every hit, not the returned page;
`truncated` says whether the page is partial. **An empty result is `n: 0, hits: [],
by_month: []`** — for a search, an empty list is the honest answer (REQ-INF-505), unlike
a missing measure, which is absent. Queries under two characters return the same
empty shape plus a `note`.

**Coordinates and `restricted.*` are never searched**, and no location text column is
in scope; a test asserts the migration text contains neither `restricted.` nor a
`lat`/`lon` token (REQ-LOC-005, RULE-29).

## Storage
Five trigram indexes on a 255 MB database (events 34 MB, transactions 1.1 MB) against
the 500 MB Supabase Free ceiling (OQ-20). Measured sizes are in the session-17 PROGRESS
entry; the indexes are dropped by a forward migration if the ceiling approaches.

## Alternatives considered
- Postgres full-text search (`tsvector`): rejected for v1 — stemming and stop-words
  hide exact merchant strings and channel names, which is what Joe searches for; trigram
  substring is what "find that thing" means here.
- A ranking model: rejected — RULE-11/RULE-15; recency is deterministic and explainable.
