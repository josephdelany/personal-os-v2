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

- `node --test tests/daily_ui.test.mjs tests/ask_ui.test.mjs tests/v0_client.test.mjs`
- `python3 tests/daily_browser_smoke.py` and `python3 tests/ask_browser_smoke.py`
- `python3 tools/test_local_sql.py --tests tests/test_v1_activation_check.py` (disposable PG17)
- Full SQL suite + ledger writer only when a migration/RPC changes, and before any production apply.

## Not done

Meal photos still go through the iPhone Shortcut; the page does not upload them.
Chase import stays a CLI (`tools/import_v0_card.py`); ambiguous rows are reviewed in the Spending card.
Visits depend on Overland and the hourly refresh being activated.
