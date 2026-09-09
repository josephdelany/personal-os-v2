# ADR-0082 — Disposable local PostgreSQL verification

Date: 2026-09-08. Development tooling only; no production connection change.

Production authentication currently fails, and migration creation alone does not
execute PL/pgSQL branches. Use PostgreSQL 17 locally to execute focused SQL tests.
This does not replace the live migration dry run or Supabase acceptance checks.

PostgreSQL is local free software: no account, usage tier, metered calls or
recurring charges. Projected usage is one temporary test server, bounded by local
disk and memory; resource exhaustion fails the test rather than purchasing capacity.
Homebrew supplies the development binary and its native dependencies. Nothing is
added to the deployed application's dependency set. No background service is enabled.

The test server listens on a Unix socket in a temporary directory, with TCP
disabled. Tests opt in through `PERSONAL_OS_TEST_SOCKET`; production `lib/db.py`
and its verified-TLS posture are unchanged. There is no automatic local fallback.

All test objects and fixture rows use disposable `*_pytest` schemas and one
rolled-back transaction, as required by RULE-01 / ADR-0022. No personal data is
copied to the local server. Apply production SQL bodies with schema tokens
rewritten, rather than reimplementing SQL behavior in Python doubles.

Limitations: local PostgreSQL cannot prove Supabase authentication, deployed
permissions, legacy schema compatibility, remote extensions, schedules, or actual
capture. Focused tests must say which prerequisites they create and which migration
bodies they execute; passing a fragment is not passing the whole chain.
