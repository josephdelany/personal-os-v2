# ADR-0036: The read API is one envelope RPC per surface, authenticated-only

## Status

Accepted (design + rolled-back proof). Migration 0021 is **staged, not applied** —
it joins 0019/0020 in the held set awaiting Joe's explicit authorization (the
auto-mode classifier enforces STANDING_RULINGS on live DDL/writes).

## Date

2026-09-01

## Context

The front end (Lovable, later) needs reads. ADR-0020 forbids a generic SQL surface
reaching any client; RULE-14/INV-3 require every rendered numeral to trace to a
stored row; ADR-0018 forbids rendering a coarsened self-report as a false point;
and personal data must never be anon-readable (the ingress anon key is write-only
by design, ADR-0034).

## Decision

- **One RPC per surface, returning one jsonb envelope** (`public.get_day(p_day)`
  first): checkin scores as {point, low, high, **atom_id**}, food labels, notes,
  coverage counts, last extract heartbeat. Every numeral carries its atom_id, so
  the renderer can refuse untraceable numerals (RULE-14) and audit is one lookup.
- **Fields get added, never renamed** (the old system's proven contract style).
- **EXECUTE to `authenticated` only; anon revoked explicitly.** The signed-in
  owner (Supabase Auth magic-link) is the only reader. The write path (anon,
  ingest_capture) and the read path (authenticated, get_day) are disjoint
  credentials — ADR-0020's separation carried to the client.
- **Absence is absent**: keys with no data are stripped, and the front-end
  contract (docs/LOVABLE_FRONTEND.md) requires "not logged", never zero.

Proof (rolled back): migrations 0001–0021 into disposable schemas + extraction of
the 3 real check-ins, then `get_day('2026-07-22')` returned energy 5.0 [4.5,5.5]
with atom_id, correct coverage; `has_function_privilege`: anon=false,
authenticated=true.

## Consequences

**Good.** The Lovable prompt is paste-ready against a frozen contract; the UI can
be built by a non-engineer with zero API design. The honesty rules travel in the
contract itself.

**Cost/residual (named).** `coverage.unextracted` is a global lag counter, not
day-scoped (documented). Auth requires Joe to create his one Supabase Auth user
before first login. Trends/findings need Phase-5 tables and future RPCs — the
envelope pattern extends; nothing here blocks it.

## Alternatives considered

- **Direct table/view SELECT grants to `authenticated`.** Rejected: ADR-0020
  (parameterised RPCs only), and a view grant invites ad-hoc client queries that
  bypass the numeral-traceability contract.
- **Anon-readable envelope for a zero-login UI.** Rejected outright: personal
  data public — never.
- **GraphQL/PostgREST resource-per-table.** Rejected: the surface is one day; one
  envelope call is simpler, and the contract can hold honesty rules a generic
  resource API cannot.
