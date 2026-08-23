# ADR-0012: ETL database TLS posture — verify against a pinned Supabase root CA

## Status

Accepted. This is the permanent transport-security posture for every database
connection the system makes, from the Phase-0 archive through all ETL from
Phase 2 onward. It supersedes nothing; it records a decision that until now
lived only in a code comment in `lib/db.py`.

## Date

2026-08-23

## Context

Phase 0's live archive required reaching the Supabase Postgres database. The
machine has no `psql`/`libpq` and no Postgres driver, so a pure-Python driver
(`pg8000`) was installed — a $0 local dev dependency with no service, account,
metered limit, or overage, so RULE-28's cost test does not apply to it.

The Supabase connection-pooler (`aws-1-us-west-2.pooler.supabase.com`) presents
a certificate chain issued by a **private CA** — leaf `*.pooler.supabase.com`
← `Supabase Intermediate 2021 CA` ← `Supabase Root 2021 CA`. The root is
Supabase's own, in no public trust store, so both the system store and
`certifi` (Mozilla's bundle) reject the chain. The pooler sends all three certs
(leaf, intermediate, and root — verified 2026-08-23 via `openssl s_client
-showcerts`), but a server-presented root is never a trust anchor: trusting
whichever root the server hands you is circular. So the root must be obtained
independently, from a source the server does not control — here, the official
`supabase/cli` repository over public-CA-verified HTTPS — and pinned.

A second, independent obstacle: this Python (3.14 / OpenSSL 3.0.18)
`ssl.create_default_context()` enables OpenSSL strict mode
(`VERIFY_X509_STRICT`), which additionally rejects this chain because the
**intermediate** (`Supabase Intermediate 2021 CA`) and the **leaf**
(`*.pooler.supabase.com`) omit an explicit `keyUsage` extension — strict mode
requires a CA appearing in the path to carry `keyUsage=keyCertSign`. Verified
2026-08-23 by inspecting all three certs: the pinned **root** *does* carry
`keyUsage` (`Certificate Sign, CRL Sign`); the intermediate and leaf do not, and
OpenSSL's strict error (`CA cert does not include key usage extension`) is
raised on the intermediate acting as a CA in the path. Standard (non-strict)
verification — what `openssl s_client -CAfile`, `libpq`, and every other
Postgres client apply — accepts it.

This posture is not a one-off for the archive. The same connection path is how
every ETL job reaches the database from Phase 2 onward. A choice made "just for
the archive" becomes the ETL default by inertia, so it is decided here as a
permanent one.

## Decision

1. **One connection path, going forward.** All DB access is mandated through
   `lib/db.py::connect()`, which reads the credential only from the
   `SUPABASE_DB_URL` environment variable (supplied via the gitignored
   `.claude/settings.local.json` `env` block). The credential is never
   hardcoded, never logged, never echoed.

   *Honest exception at authorship time:* two pre-existing scratch scripts in the
   gitignored `_legacy_snapshot/` (`live_snapshot.py`, `diag.py`, created
   2026-08-23 before this ADR) open their own `psycopg2` connections with
   `sslmode=require` and **no** `sslrootcert` — i.e. encrypt-without-verify, the
   posture this ADR rejects. They produced no surviving archive (their
   `supabase_parquet/` output dir is empty). This ADR **supersedes** them; they
   were **deleted 2026-08-23** on Joe's instruction, along with their empty
   `supabase_parquet/` output dir. The "one path" claim is now a fact on disk,
   not merely policy.

2. **Pin the Supabase root CA.** `lib/certs/supabase-prod-ca-2021.crt` holds
   `Supabase Root 2021 CA`, fetched from the official `supabase/cli` repository
   over a public-CA-verified HTTPS connection, then **proven to anchor the live
   pooler chain** — `openssl s_client … -CAfile … → Verify return code: 0
   (ok)`. It is a public certificate (no secret) and is committed so ETL has it.

3. **Verify fully.** `verify_mode = CERT_REQUIRED` and `check_hostname = True`.
   Chain verification against the pinned root and hostname matching are both on.

4. **Clear exactly one strict-mode flag.** `verify_flags &= ~VERIFY_X509_STRICT`,
   because the Supabase **intermediate and leaf** omit `keyUsage` (the pinned
   root carries it). This relaxes only the pedantic extension-presence check; it
   is the same verification level every standard Postgres client uses. **It is
   not `CERT_NONE`** and does not weaken the trust anchor.

## Rejected: CERT_NONE (encrypt without verifying the chain)

Connecting with TLS encryption but `verify_mode = CERT_NONE` was considered and
**rejected**. It was tempting because it is the posture of Supabase's own default
`sslmode=require` and would have unblocked the archive in one line. It was
rejected because:

- It provides **no protection against a man-in-the-middle** — encryption to an
  unauthenticated peer is encryption to whoever answers.
- Because this is the permanent ETL path, an unverified default would silently
  govern every future job, not just the archive.
- The proper pin turned out to be cheap and is now **proven** (return code 0),
  so the trade CERT_NONE offered (speed for security) no longer exists.

Recorded here for the same reason RULE-00 requires recording a threshold change:
this is a security posture every later phase depends on, and the reasoning must
outlive the chat it was decided in.

## Alternatives considered

- **`certifi` / public CA bundle** — fails; the CA is private, not public.
- **Direct host `db.<ref>.supabase.co`** — the pooler is the IPv4 path and was
  reachable; direct is commonly IPv6-only. Pooler chosen.
- **Waiting for Supabase to reissue a `keyUsage`-compliant root** — not our
  certificate to fix; would block Phase 0 indefinitely.

## Consequences

- Every ETL job from Phase 2 must call `lib.db.connect()`; no job may open its
  own raw connection or set its own TLS policy. (The two stale
  `_legacy_snapshot/` scratch scripts that violated this were deleted
  2026-08-23.)
- **The pinned root expires 2031-04-26.** A renewal task is owed before then.
  If Supabase rotates its CA earlier, connections **fail closed** (loud), which
  is the correct behaviour — a silent fallback to no-verify is exactly what this
  ADR forbids.
- The `VERIFY_X509_STRICT` clearing is scoped to that single flag. If Supabase
  reissues its **intermediate and leaf** certificates carrying `keyUsage` (the
  root already carries it), remove the clearing and re-verify.
- `lib/db.py` is a minimal connection helper (TLS + credential parsing only).
  Connection pooling, retry/backoff, and `ops.egress_log` wiring are **not**
  here; they belong to the Phase-2 spine.

## Enforcement

REVIEW tier. There is no automated gate yet. A future lint could assert that
`lib/db.py` uses `CERT_REQUIRED` with the pinned CA file and that no other
module constructs a DB connection or an `ssl` context with `CERT_NONE`.
