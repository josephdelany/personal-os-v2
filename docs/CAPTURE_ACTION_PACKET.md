# Capture action packet — for Joe

One list. Seven actions, each with its owner, what it unblocks, and how you know it worked.
Prepared 2026-09-09 against branch `session-21-recovery-and-ask` @ `8793a17`.

**Why this is the priority.** `tools/check_freshness.py` reports **0 of 17 monitored metrics
fresh**. Device-side capture stopped on 2026-07-28 and every scheduled job stayed green
throughout, because the jobs were alive and only their inputs were dead. Items 1–3 are the only
things that change that number; no further backend code will. The samples for the gap are still
on your phone and in Google's export, so this is recoverable — until a device is wiped or a
retention window rolls.

---

## 1. Apply migration 0051 (the import path)

- **Owner:** Joe. It is a production write; the environment's permission classifier refused it
  and I did not work around it.
- **Exact command:**
  ```bash
  cd ~/PERSONAL_OS_V2
  PYTHONPATH=. python3 tools/run_migration.py --core core --ops ops --only 0051 --verify --commit
  ```
- **What it does:** adds `file_import` to the `capture_source` enum and 20 rows to
  `core.metric_registry`. Forward-only, additive, writes no data row.
- **Verified how far:** dry-run through the whole chain, 418 statements, rolled back.
- **Unblocks:** every import path. Until it runs, `file_import` is not a valid capture source
  and `tools/import_drop.py` cannot commit anything.
- **Success condition, observable:**
  ```bash
  PYTHONPATH=. python3 -c "
  from lib import db; c=db.connect(); cur=c.cursor()
  cur.execute(\"select count(*) from pg_enum e join pg_type t on t.oid=e.enumtypid
                where t.typname='capture_source' and e.enumlabel='file_import'\")
  print('file_import present:', cur.fetchone()[0]==1)"
  ```
  prints `True`.

## 2. Apply migration 0052 (the shared model budget)

- **Owner:** Joe. Same permission boundary.
- **Command:** as above with `--only 0052`.
- **Unblocks:** any Workers AI call. `lib/egress.py` refuses without the ledger.
- **Success condition:** `select * from core.neuron_budget(1, false)` returns a row with
  `ceiling = 9000`.

## 3. Export the data that recovers the gap

- **Owner:** Joe. Needs your devices.
- **Apple Health:** Health app → your profile picture (top right) → **Export All Health Data**
  → AirDrop `export.zip` to the Mac → put it in `~/PersonalOS_Drop/`.
- **Google Takeout:** takeout.google.com → **deselect everything**, then select **Chrome** and
  **YouTube and YouTube Music** only. *Not* Location History — the importer refuses those
  members by name (REQ-LOC-005) and selecting them only makes the download larger.
- **Then:**
  ```bash
  PYTHONPATH=. python3 tools/import_drop.py --since 2026-07-28            # counts only, writes nothing
  PYTHONPATH=. python3 tools/import_drop.py --since 2026-07-28 --commit   # writes, moves to _done/
  ```
- **Unblocks:** the 43-day gap in sleep, HRV, respiratory rate, SpO2, browsing and viewing.
- **Success condition:** the dry run prints a non-zero `atoms_written` per file, and afterwards
  `tools/check_freshness.py` moves metrics out of `stale`. Paste the **counts only** — never
  contents.
- **Note:** re-dropping a file is free (SHA-256), and re-exporting an overlapping period is
  free (per-atom dedupe). Depends on item 1.

## 4. Restart live capture

- **Owner:** Joe. Needs your phone.
- **Check:** in **Health Auto Export**, which metrics are selected and on what schedule. It is
  posting today but only daily aggregates — steps, flights, walking metrics — not the
  **intraday samples** (`hr`, `hrv_window`, `spo2`, `sleep_stage`, `resp_rate`) that
  `apple_sleep` / `apple_hrv` / `apple_circadian` / `apple_vitals` are derived from. That is
  why those four feeds are dead while the app looks fine.
- **Check:** whether **OwnTracks** is still running and posting. `public.locations` stopped
  2026-07-29.
- **Unblocks:** continuous capture. Item 3 recovers history; only this restarts the feed.
- **Success condition:** `public.intraday` gains rows dated after today, and
  `tools/check_freshness.py` shows the derived feeds recovering over the following days.
- **Open question:** OQ-50 — the proximate cause is not established; the old stack's ingest
  code is not in this repository.

## 5. Rule OQ-51 — two mis-wired canonical metrics

- **Owner:** Joe. These are claims about data, which `CLAUDE.md` forbids a session deciding.
- **(a)** `steps` reads `health_history.steps`, dead since 2026-06-23, while
  `apple_watch.steps` arrives daily. **Is a Watch-derived daily count the same measurement as
  the backfilled historical one?** If yes, `SIG_CANON` takes a precedence list and the level
  shift over the overlap must be measured and reported. If no, it needs a new canonical name.
- **(b)** `screen_active_hours` reads `attention.active_hours`, which has **never existed** —
  that canonical metric has zero panel rows, ever. The nearest real metric is
  `attention.screen_active_min`: different name **and** different unit. Is it the same
  measurement, and is ÷60 the right conversion?
- **Unblocks:** canonical `steps` has been blind since June; `screen_active_hours` has never
  had a value.
- **Success condition:** a one-line ruling per metric, which becomes an ADR and a `panel.py`
  change with the overlap shift reported.

## 6. Rule OQ-48 — the four `screen_*` thresholds

- **Owner:** Joe.
- **Question:** `screen_active_hours`, `screen_binge_min`, `screen_max_binge`,
  `screen_sessions` are session-level statistics whose definitions — the inactivity gap that
  ends a session, the length that makes a binge — live in the old stack's code, which is not in
  this repository. Recover them, or rule new ones?
- **The trade:** new thresholds mean a series that steps at the changeover while keeping the
  historical name. Continuity versus correctness.
- **Unblocks:** re-deriving those metrics from `web_visit` / `media_play` atoms.

## 7. Rule OQ-53 — what a day is

- **Owner:** Joe.
- **Question:** `analysis.panel` rows from `public.signals` are grouped by `ts::date` (UTC);
  rows from `core.atoms` by `subject_day` (04:00 ET). A visit at 22:00 ET is one day under one
  rule and the previous day under the other.
- **Why it matters beyond attention:** it affects every metric that crosses the old/new stack
  boundary, so it is larger than it looks.
- **Unblocks:** removing the seam at the join. B13 avoided the immediate consequence by making
  atom-derived counts fill only days signals never covered (ADR-0058 §4).

---

## Also outstanding, lower urgency

**OQ-47 — the GitHub default branch is `v2-day1` while the work is on `main`.** Owner: Joe
(repository setting). Affects whether scheduled workflows run the current code. Success
condition: `gh repo view --json defaultBranchRef` reports the intended branch.

---

## What I will do while these are held

Continue M2's open contracts and the M3/M4 dependency order in `docs/EXECUTION_PLAN.md`.
None of it is blocked by anything above. **None of it moves the 0-of-17 number.**
