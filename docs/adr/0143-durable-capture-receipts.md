# ADR-0143 — Durable capture receipts at authenticated ingress

Status: accepted for local implementation; production migration, deployment and
device cutover remain held for approval. Date: 2026-09-22.

Requirements: REQ-CAP-006..009, 011, 016..018. Extends ADR-0034/0130.

The Python endpoint contract has no hosting or storage adapter. The old anonymous
RPC generates IDs and cannot distinguish a suppressed insert. These fail the
retry contract in ADR-0130. A Cloudflare Worker (the actor specified in the capture
requirements) authenticates before reading a body and calls a write-only RPC.
The Worker holds a signed JWT for `capture_ingest` plus the legacy anon API key.
It never holds the service-role key or the project signing secret (ADR-0020).
Migration 0075 creates a NOLOGIN/NOINHERIT role with EXECUTE on this RPC only;
PostgREST authenticator may assume it. Tests inspect effective private-table and
application-RPC privileges, including PUBLIC inheritance. PostgreSQL extension
primitives are excluded from the application-RPC inventory, not from table checks.
Provision the scoped JWT separately through trusted secret administration. Signature
verification belongs to PostgREST; the Worker also rejects wrong-role credentials
before reading a body to catch accidental service-key configuration. No model is called during
ingress. No SDK or third-party JavaScript package is required.

Migration 0075 introduces `receive_capture(text)`. It validates the client UUIDv7,
offset timestamp, source and payload. Rejections retain the exact authenticated
body in restricted `ops.ingest_rejections`; no payload/error detail is logged or
returned. `INSERT ... ON CONFLICT DO NOTHING RETURNING` determines created versus
duplicate atomically. A duplicate never replaces the earlier raw capture. The HTTP
adapter maps created to 202, duplicate to 200, retained rejection to 400, and any
unproven storage outcome to 503. Retrying the same client ID recovers a lost reply.

The adapter uses only a fixed Supabase HTTPS origin, refuses redirects, forwards no
client headers and requests commit. Release must verify PostgREST transaction-end
configuration: use `db-tx-end=commit-allow-override` and verify the response has
`Preference-Applied: tx=commit`. Default `commit` without preference support is
insufficient for this adapter: it deliberately returns 503 without that receipt.
A successful RPC is durable only when the request commits.
[PostgREST transaction contract](https://postgrest.org/en/latest/references/transactions.html).
Tests of a rolled-back SQL transaction prove inserts and conflict behavior, not
production commit acknowledgement or real two-process concurrency (OQ-82).

The legacy `ingest_capture` RPC is retained during preparation, because disabling
the phone's existing capture path before cutover loses data. It remains an explicit
release gap: deploy/test the new endpoint, update and observe the device, then
revoke legacy anonymous execution in a separately approved forward migration.
This additive migration alone does not close REQ-CAP-008 across all public writes.

Enrichment recovery is a separate dependency: REQ-CAP-025..027 request updates
forbidden by RULE-02/0012/ADR-0035. Joe approved OQ-83 in ADR-0144: immutable processing events plus a
current-state view. That decision permits the next implementation unit; it is not
a claim of working enrichment or nightly retry. Raw captures remain durable and available for later processing.

## Cost and privacy

Cloudflare Workers was already specified for this path. Use **Workers Free only**:
100,000 requests/day, hard failure at quota, fail-closed route, no paid upgrade.
Planning bound: at most 200 personal captures/retries per day (not measured usage).
One Supabase subrequest per capture; existing database storage/quota monitoring
applies. Exhaustion returns failure so the device retains its queue. No new queue,
storage service or model dependency. See [Workers limits](https://developers.cloudflare.com/workers/platform/limits/).
Node 24 is a local/CI test runtime only: open-source, no subscription, no external
calls in tests. Existing public-repository Actions execution remains $0. Synthetic
SQL fixtures use disposable schemas and rollback, never production or public rows.

## Review findings

Malformed JSONB Unicode/numeric conversions escaped rejection retention: two
regressions failed before specific 22P05/22003 catches were added. The platform's
ExecutionContext argument was initially confused with injected fetch; corrected
with a real default-export test. The first draft used service_role in an egress
process: independent review rejected that under ADR-0020; a scoped JWT replaced it.

Effective privilege testing then exposed six PUBLIC application functions despite
NOINHERIT: the check-in trigger, three pure Ask text helpers, two-argument search
wrapper and derivation_support. The search/refusal functions already owner-check
inside their bodies; this finding does not demonstrate anonymous personal-data
readback. Migration 0075 explicitly revokes ambient execution and preserves intended
authenticated/ETL APIs. No constitutional exception is required or introduced.

Role-name collision now fails the migration rather than adopting unknown privileges.
Deployment must separately audit both tokens against live legacy public ACL/RLS,
which the empty-database prerequisite fixture does not reproduce.
