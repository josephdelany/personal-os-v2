# ADR-0010: RULE-02 enforcement — append-only by grant AND trigger; the owner bypass; the CI query scope

## Status

Accepted

## Date

2026-08-23

## Context

RULE-02 requires `raw_captures` and `atoms` to be append-only, "revoked at the
grant level, not merely avoided by convention." Building the migration surfaced a
Postgres reality that the constitution's literal RULE-02 CI query does not
account for.

The constitution's RULE-02 check is:
```sql
select count(*) from information_schema.role_table_grants
where table_name in ('raw_captures','atoms')
  and privilege_type in ('UPDATE','DELETE');  -- must be 0
```
Verified against the live instance (2026-08-23): `information_schema.role_table_grants`
reports **the table owner's own implicit privileges** as a self-grant
(`postgres → postgres`, UPDATE and DELETE), and these **cannot be revoked** — an
owner always retains implicit privileges on its tables. So the literal query
returns ≥ 2 no matter what, because of the owner rows.

**Correction (session-end review, 2026-08-23):** an earlier draft of this ADR
claimed Supabase default-grants UPDATE/DELETE to `anon`/`authenticated`/`service_role`
on new tables, "which must be revoked." That is **false for a new schema** —
verified: every fresh `core` table carries only `postgres` grants, and
`pg_default_acl` for schema `core` is empty. Supabase's default privileges are
scoped to `public`, not to `core`. Consequently the migration's `REVOKE
UPDATE, DELETE … FROM anon, authenticated, service_role` on the `core` tables is a
**defensive no-op** (there was nothing to revoke). The append-only guarantee for
`service_role` therefore rests on the *explicit minimal grant* — `service_role`
gets only `SELECT, INSERT` on `atoms`/`raw_captures` and nothing else — not on the
REVOKE undoing a default. The REVOKE is kept as a guard against a future default
change, but it is not the load-bearing mechanism, and the grant-path probe passes
because service_role was never granted UPDATE/DELETE, not because a REVOKE fired.

## Decision

**Two enforcement layers.**

1. **Grant level.** The migration `REVOKE UPDATE, DELETE ON core.atoms,
   core.raw_captures FROM anon, authenticated, service_role`, and revokes schema
   `USAGE`/all-table access from `anon`/`authenticated` entirely (personal data).
   `service_role` (the future ingest/ETL identity) keeps schema `USAGE` + `SELECT,
   INSERT` — reach and append, never mutate.
2. **Trigger level.** A `BEFORE UPDATE OR DELETE` trigger on both tables raises
   `insufficient_privilege`. This catches **even the owner** (`postgres`), whose
   grant cannot be revoked. Grants stop app roles; the trigger stops everyone.

**Which role each job connects as.** Phase-2 ETL connects as `postgres` (owner) —
caught by the trigger, never by grants. The future ingest endpoint (Phase 3,
Cloudflare Worker) connects as `service_role` — caught by the grant-level revoke.
No generic mutating role touches these tables.

**The CI query is scoped to app roles.** `tools/check_invariants.py` counts
UPDATE/DELETE grants on `atoms`/`raw_captures` **where grantee ∈ {anon,
authenticated, service_role}** — expecting 0 — and separately proves the trigger/
grant behaviourally by attempting a mutation as `service_role` (rejected with
`permission denied for table atoms`, on an empty table, before any row is
processed — so nothing is fabricated, RULE-01). The owner path is verified
structurally (the trigger is present in `pg_trigger`); firing it behaviourally
would require a committed data row, which RULE-01 forbids.

**This scoping is a correction of the RULE-02 query to its stated purpose, not a
weakening (RULE-00).** REQ-CAP-012 scopes immutability to "every role used by the
ingest endpoint, the resolution job and the PWA" — the app roles, explicitly not
the migration/owner role. It changes a constitution code block, so it was flagged
for ratification, not silently applied. **Joe ratified the app-role scoping on
2026-08-23**, and the constitution's RULE-02 example query was updated the same day
to carry the `grantee`-scope with a pointer to this ADR.

## Consequences

**Good.** Append-only is enforced by two independent mechanisms; the behavioural
test proves the table privilege specifically, not a schema-level accident; nothing
is fabricated to test it.

**Bad.** The constitution's literal RULE-02 SQL and the CI implementation differ
until Joe ratifies the scoping and the constitution text is updated. Until then
this ADR is the record of why.

## Alternatives considered

- **Own the tables with a no-login role.** Rejected: the owner self-grant still
  appears in `information_schema`; the literal query still returns non-zero.
- **Trigger only, no grant revoke.** Rejected: RULE-02 explicitly requires
  grant-level revocation, and defence-in-depth is cheap.
- **Grant revoke only, no trigger.** Rejected: the owner (Phase-2 ETL identity)
  would be able to mutate; the trigger is the only thing that stops it.
