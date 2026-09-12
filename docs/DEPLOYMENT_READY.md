# Deployment — the exact actions, in dependency order

Prepared at `38d42ea`, 2026-09-11. **Nothing here has been executed.** Each step names what
authorization it needs and how to verify it afterwards. The order matters and is not cosmetic:
steps 2 and 3 taken in the wrong order turn the nightly red.

**Existing authorization reconciled first.** The last recorded grant covered the six migrations
0056–0061 and was never exercised; the frontier has since moved to **0055–0074**, and 0070–0074
were written after that grant. So the grant does not cover the current action and is not treated
as if it did. Nothing below is executed on the strength of a previous session's approval.

---

## Step 0 — verify the pending stack against production (rolled back)

```bash
PYTHONPATH=. python3 tools/verify_pending_stack.py
```

Applies every pending migration in ONE transaction against the real database, exercises the
stack, and rolls back. It last reported **STACK VERIFIED — 20 of 20** across 0055–0069;
**0070–0073 have never been through it.**

**Authorization: NOT REQUESTED AND NOT RUN.** This issues DDL against production, and the
evidence worker has just finished removing eight test modules that did exactly that behind a
rollback (OQ-78) — where the rollback held and it was still production core being written. A
rolled-back DDL transaction is not a SELECT, so it is not covered by the standing permission for
read-only work. Joe's call whether to run it before step 1 or to rely on the from-empty chain
check, which passes at 72 migrations / 589 statements and needs no production at all.

## Step 1 — apply migrations 0055–0074

```bash
for m in migrations/00{55..74}_*.sql; do
  PYTHONPATH=. python3 tools/run_migration.py "$m" --commit
done
PYTHONPATH=. python3 tools/backfill_transactions.py --core core --commit   # 1,052 legacy rows
PYTHONPATH=. python3 tools/resolve_merchants.py --commit                   # 616 paid_to links
PYTHONPATH=. python3 tools/engines/categorise.py --commit                  # 88 category rules
```

**Authorization required: production write.** Nineteen migrations plus three population steps.

Verify — and "the object exists" is not the verification:

```bash
PYTHONPATH=. python3 -c "
from lib import db; c=db.connect(); cur=c.cursor()
cur.execute(\\"select method_key, event_family from config.reconstruction_methods order by 1\\")
print('methods:', cur.fetchall())   # expect watch_non_wear, sleep_gap_explained,
                                    #        training_session, service_usage
cur.execute(\\"select count(*) from core.atoms where kind='transaction'\\")
print('transaction atoms:', cur.fetchone()[0])   # expect 1052
"
```

## Step 2 — import the workout history (R2)

```bash
cp /Users/default/Downloads/_done/export.zip ~/PersonalOS_Drop/
PYTHONPATH=. python3 tools/import_drop.py                      # inspect, writes nothing
PYTHONPATH=. python3 tools/import_drop.py --commit
PYTHONPATH=. python3 tools/reconstruct_run.py --method training_session          # dry run
PYTHONPATH=. python3 tools/reconstruct_run.py --method training_session --commit
```

**Authorization required: production write.** Must follow step 1 — `workout_session_min` has no
`core.metric_registry` row until 0070 is applied, and `atoms_metric_key_fkey` will refuse every
atom without it.

Expected, measured on a disposable server against this exact file: **93 workout atoms, 32
training-session events, 2023-02-22..2026-08-21, all DESCRIPTIVE, 0 strength set atoms, 0
`did_not_occur` rows.** Any other numbers mean something differs and should stop the sequence.

Note this reaches back to 2023-02-22, well outside the 2026-07-01 recovery window, because that
is where the training history is. `--since` still bounds it if Joe wants it narrower.

## Step 3 — publish the workflows

**This is the step that makes anything scheduled actually run, and it must come AFTER step 1.**
The nightly `analysis.yml` on this branch runs `reconstruct_run.py --all-methods --commit` and
`ops/clarification_prompts.py --commit`. Published before the migrations are applied, both are
clean no-ops by design; published after, they do real work. Published while the migrations are
half-applied, they fail.

```bash
git push origin HEAD:v2-day1        # v2-day1 IS the default branch
```

**Authorization required: push to the default branch.** This is the only option that works:

- **Not** `gh api -X PATCH repos/:owner/:repo -f default_branch=main`. `main` is at
  `b606c64` — migration **0048** against this branch's **0073**. Switching the default there
  would make `tests.yml`'s cron fire against B10-era code, which is worse than not firing.
- `v2-day1` is `4d86bd8` and carries five workflow files. This branch carries eight.

**No default-branch change is made automatically, and none is proposed.**

Verify — a `workflow_dispatch` run proves only that the file parses:

```bash
gh api repos/:owner/:repo/actions/workflows --jq '.workflows[] | "\(.name) \(.state)"'
gh workflow run freshness.yml && sleep 90 && gh run list --workflow=freshness.yml --limit 1

# THE ONLY ONE THAT COUNTS — the next morning, a row it wrote itself on its own schedule:
PYTHONPATH=. python3 -c "
from lib import db; c=db.connect(); cur=c.cursor()
cur.execute(\\"select finished_at, status from ops.runs where job_name='check_freshness'
              order by finished_at desc limit 3\\")
print(cur.fetchall())"
```

GitHub does not index a workflow whose only triggers are `schedule` and `workflow_dispatch`
when it merely rides along in a bulk push — `keepalive.yml`'s own header records this happening.
A push that *modifies* the file forces a re-scan, and `freshness.yml` carries such a
modification at this revision.

## Step 4 — activate the local import schedule

The drop folder is on Joe's Mac; no GitHub runner can read `~/PersonalOS_Drop`. Full steps are
in `docs/CAPTURE_ACTIVATION.md` §3. In short:

```bash
mkdir -p ~/PersonalOS_Drop
mkdir -p ~/.config/personal_os
printf 'SUPABASE_DB_URL=%s\n' "\$SUPABASE_DB_URL" > ~/.config/personal_os/env
chmod 600 ~/.config/personal_os/env    # the scheduler REFUSES a group- or world-readable file
PYTHONPATH=. python3 ops/capture_schedule.py --preflight   # writes nothing
PYTHONPATH=. python3 ops/capture_schedule.py --emit-launchd > ~/Library/LaunchAgents/com.personalos.import.plist
launchctl load ~/Library/LaunchAgents/com.personalos.import.plist
```

**Joe performs this.** ADR-0094 keeps activation a separate human act because the first firing is
a production write, and `--emit-launchd` deliberately installs nothing and sets
`RunAtLoad: false`.

---

## What is still NOT deployable after all four steps

- **The capture ingest endpoint has no HTTP host.** `tools/engines/ingest_endpoint.py` implements
  the whole REQ-CAP-003..018 contract and nothing serves it, so nothing can POST a capture.
  Engineering work, assigned to Worker 3 — not a deployment gate.
- **Web Push does not exist** (REQ-CAP-092), so `delivered_at` in `core.prompt_dispatch` stays
  NULL. Prompts are scheduled and never delivered. Joe has not been asked anything.
- **The USDA legs** need `USDA_FDC_API_KEY`. The cascade is built; no request has ever been
  issued to api.data.gov.
- **No set has ever been logged**, so `strength.py` stays idle after step 2. Step 2 delivers the
  session history, not the sets.
