# Capture activation — what is built, what is running, and the exact steps between

Prepared 2026-09-11 in `work/capture-finish`. Every claim below is measured at this revision;
where something was read from production or from GitHub, the command that read it is given so
it can be re-run rather than believed.

Companion to **ADR-0141**. `docs/CAPTURE_ACTION_PACKET.md` (2026-09-09) is partly superseded:
its items 1 and 2 — migrations 0051 and 0052 — **are applied**, confirmed below.

---

## 1. What is actually true today

| | state | how it was measured |
|---|---|---|
| migrations 0051 / 0052 / 0053 / 0054 | **applied** | `file_import` is in the `capture_source` enum; `core.neuron_ledger`, `config.source_inventory`, `core.inferred_events` all exist |
| migration 0069 | **not applied** | `core.inferred_events` has no `discriminating_evidence` column; `public.get_reconstruction` does not exist |
| `tools/import_drop.py` | **run once, by hand** | one `ops.runs` row, 2026-09-09 22:35 UTC, 33,355 atoms, one file |
| `ops/capture_schedule.py` | **never run** | zero `ops.runs` rows under `capture_schedule`. The launchd agent is not installed |
| `tools/check_freshness.py` | **run once, by hand** | one `ops.runs` row, 2026-09-09 22:40 UTC: 9 fresh / 17 stale / 11 never seen / 6 unmonitored |
| the `freshness` workflow | **has never existed on GitHub** | see §2 — this is the important one |
| `core.prompt_dispatch` | **empty, and until now had no writer** | 0 rows |
| capture sources with any row | `file_import` (1, 2026-09-09), `shortcut_text` (3, 2026-08-01) | `core.raw_captures` grouped by source |

```bash
# re-run the production probe (SELECT only)
PYTHONPATH=. python3 - <<'PY'
from lib import db
c = db.connect(); cur = c.cursor(); cur.execute("SET TRANSACTION READ ONLY")
cur.execute("""select job_name, count(*), max(finished_at)::date from ops.runs
               group by 1 order by 1""")
for r in cur.fetchall(): print(r)
PY
```

---

## 2. The finding that matters most: the alarm has never run

`.github/workflows/freshness.yml` is the single mechanism built to stop a repeat of the
2026-07-28 failure, where every scheduled job wrote `status='ok'` for 43 days while its inputs
were dead. **It has never fired on a schedule.** Not once.

```bash
gh api repos/:owner/:repo/actions/workflows --jq '.workflows[].path'
#   analysis.yml extract.yml gates.yml keepalive.yml pages.yml tests.yml   <- no freshness.yml

gh api repos/:owner/:repo --jq '.default_branch'
#   v2-day1

gh api "repos/:owner/:repo/contents/.github/workflows?ref=v2-day1" --jq '.[].name'
#   analysis.yml extract.yml gates.yml keepalive.yml pages.yml            <- five files

gh api repos/:owner/:repo --jq '.pushed_at'
#   2026-09-03T01:30:20Z
```

The cause is not the file's contents. GitHub delivers `schedule` events **only from the
repository's default branch**, the default branch is `v2-day1`, and `freshness.yml` has never
reached it. Neither has `tests.yml`, so the nightly suite's cron does not fire either — it
appears in the workflow list, but a listed workflow whose file is absent from the default
branch receives no scheduled event.

So the thing built to detect silent failure failed silently, and nothing in the repository could
tell the difference. That is the same class of error it exists to catch, one level up, and it is
why "tested" and "deployed" are kept apart in this project's vocabulary.

**This is a deployment act and is not the capture worker's to perform.** Two ways to fix it, for
the integration owner:

```bash
# EITHER: make the branch that carries the workflows the default (Joe or an admin token)
gh api -X PATCH repos/:owner/:repo -f default_branch=main

# OR: put the file on the branch GitHub already treats as default
git push origin <branch-carrying-freshness.yml>:v2-day1
```

Then verify — and the verification is **not** "the file exists":

```bash
# 1. GitHub has indexed it
gh api repos/:owner/:repo/actions/workflows --jq '.workflows[] | "\(.name) \(.state)"' | grep freshness

# 2. it can be made to run at all
gh workflow run freshness.yml && sleep 90 && gh run list --workflow=freshness.yml --limit 1

# 3. THE ONLY ONE THAT COUNTS — a row it wrote itself, on its own schedule, the next morning
PYTHONPATH=. python3 -c "
from lib import db; c=db.connect(); cur=c.cursor()
cur.execute(\"select finished_at, status, detail->'counts' from ops.runs
              where job_name='check_freshness' order by finished_at desc limit 3\")
[print(r) for r in cur.fetchall()]"
```

A `workflow_dispatch` run proves the file parses. Only a `schedule` run proves the alarm exists.

**Registration caveat, already learned once here.** GitHub does not index a workflow whose only
triggers are `schedule` and `workflow_dispatch` when it merely rides along in a bulk push;
`keepalive.yml`'s header records this happening to it. A push that *modifies* the file forces a
re-scan. `freshness.yml` carries such a modification at this revision, so the next push of it
registers it.

---

## 3. Activating the local import schedule

The drop folder is on Joe's Mac. No GitHub-hosted runner can read `~/PersonalOS_Drop`, so this
schedule is local and on macOS that means launchd. ADR-0094 keeps activation a separate human
act because the first firing is a production write.

**Prerequisites, in order. Each has a check that fails loudly rather than guessing.**

```bash
# a. the drop folder exists. The scheduler will NOT create it: scheduling an importer does not
#    make a device produce an export, and creating the folder would turn the prerequisite most
#    likely to be wrong into a silently satisfied one.
mkdir -p ~/PersonalOS_Drop

# b. the credential, outside the repository, readable by nobody else. A launchd agent inherits
#    no login shell, so the variable must be in a file it can read.
mkdir -p ~/.config/personal_os
printf 'SUPABASE_DB_URL=%s\n' "$SUPABASE_DB_URL" > ~/.config/personal_os/env
chmod 600 ~/.config/personal_os/env        # the scheduler REFUSES a group- or world-readable file

# c. prerequisites only — imports nothing, writes nothing
cd ~/PERSONAL_OS_V2 && PYTHONPATH=. python3 ops/capture_schedule.py --preflight
#    expect: capture_schedule: preflight ok  drop=...  pending_files=N  ready=N
#            still_arriving=0  credential=env_file

# d. the whole path against the real database, rolled back. Nothing is committed and no file
#    moves to _done/.
PYTHONPATH=. python3 ops/capture_schedule.py --run --dry-run
#    expect: capture_schedule: dry_run  ...  new_data=no
```

**Install the agent.** `--emit-launchd` prints the job description and installs nothing; the
plist deliberately carries no credential, because a file in `~/Library/LaunchAgents` is
world-readable by default and is exactly the kind of file that gets pasted into a gist when
something breaks.

```bash
cd ~/PERSONAL_OS_V2
PYTHONPATH=. python3 ops/capture_schedule.py --emit-launchd \
  > ~/Library/LaunchAgents/com.personalos.import.plist
plutil -lint ~/Library/LaunchAgents/com.personalos.import.plist

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personalos.import.plist
launchctl enable  gui/$(id -u)/com.personalos.import
launchctl print   gui/$(id -u)/com.personalos.import | head -20
```

`RunAtLoad` is false, so bootstrapping the agent does **not** perform an import — installing a
scheduler and starting one are separate acts. To make it fire once, deliberately:

```bash
launchctl kickstart -p gui/$(id -u)/com.personalos.import
```

**Verification. The only evidence that counts is a row the job wrote itself.**

```bash
PYTHONPATH=. python3 -c "
from lib import db; c=db.connect(); cur=c.cursor()
cur.execute(\"select job_name, finished_at, status, rows_written, detail->>'outcome',
                    detail->>'new_data'
               from ops.runs where job_name in ('capture_schedule','import_drop')
              order by finished_at desc limit 5\")
[print(r) for r in cur.fetchall()]"
```

Read the two columns separately and never as one sentence:

* `status='ok'` with `new_data=false` and `outcome='no_new_files'` — **the job worked and
  capture did not happen.** That is a success of the schedule and a failure of capture, and it
  is the exact pair of facts that went unnoticed for 43 days.
* `outcome='files_still_arriving'` with `status='error'` — a file is stuck mid-copy. It was not
  imported, it is still in the drop folder, and the next run retries it.
* `unrecognised=N` on the summary line — a file the importer does not recognise is sitting in
  the folder being ignored. Check the name: `export.xml`, `*_export.xml`, `export.zip`,
  `Takeout*.zip`, or `.csv`/`.qfx`/`.ofx`/`.qbo`. `health.xml` and `statement (1).csv` are not.

The per-file log, which does contain file names, stays on the Mac at
`~/PersonalOS_Drop/_state/schedule.log` and is never committed (RULE-29).

**To uninstall:** `launchctl bootout gui/$(id -u)/com.personalos.import` and delete the plist.

---

## 4. What Joe has to do on a device — the minimum list

Nothing in §3 produces data. These do, and nothing else can substitute for them: an importer
cannot generate an export that the phone never produced.

1. **Export Apple Health.** Health app → profile picture → *Export All Health Data* → Save to
   Files, then move `export.zip` into `~/PersonalOS_Drop/`. Roughly 10 minutes to generate; it
   is large. This is the only thing that recovers the sleep, HRV and vitals since the Watch
   stopped on 2026-08-21, and the export is the whole history, so one is enough.
2. **Export the bank statements for 2026-05-13 → today.** The CSV export died on 2026-05-13 and
   `chase_email` has carried roughly a third of the transactions since. Download the CSVs and
   drop them in the same folder. 38 days have no transaction at all and only this closes them.
3. **Answer OQ-55 about the Watch** — worn / paired / permissions / storage. Seventeen stale
   metrics are downstream of it and no code can determine which of those four it is.
4. **Install the Log Workout shortcut** (`docs/CAPTURE_SHORTCUT.md`). `tools/extract_workouts.py`
   runs clean and writes nothing because no set has ever been logged; B18's strength engine is
   correct and idle for the same reason. Strength is the stated primary objective.
5. **Choose a clarification prompt time** — see §5.

Copying a large export into the drop folder is now safe at any moment: a file still being
written is held back and reported rather than half-imported (ADR-0141).

---

## 5. Clarification prompts (REQ-REC-015)

`ops/clarification_prompts.py` turns a reconstruction with competing alternatives and stored
discriminating evidence into one `core.prompt_dispatch` row, under RULE-27: one per subject per
day, a dismissed subject never asked again, no duplicate while a prompt is open, and a shared
daily ceiling of three.

It writes nothing today, for two independent reasons, and both are stated rather than worked
around:

1. **Migration 0069 is not applied**, so `core.inferred_events.discriminating_evidence` does not
   exist in production and there is nothing to ask about. That is main's to apply (OQ-77).
2. **`--at` is Joe's decision.** The command refuses `--commit` without it: REQ-CAP-087 forbids
   a randomly chosen time, and RULE-27 records 81% compliance for scheduled morning prompts
   against 52% for random pings. **Recommendation: `--at 09:00`.**

```bash
PYTHONPATH=. python3 ops/clarification_prompts.py                 # plan only; writes nothing
PYTHONPATH=. python3 ops/clarification_prompts.py --at 09:00 --commit
```

**A scheduled prompt is not a delivered one.** `delivered_at` stays NULL because REQ-CAP-092
names Web Push and Web Push is not built. A row means the question is due to be asked. Nothing
in this system has asked Joe anything yet, and no row here should be read as saying otherwise.

It has no caller in any workflow. Wiring it into the nightly `analysis` workflow is a one-step
change to a file the integration owner owns, and it is a production write, so it is not made
here.

---

## 6. Proving the path without touching production

```bash
python3 tools/capture_acceptance.py          # ten cases, real processes, disposable server
python3 tools/capture_acceptance.py --list
```

It starts its own PostgreSQL 17 server with TCP disabled, builds `core_dryrun`/`ops_dryrun`,
runs the real `capture_schedule.py` and `import_drop.py` as separate processes, destroys the
instance, and exits non-zero if any case fails. It needs PostgreSQL 17 locally and says so if it
is absent. `.github/workflows/capture-acceptance.yml` runs it on any push that touches the
capture path.

---

## 7. Software versus observation — what is left

**Software, and someone can just write it:**

* device-level source loss (Watch vs iPhone) — `check_freshness` sees the ingress channel, not
  the instrument. Closing it means naming instruments from stored configuration rather than
  parsing `evidence_span`, which is a migration. ADR-0141, batched question 3.
* a stored acknowledgement for a deliberately-quiet source, so `source_quiet` could fail the
  run instead of only reporting. ADR-0141, batched question 2.
* a caller for `ops/clarification_prompts.py`.
* the B16 media path — Storage bucket, the `capture-media` Edge Function, transcription. The
  pure engines exist (`vision_and_prompts.py`, `capture_budget.py`, `capture_resilience.py`) and
  nothing calls them. `core.neuron_ledger` is applied and empty.

**Observation, and no amount of code substitutes for it:**

* an export in the drop folder (§4.1, §4.2);
* the launchd agent installed and one unattended firing recorded (§3);
* `freshness.yml` on the default branch and one row written by a `schedule` event (§2);
* a workout logged, which is what makes B18 stop being idle.
