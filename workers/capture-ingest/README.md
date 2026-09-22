# Capture ingress — prepared, not deployed

REQ-CAP-006..009/011/016..018; ADR-0143. Entrypoint `index.mjs` uses standard Web APIs.
Run its tests with `node --test tests/capture_http.test.mjs` from the repository root.
SQL behavior: `python3 tools/test_local_sql.py --tests tests/test_capture_ingress_sql.py`.

Deployment is held. Before requesting approval, prepare the exact project, pending
migration chain, Worker route and device cutover. Then verify all of these:

1. Migration 0075 and all dependencies tested and applied under production authorization.
2. Cloudflare **Workers Free**, fail-closed route; no paid plan or billing on overage.
3. Secrets configured through the platform: `CAPTURE_TOKEN`, `SUPABASE_URL` (exact
   project HTTPS origin), `SUPABASE_ANON_KEY` (legacy JWT with role `anon`), and
   `SUPABASE_CAPTURE_JWT` (signed, expiring JWT with role `capture_ingest`). Provision
   the scoped JWT outside the Worker; verify rotation/expiry and authenticator role
   membership. Never give the Worker the signing secret or service-role key. Only
   the capture token goes on the phone. No credentials in chat, git, command arguments or logs.
4. PostgREST `db-tx-end=commit-allow-override`, with an observed
   `Preference-Applied: tx=commit` response. Default `commit` alone lacks the header
   and the Worker will return 503. Never loosen that check to make a smoke test pass.
   Audit both the scoped token and anon key's effective private-read privileges,
   including legacy `public` tables and definer RPCs. Local legacy prerequisites
   omit production ACL/RLS details and cannot prove this. Migration refuses any
   existing `capture_ingest` role rather than trusting its prior privileges.
5. An authorized real capture sent through the deployed Worker returns 202, then
   reads back from another transaction with matching ID/event time/payload. Replay
   the same ID: 200 duplicate, unchanged original, one stored row. Invalid token:
   401 with no body processing. Provider/quota/storage error: no false 200/202.
6. Confirm phone queue keeps failures and removes only acknowledged lines. Legacy
   `ingest_capture` still permits anonymous writes: retire its grants by approved
   forward migration only after device cutover and observation. Until then the
   new endpoint's authentication does not secure the old path.

No enrichment runs in this handler. Durable rows survive downstream unavailability,
but media transcription, extraction, retry scheduling, processing-state readback
and the 72-hour stalled review are still required (OQ-83). The Python contract
helper is not this deployable handler and must not be used as hosting evidence.
No public route is enabled by the checked-in Wrangler configuration.
