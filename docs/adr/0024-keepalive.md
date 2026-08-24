# ADR-0024: Reliability keepalives, and the ops.runs heartbeat doctrine

## Status

Accepted

## Date

2026-08-23

## Context

Two calendar clocks silently end this project (ROADMAP Phase 0, Gate 0):

- **Supabase Free pauses a project after 7 days of inactivity.** A paused project
  stops answering, so every downstream job dies quietly.
- **GitHub disables a repository's scheduled workflows after 60 days of no repository
  activity.** Since the keepalive itself runs on GitHub Actions, this failure would
  disable the very thing that keeps Supabase warm — one clock killing the other.

Gate 0 requires each keepalive to have **fired on its own schedule and left a row in
`ops.runs`**. `ops.runs`/`ops.job_registry`/`ops.egress_log` already exist (migration
`0011`, session 7) — this session did not recreate them. Features F-014/F-015 cited
`REQ-NFR-001`/`REQ-NFR-002`, requirement IDs that existed in no spec (the `REQ-NFR` half
of OQ-16), so the spec had to be written before the code (CLAUDE.md: a missing
requirement is written first).

Two facts constrain the design. **The repo has never been pushed to GitHub** (OQ-02
reserved the first push as a deliberate outward action), so no scheduled firing can
happen yet; and Joe ruled this session to **build and prove the mechanism locally**, and
that he does the push later. Separately, RULE-01 forbids fabricated rows in any table —
so whether a keepalive may *commit* a proof-of-life row to `ops.runs` needed a ruling.

## Decision

**One external heartbeat, on GitHub Actions, covering both clocks** (`ops/keepalive.py`
+ `.github/workflows/keepalive.yml`):

- **Supabase (REQ-NFR-001):** a daily job (`cron: '17 6 * * *'`, period 1 day ≪ 7)
  makes an authenticated write to Postgres — the write *is* the `ops.runs` row, so no
  separate ping is needed.
- **GitHub (REQ-NFR-002):** the **same daily job** writes a `keepalive_github` proof-of-life
  row to `ops.runs` and checks repository staleness **every day**, making a single
  heartbeat commit to `ops/heartbeat.txt` **only when the most recent commit is older than
  50 days**. A daily check bounds worst-case staleness at 51 days (< GitHub's 60-day
  limit); a *monthly* check would allow 50 + 31 = 81 days and let the schedule disable
  itself — the reviewer's finding B1, which this daily structure exists to avoid.
  Commit-when-stale (not commit-every-run) keeps `main` from accreting ~365 commits/year.
  The heartbeat is a bare UTC timestamp — no personal data ever leaves this way (RULE-29).

**The ops.runs heartbeat doctrine (RULE-01 ruling by Joe):** a keepalive's proof-of-life
is a genuine operational row recording that a job *ran at time T*. That is a **true
operational fact, not fabricated data** — the row carries `rows_written = 0` because a
keepalive writes no *data* rows. Committing it is therefore permitted. The mechanism is
proven by the named tests in `tests/test_keepalive.py`, which drive both the success and
failure paths inside a **rolled-back disposable `ops_pytest` schema** (ADR-0022).

**REQ-NFR-003/004:** every run writes exactly one `ops.runs` row (`running` → `ok`), and
a failed job records `status = 'error'` when the database is reachable and exits non-zero
in every failure case, so a keepalive death is visible, not silent.

**`started_at`/`finished_at`** use `clock_timestamp()` (wall-clock at each statement), not
`now()` (fixed for the whole transaction), so `finished_at` is the real completion instant
rather than a copy of `started_at`.

## Consequences

**Good.** The mechanism is proven by **6 named tests** (`tests/test_keepalive.py`, all
pass). `REQ-NFR` exists, closing the REQ-NFR half of OQ-16. `ops.job_registry` names both
jobs.

**Bad / flagged, honestly.** **No clock is running yet.** Gate 0 cannot close until the
repo is pushed to GitHub (OQ-02) *and* `SUPABASE_DB_URL` is set as an Actions secret;
only then does `keepalive_supabase` fire (≤ 24 h later) and `keepalive_github` (same daily
run). **F-014/F-015 stay `failing`** — the mechanism passing is not the feature (which is
"fired on schedule"). The Supabase 7-day clock is not at the wall today only because the
old cron stack (OQ-17) keeps the DB warm; that is luck, not our keepalive.
**Stale live rows (reviewer, session-end — now corrected, OQ-28).** The two `ops.runs`
rows and the `keepalive_github` `ops.job_registry` row committed earlier this session were
written by *pre-fix* code (rows `now()`-stamped with no `trigger` key; registry row on the
monthly `'0 6 1 * *'` / 1440h design B1 removed). With Joe's consent the `ops.runs` rows are
now marked `trigger=manual_smoke` (labelled, not re-run — they stay `now()`-stamped so they
are never mistaken for a scheduled firing) and `keepalive_github` moved to the daily design
(`'17 6 * * *'`, 1200h). The mechanism's evidence is the 6 named tests, not these rows.

## Alternatives considered

- **Supabase-side `pg_cron` keepalive as primary.** Rejected: circular — the scheduler
  would live inside the project it keeps alive. Available as belt-and-braces if Joe wants
  cover before the push (offered; not built).
- **A third-party keepalive Action.** Rejected: hands a marketplace action a write-scoped
  token on a public repo; the stale-commit logic is a few lines of inline shell.
- **Daily heartbeat commit.** Rejected: ~365 commits/year of churn vs commit-when-stale.
- **No committed heartbeat (rolled-back only).** Considered under RULE-01; Joe ruled a
  true operational run-record is not fabricated data, so a committed heartbeat is allowed.
