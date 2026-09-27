# Next session — 2026-09-25

Overwrite this file at each stopping point; keep it under ~60 lines (ADR-0173).
Previous 2,175-line checkpoint: `docs/history/2026-09-25-next-session-archive.md`.

<!-- backend-control:start -->
```json
{
  "version": 1,
  "status": "held",
  "updated_at": "2026-09-25T21:00:00+00:00",
  "last_progress_at": "2026-09-25T21:00:00+00:00",
  "unit": "V1-activation",
  "next_action": "Waiting on Joe: reset the Supabase database password and update SUPABASE_DB_URL (never paste it in chat). Then run the read-only ops/preflight/v0_backend.sql, turn the result into an exact migration list, and ask Joe to authorize the apply and the page publication. No new features until 7 real days of use (ADR-0173)."
}
```
<!-- backend-control:end -->

## Where things stand

| Piece | Implemented | Tested | Deployed | Observed |
|---|---|---|---|---|
| V0 owner RPCs (0091–0096) | yes | local SQL suite | no | no |
| Daily page `app/index.html` (Today/Add/History/Ask) | yes | Node + offline browser smoke | no | no |
| Old exploratory views (`app/explore.html`) | yes | offline browser smoke | no | no |

The database credential failed with 28P01 on 2026-09-24. Nothing has run on Joe's real account.

## Joe's steps (only Joe can do these)

1. Supabase dashboard → Project Settings → Database → reset the database password.
   Put the new connection string in `SUPABASE_DB_URL` wherever it is normally set.
   If GitHub Actions uses it, update that repository secret too. Say "done" without pasting it.
2. Approve the exact migration list. `python3 -m tools.v1_activation_check` produces it
   read-only; each file is dry-run before any `--commit`.
3. Publication: the branch is merged to `main`, which deploys `app/` to Pages
   (APP_PUBLICATION.md). Until migrations are applied the page signs in but cannot load days.
4. Use it: a morning and evening check-in, meals, sets. Seven real days.
   Data sources and the old Mac jobs awaiting a decision: `docs/DATA_IN.md`.

## Try it before activation

Open the published page with `?demo=1`: the real UI over an in-memory fake server. Nothing
is sent or kept; reload resets it.

## Checks for this track

Use the project virtualenv: system `python3` lacks Pint and fails ~80 tests spuriously.
`V=/tmp/personal-os-pint-venv-cf404e6/bin` (outside the repo; /tmp may be cleared on reboot;
recreate with `python3 -m venv` + the pip line in `.github/workflows/tests.yml`).

- `node --test tests/daily_ui.test.mjs tests/ask_ui.test.mjs tests/v0_client.test.mjs`
- `python3 tests/daily_browser_smoke.py` and `python3 tests/ask_browser_smoke.py`
- `PATH="$V:$PATH" env -u SUPABASE_DB_URL python3 -m pytest -q tests` (no-DB suite)
- `PATH="$V:$PATH" env -u SUPABASE_DB_URL python3 tools/test_local_sql.py` (disposable PG17)
- Last full run at ba9d9e6: no-DB 1488 passed / 0 failed; SQL 1252 passed / 1 skipped / 0 failed.
- Editing either browser harness breaks its pinned hash (ADR-0174); re-pin only with review.

## Not done

ADR-0174 harness pins: independent review accepted 2026-09-27.

Meal photos still go through the iPhone Shortcut; the page does not upload them.
Chase import stays a CLI (`tools/import_v0_card.py`); ambiguous rows are reviewed in the Spending card.
Visits depend on Overland and the hourly refresh being activated.
