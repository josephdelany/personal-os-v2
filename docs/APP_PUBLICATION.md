# App publication — daily page

Updated 2026-09-25 (ADR-0173). Supersedes the release/usable-ask packet (a74355c/274f01e),
whose Ask improvements were integrated at 21faf12 and whose page is now `app/explore.html`.
That packet's text remains in Git history.

## How the page is published

`pages.yml` deploys `app/` to GitHub Pages on a push to `main` that touches `app/**`, after
running the Node UI tests (Ask, daily page, V0 client). The `github-pages` environment
already allows `main`, so no environment policy change is needed.

The earlier packet withheld pushes to `main` because `tests.yml` runs the suite against the
production database on every `main` push, and main's fixtures at that time could apply
migrations there. The current tree refuses schema-building helpers without the disposable
server and lints for it (ef2dd76; `tests/test_release_acceptance.py`, 28 pass locally). Main's
nightly schedule was already running the older, unguarded fixtures, so merging the current
tree reduces that exposure. The live suite still reads production and depends on the
repository `SUPABASE_DB_URL` secret, which may be the stale credential (28P01).

## What publication does not do

It does not apply migrations 0091–0096. Until they are applied, the page can sign in but
the Today/History reads return "Couldn't load this day" (never an empty day). Database
activation follows V0_BACKEND_ACTIVATION after Joe restores the credential.

## Verification after a push

1. The `pages` run for the pushed commit succeeds (tests run before upload).
2. The served `index.html`, `daily.mjs` and `v0_client.mjs` match the commit.
3. After activation: Joe signs in on his phone and one real check-in saves and reads back.
