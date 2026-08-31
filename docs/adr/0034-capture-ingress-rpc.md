# ADR-0034: The capture ingress — a write-only RPC, not table access

## Status

Proposed — **not applied**; opening an internet-reachable write path to the personal
database is a STANDING_RULINGS STOP-AND-ASK #5 decision (changes what enters the
system). This ADR is the design for Joe to approve; migration 0017 implements it and
is held for his `--commit`.

## Date

2026-08-31

## Context

The goal (`ops/WORK_QUEUE.md`) is unattended capture running before the subscription
ends. RULE-30 fixes the capture channel: an iOS Shortcut POSTs; the PWA never calls
`getUserMedia`. The Shortcut needs an HTTPS endpoint that lands a row in
`core.raw_captures`. There is no deployed endpoint and no Cloudflare/Supabase-Edge
credential available to the agent, so a custom function deploy is out. But Supabase
already exposes PostgREST over the database — the endpoint exists; the only question
is how the Shortcut authenticates and what it may do.

Current posture (`migrations/0012`, verified live):
- `anon`/`authenticated` have **REVOKE ALL** on the `core` schema — no table access.
- `service_role` has `SELECT, INSERT` on `raw_captures`/`atoms` (the ETL identity).
- RLS is on; `raw_captures` is append-only (trigger); `recorded_at` is forced server-side.

Two naive options both fail:
- **Anon key → tables:** anon has no access; capture is denied.
- **Service-role key in the Shortcut:** works, but the service-role key is a
  full-bypass secret. On a phone it is a catastrophic leak surface. Rejected.

## Decision

**Capture lands through a single `SECURITY DEFINER` RPC, `public.ingest_capture(...)`,
that `anon` may EXECUTE and nothing else.** This is ADR-0020's read/egress separation
applied to ingress: the public credential can *append a capture and do nothing else* —
it cannot read a row, reach the `core` schema, touch another table, or mutate.

- The function inserts into `core.raw_captures` with `trust_level='trusted'`
  (self-authored Shortcut/PWA capture) and `processing_status='received'`, running as
  its owner (which holds the INSERT right); the append-only trigger and the
  `force_recorded_at` trigger still apply.
- It accepts only the self-authored sources (`shortcut_voice|photo|text`, `pwa_text`)
  and raises on any other — third-party feeds (`email_receipt`, `healthkit_workout`,
  `location`) are `untrusted`-lane and ingested by the ETL/`service_role`, never this
  public path (ADR-0020 trust boundary).
- `anon` gets `EXECUTE` on this one function; **no schema-`core` grant, no table grant.**
- Idempotent: a client-supplied `capture_id` (UUIDv7, REQ-CAP-006) with
  `ON CONFLICT DO NOTHING` makes a retried POST safe.

The Shortcut carries the project **anon key** (semi-public by design) and calls
`POST /rest/v1/rpc/ingest_capture`. The anon key stays in the Shortcut, on Joe's phone;
it never reaches the agent or the repo.

## Consequences

**Good.** Real capture can land with **zero deploy, zero agent-held secret, zero
`getUserMedia`**. The public credential is write-only and narrow: the worst a leak
buys is appending capture rows (append-only, no read, no other table) — recoverable and
rate-limitable, never a data-exfiltration or mutation path. The whole thing is one
migration the agent can author and dry-run; only the apply and the Shortcut are Joe's.

**Cost / residual (named, not hidden).**
- **Capture spam** is the live risk: anyone with the anon key + URL can append rows.
  Mitigations, owed if it ever bites: a shared capture token checked in the function; a
  per-source rate limit; rotating the anon key. Not built now — for a single-user
  system the exposure is bounded and the append-only table makes cleanup trivial.
- **Assumes Supabase's default PostgREST config** exposes the `public` schema and
  `anon` role. If Joe has locked PostgREST down, the grant needs adjusting.
- **Extraction is deferred.** This lands `raw_captures` only. `raw_captures → atoms`
  (extraction) is a later, deferrable step — and crucially, captures are retained
  immutably, so extraction can run any time later, even after the subscription ends.
  Landing the raw capture is what the data clock actually requires.

## Alternatives considered

- **A dedicated `capture` Postgres role + a minted JWT.** Cleaner in theory, but minting
  a role-scoped JWT needs the project JWT secret (a full-power secret the agent must not
  handle) and more moving parts. The `SECURITY DEFINER` RPC gets the same write-only
  narrowness with only an EXECUTE grant. Rejected as heavier for no security gain.
- **Deploy a Cloudflare Worker / Supabase Edge Function as the endpoint.** No credential
  available to the agent; and it adds an egress-capable compute surface where a plain DB
  function suffices. Deferred — revisit only if the RPC path proves insufficient.
- **Service-role key in the Shortcut.** Rejected (full-bypass secret on a phone).
