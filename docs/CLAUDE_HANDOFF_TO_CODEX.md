> Historical reference. Current work order: [EXECUTION_PLAN](EXECUTION_PLAN.md).
> Current evidence: [NEXT_SESSION](NEXT_SESSION.md). Requirements and accepted gates
> remain binding; historical status and scheduling instructions do not govern execution.

# HANDOFF — Claude → Codex

**Written** 2026-09-06 by Claude (Opus 5), at Joe's instruction, for the agent taking over
implementation in `/Users/default/PERSONAL_OS_V2`.

**Purpose.** Diagnose why progress has stalled. This is not a design document and it does not
propose architecture. It records what is true, what is only claimed, and where the two diverge.

---

## 0. How to read this document

Every claim below is tagged:

- **[OBSERVED]** — I ran the command or query in this session (2026-09-06, 14:00–14:45 UTC) and
  read the output. The command is given so you can re-run it.
- **[REPO]** — recorded in the repository (`ops/PROGRESS.md`, an ADR, a spec) by a previous
  session. I did not independently re-verify it. Treat as a prior session's testimony.
- **[INFERRED]** — my reasoning from observed facts. Could be wrong. Reasoning is shown so you
  can attack it.
- **[UNKNOWN]** — I could not determine this and did not guess.

**A correction you need before anything else.** Joe's brief for this document assumed I was
mid-implementation and blocked on a failing step. **I was not.** [OBSERVED] This session
contained exactly one prior user message — a request for project status — and I did no
implementation work at all. I did not write code, run a migration, or commit anything.

So the honest answer to "the exact step you are stuck on" is: **there is no failing command.**
Every gate I ran is green. The stall is not a broken build. It is three structural problems that
green gates cannot see, documented in §3. If you go looking for a stack trace to fix, you will
not find one, and you will waste the session. **Nothing in this document is a report of a
command that failed for me.**

The last agent that *did* implement work was "session 20" on 2026-09-02 (four days ago). It
finished B10 cleanly and committed. Its own account is `ops/PROGRESS.md` from line 5086.

---

## 1. What Joe was most recently trying to finish

### The stated goal, in his own ordering

[REPO] `CLAUDE.md` records a ruling of 27 Aug that overrides the roadmap's phase order:

> get continuous unattended capture running before the Claude subscription ends — data can only
> be collected once, code can be written anytime.

[REPO] `docs/REMEDIATION_PLAN.md` "TRACK 0" says the same thing more bluntly: *"Zero workouts.
Zero food. Three self-reports total... No phase of this build fixes that, and nothing can
backfill it... This is the single highest-value action available to you and it does not require
the terminal."*

### The mechanism he chose to get there

[REPO] `docs/build/README.md` defines a chain of 24 build orders, B0 → B23, one per session, each
producing one migration. Joe drives it by pasting a fixed line per session. There is also a
parallel "L" chain (L0–L8) for the Lovable front end, which needs no agent.

[OBSERVED] The chain's progress, from `git log`:

| File | Commit | Migration | State |
|---|---|---|---|
| B0–B7 | various, 2026-09-02 | 0034–0044 | committed, live |
| B8 | `552a611` | 0045 | committed, live |
| B9 | `2d829b9` | 0046 | committed, live |
| B10 | `b606c64` | 0047, 0048 | committed, live |
| **B11** | **none** | **0049** | **drafted only — see §7** |
| B12–B23 | none | 0050–0065 | not started |

**So: Joe was most recently trying to finish B11 — "Ask", a question in, a traced and tiered
answer out.** [OBSERVED] `docs/build/B11_ask.md` (11,535 bytes) splits it into B11.1 (the
deterministic core, no model on the path) and B11.2 (a Cloudflare Workers AI language layer with
the deterministic parser as fallback). Only B11.1 was started.

[OBSERVED] All ten B-file commits are dated **2026-09-02**. B0 through B10 — ten build orders and
fifteen migrations — were completed in a single day. B11 was started the same day and abandoned
part-way. **Nothing has been committed in the four days since.**

[INFERRED] The chain was being run at very high throughput and stopped mid-file. The most likely
cause is the session ending (context exhaustion, or Joe stopping) rather than a blocking defect,
because the drafted SQL is complete and valid (§7 proves it applies). I cannot confirm this —
there is no PROGRESS entry for B11. **[UNKNOWN] Why the B11 session actually stopped.** Ask Joe;
he was there.

---

## 2. The exact state of the working tree

[OBSERVED] `git status --short`:

```
?? migrations/0049_ask_core.sql
```

That is the entire diff. One untracked file. No modified files, no staged files, **no stash**
(`git stash list` is empty). `main` is at `b606c64` and is identical to `origin/main` — nothing
unpushed.

[OBSERVED] Local gates, run this session:

```
$ python3 tools/validate_layout.py
41 passed, 0 warnings, 0 failed

$ PYTHONPATH=. python3 tools/check_invariants.py --core core
INVARIANTS: ALL PASS
  [RULE-04] PENDING — derived_measures does not exist yet (Phase 5); not a failure this phase.
```

[REPO] Last full suite (session 20, B10): `update_features.py --strict` → **134 passed, 0 failed,
0 errors, 0 skipped of 134**. [OBSERVED] The corresponding CI run on `main` (`33703906685`,
2026-09-03) is green.

**This is the trap.** Everything reports healthy. The problems in §3 are all invisible to every
check that exists.

---

## 3. The three real reasons progress has stalled

### 3.1 The data the system reasons about stopped arriving on 27–28 July 2026

This is the most important section in this document.

[OBSERVED] `analysis.panel`, grouped by source, last day with data (today is 2026-09-06):

| Source | Last day | Days stale | Metrics |
|---|---|---|---|
| `signals:weather` | 2026-09-06 | 0 | 21 |
| `signals:engine` | 2026-09-05 | 1 | 68 |
| `signals:gmail` | 2026-09-05 | 1 | 6 |
| `signals:apple_watch` | 2026-09-04 | 2 | 35 |
| `signals:attention` | 2026-09-02 | 4 | 16 |
| `signals:withings` | 2026-08-23 | 14 | 12 |
| `signals:github` | 2026-08-05 | 32 | 13 |
| `signals:apple_load` | **2026-07-28** | **40** | 7 |
| `signals:information` | **2026-07-28** | **40** | 21 |
| `signals:apple_sleep` | **2026-07-28** | **40** | 24 |
| `signals:apple_vitals` | **2026-07-28** | **40** | 7 |
| `signals:apple_circadian` | **2026-07-28** | **40** | 11 |
| `signals:apple_hrv` | **2026-07-28** | **40** | 20 |
| `signals:apple_gait` | **2026-07-27** | **41** | 5 |
| `signals:spend` | **2026-07-27** | **41** | 9 |
| `signals:mobility` | 2026-07-24 | 44 | 7 |
| `signals:checkin` | 2026-07-22 | 46 | 3 |
| `signals:health_history` | 2026-06-24 | 74 | 25 |

[OBSERVED] `public.intraday`, every series, last timestamp:

```
hr            2026-07-28 13:48    hrv_window  2026-07-28 13:30
spo2          2026-07-28 11:36    sleep_stage 2026-07-28 10:34
resp_rate     2026-07-28 09:43    rhr         2026-07-28 04:51
walking_*     2026-07-27 23:29
```

[OBSERVED] `public.ingest_status`:

```
owntracks           last_ingest 2026-07-29 23:21    (location — dead 38 days)
health_auto_export  last_ingest 2026-09-05 04:09    (alive)
```

**What this means.** [INFERRED, high confidence] A single event on 27–28 July killed sleep, HRV,
vitals, circadian, gait, intraday (heart rate, SpO2, sleep stages, respiration), browsing/media,
and spend — simultaneously. Six or seven independent feeds do not fail on the same day by
coincidence. One credential, device setting, export configuration, or automation stopped.

**A specific diagnostic lead.** [OBSERVED] `health_auto_export` is *still ingesting* (5 Sep), and
`apple_watch` step/gait aggregates are fresh to 4 Sep — but `apple_sleep`, `apple_hrv`,
`apple_vitals` and `apple_circadian` from the same pipeline all stop dead on 28 July.
[INFERRED] The transport is alive and the payload shrank. That points at the Auto Export app's
selected data types on the phone, or at a parser that silently stopped mapping those types —
**not** at a dead credential. Check the phone's export configuration first; it is free to check.

**A trap in the ingest log.** [OBSERVED] `signals:apple_load` and `signals:apple_gait` show
`max(ingested_at)` of 2026-09-01 but `max(ts)` of 2026-07-27/28. That is the `legacy_daily_load`
backfill re-reading old rows. **A freshness check written against `ingested_at` will report these
feeds healthy.** Use `max(ts)`, always.

**Why this is the stall and not just a bug.** The B7–B10 machinery (watch resolver, promotion
gate, confirmation gate, recommendations) reasons over `analysis.panel`. Its personal signal is
now step counts, email counts and *the weather* — and the weather is an external API, not Joe.
[REPO] The 37 registered candidate hypotheses are written against drivers like sleep and HRV.
[INFERRED] The inference layer cannot produce a finding because its inputs are gone, and B12–B23
would add ~13 more sessions of engine on top of the same empty panel.

**Nothing alerted.** [REPO] `docs/ROADMAP.md` places staleness alerting at Phase 4 / Gate 4 —
after the analysis layer that consumes the feeds. [INFERRED] That ordering is the direct cause of
six weeks of silent loss. It should be inverted.

### 3.2 The scheduled jobs run stale code, because the default branch is not `main`

[OBSERVED]:

```
$ gh repo view --json defaultBranchRef
{"defaultBranchRef":{"name":"v2-day1"}}

$ gh api repos/:owner/:repo/commits/v2-day1
4d86bd8  2026-09-02T19:50:04Z  docs/build: add B8–B23 to the build pack

$ gh api repos/:owner/:repo/compare/v2-day1...main
{"ahead":3,"behind":0,"status":"ahead"}
```

**The default branch is `v2-day1`, three commits behind `main`. The three missing commits are
B8, B9 and B10.** GitHub fires `schedule:` triggers only on the default branch, so every nightly
job runs the pre-B8 versions of the workflow files.

Two confirmed consequences:

**(a) The confirmation gate and the recommendations generator are not running.** [OBSERVED] Steps
in the most recent nightly `analysis` run (`34032337149`, 2026-09-06 12:10):

```
panel + baselines refresh                      -> success
weekly contrast scan (Mondays; ...)             -> success
resolve matured watches                         -> success
(no confirmation gate step)
(no recommendations step)
```

Those two steps exist only in `main`'s `.github/workflows/analysis.yml`. Corroborated in the
database — [OBSERVED] `ops.runs` grouped by job:

```
confirm_gate   n=1   last 2026-09-02 23:11
recommend      n=1   last 2026-09-02 23:48
```

One run each — the manual runs the B9 and B10 sessions performed during the build. **B9 and B10
have never executed unattended.**

**(b) The nightly test suite has never fired.** [OBSERVED] `.github/workflows/tests.yml` carries
`cron: '0 9 * * *'`, added in B8's commit. `gh run list --workflow tests.yml` returns exactly
three runs, all `push`, none `schedule`. The full suite runs only when someone pushes.

[OBSERVED] The fix is `gh repo edit --default-branch main`. **[UNKNOWN] Whether `v2-day1` is the
default deliberately.** I did not change it — it is outward-facing on a public repo and is Joe's
call. Ask before flipping it.

### 3.3 Everything built in B6–B10 has zero live subjects

[OBSERVED]:

```
core.hypothesis_register  ->  37 CANDIDATE, 0 PROMOTED, 0 CONFIRMED_OBSERVATIONAL
analysis.watch_progress   ->  0 rows
core.findings             ->  0 rows
core.recommendations      ->  0 rows
core.raw_captures         ->  3 rows, all processing_status='received',
                              captured 2026-07-22 .. 2026-08-01
core.atoms                ->  5 rows
core.entities             ->  0 rows
restricted.location_fixes ->  0 rows
```

[REPO] B9's PROGRESS entry states the first live confirmation "cannot happen before ~November
2026" — a watch needs ~61 paired days to promote, then ~60 more to confirm.

[OBSERVED] **That clock has not started.** It starts when a watch is registered, and
`analysis.watch_progress` is empty. No watch has ever been registered. [INFERRED] Every "~November
2026" date in the repository is therefore optimistic by however long it takes Joe to register a
first watch — and a watch cannot mature on feeds that stopped in July.

[OBSERVED] The Overland location receiver was deployed on 2 Sep with its token set, and has
received **zero** fixes in four days. [INFERRED] It was deployed but never configured on the
phone, or the token was never entered. [REPO] This is consistent with OQ-44(k), which records
that Joe was to configure Overland and rotate the token.

---

## 4. What was tried, what happened, and why each attempt failed

These are prior sessions' attempts, from `ops/PROGRESS.md`. I did not re-run them. They are here
because each one is a live constraint you will hit again.

### 4.1 DoWhy cannot be installed — the refutation tests are hand-rolled

[REPO] B9 (session 20). `pip install dowhy` fails. Every DoWhy release requires Python `<3.14`;
the only interpreter on this machine is **3.14.3**. It would install on the GitHub runner (3.12),
which would put the check only where Joe cannot run it — and Joe verifies by running.

**Resolution taken:** three refuters reimplemented in `tools/engines/confirm.refuters` over the
same HAC estimator, deterministic and seeded (ADR-0051 §6). The test named for DoWhy was renamed
rather than left lying. **Consequence:** REQ-TIER-013's DoWhy clause is satisfied *in intent, not
in implementation*. [INFERRED] If you touch the confirmation gate, do not "fix" this by adding
DoWhy — you will break the local run. The Python version is the binding constraint.

### 4.2 `window` is a reserved word in PostgreSQL

[REPO] B9's `analysis.spec_curves` DDL declared a column named `window`. `CREATE TABLE` failed to
parse; 21 twin-based tests errored. Renamed `window_spec`. Recorded in ADR-0050.

### 4.3 The twin fixture applies *every* file in `migrations/`, including uncommitted ones

[REPO] This bit twice, in consecutive sessions.

- B8's suite run was contaminated because B9's `0046` was already sitting untracked in
  `migrations/`. `tests/_location_fixture.py` applies every file in that directory to the
  disposable twins, and 0046 reworded a note that a B8 test asserted verbatim. One failure of 107.
- B9's suite run was contaminated because B10's `specs/09-action/requirements.md` had been
  written while the suite ran. `validate_layout.py` counts every `REQ-*` token in a spec as a
  declaration, so B10's *prose citations* of REQ-TIER-047/049 read as duplicate IDs. One failure
  of 122.

**Lesson recorded twice in PROGRESS:** nothing belonging to the next build file may touch
`migrations/` or `specs/` until the current one is committed.

**This applies to you right now.** [OBSERVED] `migrations/0049_ask_core.sql` is untracked and
present. Any test run you do today applies it to the twins. It dry-runs clean (§7), so it is
unlikely to break anything — but if you get an inexplicable single-test failure, this is why.

### 4.4 A leaked `idle in transaction` session bricked the test suite

[REPO] B10. An interrupted test run left a session holding the disposable `core_pytest` schema;
every subsequent run timed out on `CREATE SCHEMA`. Diagnosed in `pg_stat_activity`, terminated by
pid — only that one, only a `*_pytest` transaction whose outcome was a rollback either way.

[INFERRED] If the suite hangs on `CREATE SCHEMA`, look here first. The tests are slow (one module
is ~255 s; another was 21 min before an INSERT-batching fix took it to ~5), so interrupting a run
is tempting and this is the cost.

### 4.5 The confirmation gate's null moved the earliest possible promotion by a month

[REPO] B9. REQ-TIER-012's circular-shift null needs a shift of ≥30 days in either direction,
which needs ≥61 paired days. A 45-day window cannot support it. So a v2 watch now ledgers
`insufficient_window_too_short` at look 1 until the window is long enough.

The session explicitly refused to shrink the shift to fit, citing RULE-00 (never weaken a gate).
[INFERRED] Correct call, and worth knowing: **the promotion timetable is a consequence of the
statistics, not a configuration value.** Do not "tune" it.

### 4.6 The naive refuters could never fail

[REPO] B9 measured this rather than assuming it. A random-80%-subset refuter is nested in the full
sample, so a clean effect, an effect carried by four leverage points, and pure noise all scored
"inside" 1.00 — the test could not fail. Replaced with leave-one-contiguous-block-out (5 blocks,
≥80% inside), the correct resampling unit for a time series.

[INFERRED] This is the single best piece of engineering in the repository's history: someone
tested the test. Keep the habit.

### 4.7 The `scan._shift` null was silently degenerate

[REPO] B9. `scan._shift` computed its offset as `60 + hash % 241` with no reference to series
length, so on any shorter series it returned the input unchanged. Measured on a synthetic pair
with a real effect: `share_sig 1.000` **and** `null_median_share 1.000` — the null was the
signal. `speccurve.circular_shift` replaces it; `scan` itself was left untouched.

**[INFERRED] `scan.py` may still contain the degenerate `_shift`.** I did not open it. If any
path still calls it on a short series, its null is meaningless. Worth checking early.

---

## 5. Recurring approval blocks, contradictions, and infrastructure limits

### 5.1 Approval blocks that recur

**(a) Live migration applies are held for Joe.** [REPO] PROGRESS lines 1765, 1911, 4483 record
three separate occasions where a live `--commit` was blocked and handed back. Line 4483: B7's
`run_migration.py --core core --ops ops --only 0042 --commit` was denied; the migration sat
"written, tested on twins, LIVE APPLY HELD" until the next session. This is by design, not
malfunction. [INFERRED] Budget for it: **any B-file that ends in a live apply cannot be finished
in one unattended pass.**

**(b) The destructive-command guard hook.** [OBSERVED] `.claude/hooks/guard-destructive.sh` runs
`PreToolUse` on every Bash call and hard-blocks (exit 2, no prompt): `DROP`/`TRUNCATE`
TABLE/SCHEMA/DATABASE; `DELETE FROM`/`UPDATE` against `atoms|raw_captures|entities|links|findings`;
force push; `git reset --hard`; recursive force delete; anything matching a credential pattern;
and **any `curl`, `wget`, or `nc`** (RULE-29 — outbound requests must go through the egress-logged
client).

[OBSERVED] It fired on me this session: a harmless `env | grep -i supabase` was blocked as a
credential echo. The block is a shell regex over the command string, so it catches by shape, not
intent. Expect false positives. Do not work around it — it is load-bearing doctrine, and [REPO]
OQ-24 records that a previous self-edit of this guard needed explicit authorisation.

**(c) The `curl` block will bite you specifically.** [INFERRED] Any diagnosis of the dead feeds
(§3.1) that involves poking an HTTP endpoint from the shell is blocked. Route it through
`lib/egress.py`, or ask Joe to run it with the `!` prefix.

**(d) The rulings document that governs these blocks is not in the repository.** [OBSERVED]
`docs/STANDING_RULINGS.md` and `ops/WORK_QUEUE.md` **do not exist**, are not in git history, and
are referenced by no tracked file. [REPO] PROGRESS (session 17) records that both were "moved out
of the tree" as never-tracked and stale, with "copies kept in the session scratchpad" — a
scratchpad that no longer exists.

PROGRESS still cites "STANDING_RULINGS STOP-AND-ASK #2" and "#5" as governing constraints.
**Those numbered rulings are unrecoverable from the repository.** [INFERRED] This is a genuine
loss of institutional memory and one reason a fresh agent cannot pick up cleanly. Ask Joe to
reconstruct them, or treat `CLAUDE.md`'s `<safety>` block as the whole rule.

### 5.2 Contradictory or unsatisfiable requirements (all recorded, none resolved in code)

**(a) REQ-TIER-025 vs REQ-TIER-048/049.** [REPO] -025 forbids rendering a frequentist confidence
interval on any user-facing surface; -048/-049 require an interval on every recommendation below
CONFIRMED. B10 satisfied both by reporting a *credible* interval at 80% mass plus a probability
of direction, with `interval_method` naming how each was computed. At CONFIRMED that is "a
flat-prior normal posterior from B9's HAC estimate" — disclosed plainly as *numerically the HAC
interval, read as a credible interval*. [INFERRED] That is a presentational resolution of a
substantive conflict. It is honest because it is labelled. B19's NumPyro layer is supposed to
supersede it.

**(b) REQ-FIN-190 / REQ-FIN-198 are unreconciled.** [REPO] Carried as A-Q3 in
`specs/09-action/requirements.md`. Consequence: **no finance surface may recommend anything**
until B17 settles it.

**(c) REQ-NAR-024 forbids rendering any behaviour "with a judgment attached."** [REPO] Found *by
accident* during the constitution audit, per `docs/REMEDIATION_PLAN.md` §1.1. [INFERRED] Taken
literally it conflicts with the entire REQ-ACT recommendation layer B10 just built. I did not
check whether B10 addressed it. **Worth an explicit check.**

**(d) The requirements were never ratified.** [REPO] REMEDIATION_PLAN Track 1.1: the 564 (now
650) requirements "were written by three sub-agents in parallel, in a single turn, before any
rulings existed, under the framing the constitution audit just overturned. They have never been
checked against what you actually want." Tracks 1.1–1.3 were scheduled to run **before Phase 3**.
[OBSERVED] The B-chain runs against those unratified requirements anyway.

**(e) B11's own build file contradicts the live schema.** [OBSERVED] `docs/build/B11_ask.md`
specifies `CREATE TABLE __CORE__.render_violations` and `config.strings(k, v)`. Live, [OBSERVED]
`analysis.render_violations` already exists (created by B10's 0047) and `config.strings` has
columns `(key, value, note)`. The drafted 0049 silently resolved both divergences correctly —
it `ALTER`s the existing `analysis.render_violations` and matches the real `config.strings`
shape. [INFERRED] The B-files were written on 2 Sep against a projected schema and have drifted.
**Read each B-file against the live schema before executing it, as its own rule 12 instructs.**

**(f) B11's migration numbers are wrong.** [OBSERVED] `B11_ask.md` is titled "migrations
0048–0049" and B11.1 says "migration 0048". 0048 was consumed by B10
(`0048_pending_excludes_void.sql`). The drafted file correctly uses 0049. B11.2 will need 0050,
which collides with B12's stated number. Renumber the tail of the build pack, or accept drift.

**(g) An internal inconsistency in the OQ-44 lettering.** [OBSERVED] `docs/OPEN_QUESTIONS.md`'s
resolution line maps **(i)** to "v2 rule template" and **(j)** to "coverage < 0.60 gates".
PROGRESS's session-19 addendum maps **OQ-44(i)** to the false-promotion-rate finding and
**OQ-44(j)** to the coverage clause. The two mappings disagree. **[UNKNOWN] which is
authoritative.** Matters because §6.3's unresolved finding is cited by letter.

### 5.3 Infrastructure limits

- **Python 3.14.3 is the only local interpreter.** [REPO] Excludes DoWhy entirely. [INFERRED] Will
  exclude other scientific packages; check before designing around one.
- **$0 recurring, hard.** [REPO] `CLAUDE.md`: any dependency needs its free-tier limit, projected
  usage, and overflow behaviour stated in an ADR *before* it is added. A service that bills on
  overage rather than failing is disqualified. [REPO] ADR-0046 records Supabase Edge Functions at
  500K invocations/month, fails closed, projected ~8.6K/month.
- **Supabase Postgres Free is 500 MB** and `atoms` is append-only. [REPO] OQ-20, open. [REPO]
  ADR-0028 defers the legacy Parquet load (309,826 atoms, measured 113 MB) partly for this reason.
- **Two keepalives are load-bearing.** [REPO] Supabase pauses a free project after 7 days idle;
  GitHub disables scheduled workflows after 60 days of repo inactivity. [OBSERVED] Both are
  firing daily and healthy — `keepalive_supabase` and `keepalive_github`, last 2026-09-06 11:03,
  7 runs each in the last 7 days, all `ok`. **Do not break these.**
- **Extraction is blocked on a missing credential.** [OBSERVED] `tools/status.py` reports:
  "extraction (raw_captures → atoms) needs the Cloudflare Workers AI credential to run." This is
  why 3 captures have sat at `processing_status='received'` since 1 August. [INFERRED] It is also
  a hard precondition for B11.2 and B16.
- **Credentials live in `.claude/settings.local.json`.** [OBSERVED] That file is untracked, has
  never been committed, and is not in git history — but it is protected by a **global** gitignore
  (`~/.config/git/ignore`), **not** by the repo's own `.gitignore`. [OBSERVED] The repository is
  **public**. [INFERRED] On any other machine, any other user account, or any fresh clone that
  re-creates that file, the repo's own ignore rules would not protect it. Adding the path to the
  repo's `.gitignore` is a one-line, zero-risk hardening. I did not make the change (Joe's call,
  and outside this document's remit). **No credential values appear in this document.**

---

## 6. Verified in production vs. implemented locally vs. described in documents

This is the section I would read first.

### 6.1 Verified working in production (observed in the live database or CI this session)

| Thing | Evidence |
|---|---|
| Both keepalives | `ops.runs`, 7 runs each in 7 days, all `ok`, last 2026-09-06 11:03 |
| Hourly `extract_checkins` | 33 runs in 7 days, all `ok`, last 13:10 today |
| Hourly `derive_visits` | 26 runs in 7 days, all `ok` |
| Nightly `panel_build` / `baselines_build` / `forecast_nightly` | 6/6/5 runs, last today 12:10 |
| Nightly `resolve_watches` | 9 runs, last today 12:13 — but on 0 subjects |
| Append-only enforcement | `check_invariants.py` — UPDATE/DELETE on `atoms` and `raw_captures` rejected at both grant and trigger level, for owner *and* `service_role`. Shown, not asserted. |
| INV-1 (no orphan atoms) | FK present, orphan count 0 |
| Layout/privacy gates | `validate_layout.py` 41/0/0, incl. no committed coordinate or home literal |
| The read RPCs from B1–B6 | [REPO] proven live in their sessions; [OBSERVED] I did not re-execute them |

### 6.2 Implemented and tested locally, but never exercised on a real row

**Everything from B7 through B10.** This is the largest category and the one most likely to be
misread as "done".

- The watch resolver, the two-look protocol, the paired-day clock — [OBSERVED] `watch_progress`
  is empty; the resolver has run 9 times over 0 subjects.
- The 108-specification curve, the circular-shift null, hierarchical FDR, the promotion gate —
  [OBSERVED] `confirm_gate` has run **once**, manually, on 2 Sep, and reported
  `{'considered': 0, 'confirmed': 0, ...}`.
- The registered DAG (22 seed edges), minimal backdoor sets, HAC errors, E-values, negative
  controls, the three refuters — never applied to a real hypothesis.
- The recommendations layer, both channels, the RULE-26 referral guard, auto-demotion —
  [OBSERVED] `recommend` has run **once**, manually, reporting all-zero counts;
  `core.recommendations` is empty.
- [REPO] B10's own WHAT I DID NOT DO says it plainly: *"Nothing can fire yet... Every claim about
  the pattern channel rests on twin fixtures."* B9's says: *"Nothing has run on a real row."*

**Credit where due:** these sessions declared this themselves. The WHAT I DID NOT DO sections are
accurate and are the most valuable prose in the repository. Read them before trusting any
component.

### 6.3 The honesty numbers that *were* measured

[REPO] Worth carrying forward because they are real measurements, not claims:

- **3.0%** — false-confirmation rate on 200 seeded AR(1) ρ=0.5 pure-noise runs with the direction
  pre-registered, against REQ-TIER-012/013's implied 5%. Runs in CI.
- **6.5%** — the same measurement with the direction chosen *after* seeing the data. [REPO] "That
  difference is the arithmetic value of pre-registration in this system."
- **~20%** — [REPO] the session-19 reviewer's independent simulation of the *two-look resolver's*
  false-promotion rate under the null (4000 trials/cell, AR(1) nulls, using the repo's own
  `_contrast`/`_dow_demedian`/`_kish_n_eff`). Matched a previous reviewer's independent 0.14/0.20
  single-look figures.

[INFERRED] The 20% figure may be superseded by B9, which added the spec curve and circular-shift
null *in front of* promotion and measured 3.0% end-to-end. But the two numbers measure different
gates on different paths, and **nobody re-ran the 20% measurement after B9 landed.** Do not assume
it is fixed. The reviewer also flagged the limits of their own simulation (i.i.d. AR(1),
no weekday structure, no trend, Gaussian marginal) and named the better test: a replay on Joe's
real `analysis.panel` with circularly-shifted drivers, using machinery `scan.py` already has.

### 6.4 Described in documents only — not built

- **`ops/features.json` is the honest scoreboard and it reads 3 passing of 15.** [OBSERVED] The
  three: the two keepalives (REQ-NFR-001/002) and the atoms taxonomy (REQ-ONT-001). The twelve
  failing include the Big Mac end-to-end slice, food capture, USDA lookup, interval nutrition,
  Gmail receipt parsing, the claim ladder, and "every rendered numeral traces to a stored
  computation." [OBSERVED] It has not moved through the entire B1–B10 build, because no B-file's
  tests carry a ledger requirement ID. [INFERRED] The headline metric has been flat for ten build
  sessions while fifteen migrations shipped. That gap is itself a finding.
- **Gate 3 (the Big Mac vertical slice) is not close.** [REPO] It requires Joe to speak into a
  Shortcut and have the meal and the charge appear as linked atoms with intervals and provenance.
  [OBSERVED] 3 captures ever, none extracted, 5 atoms, 0 entities, and extraction blocked on a
  missing credential.
- **B12–B23** — twelve build files, all written, none started.
- **The Lovable front end.** [OBSERVED] `app/` contains a single `index.html`; `pages.yml` last
  deployed 2026-09-02. [REPO] L0–L8 describe rewiring it to the new RPCs. [REPO] The
  session-18 reviewer explicitly noted they never opened the client, so **whether the front end
  honours RULE-14's numeral-template rule is unverified**. [UNKNOWN] I did not open it either.
- **The old stack is still live and still writing.** [OBSERVED] 8 active `pg_cron` jobs
  (`health_staleness_check`, `brief_readiness_tick`, `day-narrative-tick`, `enumerate_insights`,
  `generate_betterment_plan`, `refresh_metric_catalog`, `run_coaches`, `log_forecast`) plus
  `public.ask(text)` serving the old PWA. [REPO] OQ-17 freezes it until the new capture path
  ingests one real day end to end. That has not happened, so **two systems are running**.

---

## 7. `migrations/0049_ask_core.sql` — exact status

**Summary: complete, valid, never applied, never tested, never committed, no ADR, no client.**

[OBSERVED] The file: 413 lines, 28 statements, untracked, dated 2026-09-02.

**It is syntactically and semantically valid.** [OBSERVED] I ran the prescribed dry run — a
rolled-back transaction on the live instance, which persists nothing:

```
$ PYTHONPATH=. python3 tools/run_migration.py --core core_dryrun --ops ops_dryrun
  ...
  ok  0048_pending_excludes_void.sql  (4 statements)
  ok  0049_ask_core.sql  (28 statements)
ROLLED BACK 392 statements (dry run on core_dryrun/ops_dryrun) — schema executed end to end,
nothing persisted
```

**It has not been applied to production.** [OBSERVED] Every object it creates is absent live:

```
config.operations           -> NULL        config.ask_grammar    -> NULL
config.ask_templates        -> NULL        config.tier_vocabulary-> NULL
core.questions              -> NULL        core.computations     -> NULL
analysis.f_daily_panel      -> absent
public.ask overloads live   -> ask(text) only     [the OLD stack's function]
analysis.render_violations  -> exists, WITHOUT the question_id column 0049 adds
```

**What the file contains** [OBSERVED, from reading it]:

- `config.operations` — a closed registry of 11 operations, each with an arity and a
  `tier_ceiling` (all `DESCRIPTIVE` except `contrast` → `EXPLORATORY` and `effect` → `PROMOTED`).
- `config.ask_grammar` — priority-ordered POSIX regexes over the lowercased question.
- `config.ask_templates`, `config.tier_vocabulary`, plus rows into the existing `config.strings`.
- `core.questions` and `core.computations` — the computation is persisted **before** narration
  (REQ-ASK-006), with `observation_keys`, `coverage`, `tier` and `code_version`.
- `analysis.f_daily_panel(date)`, `public._ask_resolve_metric`, `public._ask_range`.
- `public.ask(p_question text, p_as_of date)` — ~210 lines of plpgsql, the executor.
- The REQ-ASK-010 numeral verifier: every numeral in the rendered answer must appear as a value
  in the stored `result`, or be the day count, or occur in the range label. On violation it
  writes to `analysis.render_violations` and replaces the sentence with the raw result set.
- Owner-lock preamble and `REVOKE`/`GRANT` tail per the build pack's rule 1.

**Two deliberate design decisions are documented in its header comment** [OBSERVED] — you should
honour or explicitly overturn them, not silently undo them:

1. **The name collision is handled, not worked around.** `public.ask(text)` already exists and
   serves the old PWA (OQ-17). A two-argument overload with a `DEFAULT` would make every
   single-argument call ambiguous and break that app. So the new function takes **both arguments
   as required**: `ask(text, date)` cannot collide with `ask(text)`. The default comes back at
   B22 when the old stack retires.
2. **One owner for the executor.** B11 asks for "the same logic" in Python as well. The header
   argues that two implementations of one executor is exactly the drift RULE-11/12 exists to
   prevent, so the executor lives once, in plpgsql, and `tools/engines/ask.py` is to be a thin
   client. [OBSERVED] **`tools/engines/ask.py` does not exist.**

**What is missing to finish B11.1:**

| Artefact | State |
|---|---|
| `migrations/0049_ask_core.sql` | drafted, dry-run clean, **not applied, not committed** |
| `tests/test_ask.py` | **does not exist** — no test carries a `REQ_ASK_*` name |
| `tools/engines/ask.py` | **does not exist** |
| ADR-0053 (operation registry + computations) | **not written** — ADRs stop at 0052 |
| ADR-0054 (Workers AI language layer) | not written; B11.2 not started |
| PROGRESS entry for B11 | **none** |

[INFERRED] Roughly half a session of work remains on B11.1, most of it tests. The SQL is the hard
part and it is done. **Do not rewrite it.** Read it, write the tests against it, dry-run, apply,
commit, ADR.

**One caution.** [OBSERVED] `0049` grants `EXECUTE` on `ask(text,date)` to `authenticated` and
adds a `question_id` column to `analysis.render_violations`. Applying it changes a table B10's
code writes to. The `ADD COLUMN IF NOT EXISTS` is additive and nullable, so [INFERRED] this is
safe — but it is a live schema change to a table another engine uses, and the live apply is a
STOP-AND-ASK per §5.1(a).

---

## 8. Unresolved review findings

[REPO] The project runs an adversarial reviewer at the end of each unit; "finding nothing is a
failed review." Most findings were fixed in-session. These were **explicitly not fixed** and are
carried:

1. **The two-look resolver's ~20% null promotion rate** (§6.3). [REPO] The reviewer offered three
   options; the session recorded "the three options are Joe's" and changed nothing. **Ruling
   owed.** Possibly superseded by B9 — unmeasured.
2. **HAC / p-deflation in the resolver: not built.** [REPO] Named as the principled fix for the
   above. Not implemented.
3. **REQ-TIER-017's coverage clause is implemented only in the resolver.** [REPO] Not in
   `get_domain`, not in `get_period`, not in any other surface that reports an aggregate.
4. **REQ-TIER-045 is not implemented.** [REPO] A CONFIRMED finding whose adjustment-set coverage
   falls below 0.60 in the trailing 90 days should re-render as INSUFFICIENT. It does not; a
   monthly re-check is the only guard.
5. **REQ-TIER-015 / the EXPERIMENTAL tier and micro-trials: untouched.**
6. **`insufficient_window_too_short`** was in the reason CHECK with no code path writing it (B8);
   B9 gave it one. [INFERRED] Resolved, but verify.
7. **The ledger COMMENT's "every status change" wording is now inaccurate** (it records looks
   too). [REPO] Noted, not rewritten, because the table is append-only.
8. **The DAG is a 22-edge seed.** [REPO] "Nothing can be confirmed that it does not know, so its
   gaps are silent refusals, not wrong answers — but they are refusals Joe will only see when a
   watch matures."
9. **The negative controls cost power.** [REPO] The future-exposure control refutes at p<0.20, so
   a genuine finding has ~20% chance of chance-refutation at each evaluation. Set by B9, not tuned.
10. **The PROMOTED interval is the weakest number in the payload.** [REPO] B10 says so explicitly:
    the generator reads the effect from the resolution ledger, which stores the delta but not the
    raw quartile sides, so the interval "uses a spread of half the effect, which is an assumption,
    not a measurement." The Bayesian bootstrap is implemented and tested but **not wired**.
11. **`config.standing_orders.condition_sql` is executed SQL held in a table.** [REPO] Owner-written,
    changeable only by migration, engine rebinds only the schema prefix — "but it is still a
    stored string that gets executed, and that is worth knowing."
12. **Every `min_effect` is a guess** (OQ-10). [REPO] They decide whether a recommendation is
    emitted at all, "so a wrong guess silences a real finding or admits a trivial one."
13. **The medical vocabulary is a 27-term list written by an agent**, not a clinical taxonomy.
14. **RULE-27's cadence is asserted, not enforced.** [REPO] The unique index enforces one
    instruction per day, not one interruption per day.
15. **The RULE-22 forbidden-import grep was not in CI** at session 19. [OBSERVED] It is now —
    `gates.yml` has a "RULE-22 forbidden methods" step. Resolved.
16. **A disagreement is recorded against me (the previous agent), and it stands.** [REPO]
    OQ-44(k): Joe instructed "print the token once so I can type it into Overland." `CLAUDE.md`
    forbids credentials in chat. The agent printed it without flagging the conflict first — "that
    is the fault." The token is in that transcript. [REPO] Rotation was assigned to Joe.
    [OBSERVED] `restricted.location_fixes` is still empty, which [INFERRED] suggests Overland was
    never configured, which [INFERRED] suggests **the rotation may also not have happened.**
    Worth one question to Joe. **I have not seen the token and it is not in this document.**

### Open questions with no ruling

[OBSERVED] `docs/OPEN_QUESTIONS.md` is 66 KB; 33 items are marked RESOLVED. Still open and
relevant to the near-term work: **OQ-10** (twelve placeholder thresholds), **OQ-17** (old stack
still live), **OQ-18** (no workout/strength history, though strength is the stated objective
function), **OQ-20** (500 MB ceiling), **OQ-29** (when the legacy Parquet backfill loads),
**OQ-31** (requirements audit ranked but not ratified; two rulings owe ADRs), **OQ-33** (atom
shape for one strength set), **OQ-34** (what fires the confirmation job), **OQ-35** (standard-drink
definition), **OQ-36** (e1RM formula, ACWR windows), **OQ-37** (home geofence, mobility windows,
place taxonomy), **OQ-40** (coverage-vocabulary thresholds), **OQ-42** (why `analysis.forecasts`
was absent), **OQ-43** (whether 282 legacy location rows are wanted in the restricted store).

[REPO] A batched decision list sits in PROGRESS under "DECISIONS FOR JOE" (line ~1831), including
a held migration: `migrations/pending/0016_alcohol_metric_seed.sql`, dry-run verified, awaiting
Joe's confirmation of five column values before it can move into `migrations/` and be applied.

---

## 9. Context from this conversation that is not in the repository

Everything here originates in this session (2026-09-06) and exists nowhere else:

1. **The 27–28 July feed death, with dates and per-source staleness** (§3.1). No document in the
   repository records it. `CLAUDE.md` describes an *older* decay pattern ("media dead since 19
   June, health ~26 days stale") that no longer matches the data.
2. **The default-branch drift and its two consequences** (§3.2). Not recorded anywhere. Every
   PROGRESS entry that says "the nightly workflow runs X" is, for B9 and B10, false in production.
3. **The `ingested_at` vs `ts` trap** (§3.1) — two feeds look fresh in the ingest log and are 40
   days stale in fact.
4. **Zero watches, so the promotion clock never started** (§3.3). The repository's "~November
   2026" dates all assume a clock that is not running.
5. **The Overland receiver has received nothing in four days** (§3.3), and the [INFERRED] link to
   the possibly-unrotated token (§8.16).
6. **`0049` dry-runs clean at 28 statements** (§7) — this had never been established.
7. **`docs/STANDING_RULINGS.md` and `ops/WORK_QUEUE.md` are unrecoverable** (§5.1d).
8. **The credential file is protected only by a global gitignore on a public repo** (§5.3).
9. **The OQ-44 lettering inconsistency** (§5.2g).
10. **`ops/features.json` did not move once across ten build sessions** (§6.4).
11. **Joe's framing of this handoff assumed I was blocked on a failing step.** I was not (§0). If
    he believes there is a specific error to fix, either it is from a session neither of us can
    see, or the assumption is wrong. **Worth clarifying with him directly before you plan.**

---

## 10. The shortest route to a usable product

This is my recommendation, not a ruling. [INFERRED] throughout. Joe decides.

**The premise I would challenge first.** The B-chain treats "usable" as "B23 committed" — twelve
more build files, ~25 sessions, each adding inference machinery. But [OBSERVED] the system already
has 48 migrations, a nine-module domain envelope, search, entity pages, movements, findings
lifecycle lists, a resolver, a promotion gate, a confirmation gate and a recommendation engine —
and it renders **nothing**, because it has no data and no subjects. **The bottleneck is not
missing code. Adding code does not move it.**

### The four things, in order

**1. Restore capture. Nothing else is on the critical path. (Days, mostly Joe's, not an agent's.)**

Diagnose the 27–28 July event. Start with the phone's Auto Export data-type selection (§3.1) —
the transport is demonstrably alive and only the payload shrank. Then owntracks/location, then
spend. In parallel, and worth more than all of it: [REPO] Track 0 — a lifting logger, meal
photos, a nightly note. Crude is fine; Phase 3 imports crude perfectly well. Every day without
this is a row that cannot be recovered later at any price. **This is the only item on the list
that gets permanently more expensive while you think about it.**

**2. Make the next death loud. (One session.)**

A staleness alarm over `ops.runs` and `max(ts)` per source, with a threshold per feed and a
failing CI check. [REPO] It is currently scheduled at Phase 4 / Gate 4 — *after* the analysis
layer that consumes the feeds. That ordering is why six weeks vanished silently. Pull it forward.
It is a handful of rows and one query, and it is the difference between losing six weeks once and
losing six weeks repeatedly.

**3. Fix the branch. (Five minutes, Joe's approval.)**

`gh repo edit --default-branch main` — after confirming `v2-day1` is not the default for a reason.
Until then, two of the three nightly engines and the entire nightly test suite are not running.

**4. Register one watch on a feed that is actually alive. (One session.)**

[OBSERVED] Nothing has ever been through the pipeline end to end. Until one real hypothesis is
registered and one nightly resolver run touches it, B7–B10 are twelve thousand lines proven only
on synthetic twins. One live subject would exercise the resolver, the clock, the ledger and the
surfaces at once, and would find real defects that fixtures cannot. Pick a driver–outcome pair
from the feeds still breathing.

### Then, and only then

Finish B11.1 — it is half a session (§7) and gives Joe a question box over the record, which is
the most *usable* thing available for the least work. Then reassess whether B12–B23 in their
stated order is still right, because [INFERRED] several of them (B17 finance, B18 workouts, B21
body/sleep) build surfaces over feeds that are currently dead, and B12/B16 both depend on the
Workers AI credential that is currently missing.

**What I would not do:** continue the B-chain as written from B11 through B23 on the assumption
that data will be there when the engines are finished. [OBSERVED] The chain's own instructions
say "never block the chain — mark the step HELD and continue," which is excellent for throughput
and precisely wrong here: the held step *is* the project.

**The cost nobody has priced.** ~25 sessions of engine-building against a panel whose personal
signal is step counts, email counts and the weather. The confirmation gate cannot confirm anything
without sleep, HRV and spend — the drivers the 37 candidate hypotheses are written against.
Continuing down the chain first is building the roof while the foundation drains.

---

## 11. Fast orientation for the incoming agent

**Read first, in this order:** `CLAUDE.md` (doctrine and stance — the `<push_back>` and
`<no_fabrication>` blocks are not decoration), `docs/CONSTITUTION.md` (30 numbered rules, hard
capped at 30 by `.claude/rules/constitution-cap.md`), `docs/DECISIONS.md` (52 ADRs, one-line
index), the last three entries of `ops/PROGRESS.md` (it is 342 KB — do not read it all), and
`docs/build/README.md`.

**Commands that tell you the truth, all read-only:**

```bash
PYTHONPATH=. python3 tools/status.py            # live capture/liveness summary, never prints payloads
PYTHONPATH=. python3 tools/check_invariants.py --core core
python3 tools/validate_layout.py
gh run list --limit 20
```

**The five house rules that will trip you first:**

1. **Never weaken a gate, threshold, or test to make it pass** (RULE-00 / INV-6). Non-negotiable,
   and the repository has a good track record of honouring it under pressure.
2. **Never fabricate a row.** No placeholder, sample, or synthetic data in any real table, for any
   reason including testing. Fixtures live in `tests/fixtures/` and touch disposable schemas only.
3. **Dry run before every apply.** `--core core_dryrun --ops ops_dryrun` first, then
   `--core core --ops ops --commit`, and expect the live apply to be held for Joe.
4. **Every test name contains the requirement ID it covers.** `tools/update_features.py` parses
   JUnit XML and flips a ledger entry only on an exact `REQ_X_NNN` match. Never rename a test to
   make it match.
5. **Joe is not an engineer and verifies by running things.** Ship evidence, not assertions. Every
   session ends with a Definition of Done including a section titled **WHAT I DID NOT DO** — the
   existing ones are the most useful documents in the repository, and the reason this handoff was
   possible at all.

**And the standing instruction that matters most:** *"You are the experienced engineer here and I
am not. Your job is not to agree with me... Silent compliance with a bad instruction is the worst
outcome available to us."* The B-chain will keep asking to be run. Say what it costs.
