# RUNBOOK — operating the file without Claude

*Written 2026-09-02 for the day the Claude subscription ends. Everything below is
free, runs without any model, and needs only: a GitHub account, the Supabase project,
Lovable (its own model, its own credits), and your phone.*

## 1. What runs by itself (GitHub Actions, free tier, already live)

| Job | Schedule | What it does | Proof it ran |
|---|---|---|---|
| `keepalive` | daily 06:17 UTC | Pings Supabase and GitHub so neither pauses; heartbeat commit if the repo goes stale | `get_trust().job_heartbeats` → `supabase`, `github` rows |
| `extract` | hourly at :41 | Turns every new capture (check-ins, food, workouts, health, notes) into atoms; after B5 also runs `derive_visits` | `job_heartbeats` → `extract_checkins`, `derive_visits` |
| `analysis` | nightly 08:23 UTC | Rebuilds the panel and baselines; Mondays: the contrast scan with its shuffled-null twin; forecasts | `job_heartbeats` → `panel_build`, `baselines`, `scan`, `forecast` |
| `gates` | every push | Layout + guard tests | green check on GitHub |
| `pages` | every push | Deploys the v0 surface | josephdelany.github.io/personal-os-v2 |

Nothing here calls a model. If Anthropic vanished tomorrow, all of it keeps running.

## 2. What you do (the only human inputs)

**Daily, from the phone (30 seconds):** Night check-in Shortcut. Log Food at meals.
Log Workout after each session. Overland runs by itself.

**Weekly:** open RELIABILITY in the app. Read the heartbeats and blind spots. That is
the whole health check. Every job row should say `ok` within its schedule; every
core metric should have a `last_day` within a few days.

**Monthly:** refresh the exports that feed the seven-year history — Apple Health
export, bank export, Chrome/YouTube history — via the old stack's importers (still
running in `josephdelany/Personal-OS`) until they are rebuilt as captures. Until then,
`coverage_blindspots` will name the streams going stale; that is the reminder.

**Whenever you have Lovable credits:** paste the next round from `docs/build/L*.md`
in order (L0 → L7). Each is one message. Each names its precondition; do not paste a
round whose backend is not live.

## 3. How to tell if something is broken

Open RELIABILITY (or run `select public.get_trust()` in the Supabase SQL editor after
`select set_config('request.jwt.claims','{"email":"joseph.delany21@gmail.com"}',true);`).

| Symptom | Meaning | Fix |
|---|---|---|
| A job's `last` is older than 2× its schedule | The Action stopped | GitHub → Actions → the workflow → "Re-run"; if it fails, read the log's last 20 lines; the usual cause is the `SUPABASE_DB_URL` secret expired (rotate the DB password in Supabase → Settings → Database, update the secret) |
| `status: error` on `extract_checkins` | A capture had a shape the extractor refused | It is skipped, not lost; nothing to do unless it repeats hourly — then open the capture in `core.raw_captures` and see which key is malformed |
| App shows "owner only" everywhere | Magic-link session expired | Sign in again |
| App shows "The file could not be read: …" | An RPC errored | The message names the function; paste it into the Supabase SQL editor to see the real error |
| Supabase email "project will be paused" | Keepalive stopped writing | Re-run `keepalive` by hand (Actions → keepalive → Run workflow); check the secret |
| Supabase storage above 450 MB | Growth from captures/fixes | `select pg_size_pretty(pg_database_size(current_database()))`; the reclaimable ~174 MB is the old stack's tables (OQ-17) — drop them only after the importers are rebuilt |
| Overland stops sending | App killed / token wrong | Open Overland: green status, endpoint ends `/location-ingest`, token matches the Supabase secret |

## 4. Rules that must survive without anyone enforcing them

- Never edit or delete a row in `core.raw_captures`, `core.atoms`, `restricted.location_fixes`. Corrections are new rows. The triggers will refuse; do not disable them.
- Never put a coordinate, a password, a personal data file, or the DB URL into the repo. `gates` will refuse the commit; do not weaken it.
- Never grant `anon` or `authenticated` on any table. Reads go through `get_*` functions only.
- Never edit `ops/features.json` by hand; run `python3 tools/update_features.py`.
- A number the app did not receive from an envelope is not shown. If Lovable ever "helpfully" computes one, the round that introduced it is reverted.

## 5. Resuming with any model later

Everything a future model needs is in the repo, in this order: `CLAUDE.md` →
`docs/CONSTITUTION.md` → `docs/DECISIONS.md` → `docs/THE_FILE.md` → `docs/build/README.md`
→ `ops/PROGRESS.md` (last three entries). The build pack in `docs/build/` lists the
first unfinished item. Any coding model can run a `B*.md` file; the instructions
assume nothing about which one.

The two things that still need a model, in priority order: (1) the **ask** engine
(REQ-ASK: a question → a registered query plan → a traced, tiered answer; no design
exists beyond the requirements); (2) rebuilding the old stack's importers (Apple Health,
bank, browser history) as capture paths so the `Personal-OS` repo can be retired and its
174 MB reclaimed.

## 6. Cost

$0/month. GitHub Actions free tier (~2,000 min/mo; this uses ~120). Supabase free tier
(500 MB; watch §3). Supabase Edge Functions free tier (500k calls/mo; Overland uses
~300/day). Lovable: your existing credits only; no round requires a paid plan.
