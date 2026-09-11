# ADR-0140 — The capture path, completed and exercised as processes

**Status:** Accepted (implementation), with three items batched for Joe below.
**Date:** 2026-09-11
**Supersedes:** nothing. **Amends:** ADR-0094 (the scheduled local import), ADR-0060
(freshness keeps its own schedule), ADR-0082 (the disposable SQL server).
**Numbering note:** written in the `work/capture-finish` worktree while three other worktrees
were open. Parallel worktrees cannot reserve an ADR number (ADR-0091 → 0094 happened for this
reason). Renumber on integration; nothing depends on the digits.

## Context

`ops/capture_schedule.py`, `tools/import_drop.py` and `tools/check_freshness.py` were each
built and each tested. What had never been established is that they form a **path**: that a
file landing in a folder becomes rows, that running the command twice does not double them,
and that two copies firing at once do not both import.

The gap was structural rather than accidental. Every scheduling test in
`tests/test_capture_schedule.py` drives the wrapper with an injected `runner` and an injected
`connect` — no importer subprocess, no database. That is the right shape for proving what the
wrapper does with an exit code, and it cannot prove the properties that matter most here. **A
`flock` tested against a fake is a test of the fake.**

Exercising the real path surfaced four defects, three of which no in-process test could have
found.

## Decision

### 1. The path is proven by a runnable command, not by assertions

`tools/capture_acceptance.py` runs the real `ops/capture_schedule.py` and the real
`tools/import_drop.py` as separate operating-system processes against a real PostgreSQL 17
server, and reads their exit codes from the processes. Ten cases, all passing at this revision:

| # | case | evidence |
|---|---|---|
| 1 | new input is discovered and processed | 2 atoms, 1 capture row, file moved to `_done/`, one `import_drop` row, **zero duplicate heartbeats** |
| 2 | repeated input is not duplicated | atoms and capture rows unchanged |
| 3 | an overlapping window adds only what is new | 2 → 3 atoms for a three-day export overlapping two stored days |
| 4 | an unrecognised file is reported, not silently ignored | exit 0, 0 atoms, file retained, `unrecognised=1` on the summary |
| 5 | missing or unreadable input is not a successful capture | empty = 0/`no_new_files`; missing folder = 2 **and not created**; unreadable = 1 and retained |
| 6 | processing failure is visible and retryable | corrupt file: exit 1, 0 atoms, file kept, error row; the replacement then imports |
| 7 | concurrent invocation does not double-process | two simultaneous processes, exit codes `[0, 3]`, six atoms written exactly once |
| 8 | a file still arriving is not imported | growing file: exit 1, 0 atoms, **0 capture rows**; imported on the run after the writer finished |
| 9 | heartbeat success does not conceal stale evidence | `capture_schedule` ok with `new_data=yes` **while** `check_freshness` exits 1 with a 40-day-stale metric |
| 10 | a dry run writes nothing | atoms and capture rows unchanged |

### 2. RULE-01: the isolation boundary is the server's lifetime, not a transaction

**This is the one decision in this ADR that widens a constitutional carve-out, and it is stated
rather than assumed.** RULE-01's bounded exception is a *transaction* that rolls back. Case 7 is
two processes, and two processes cannot share an uncommitted transaction — an overlap test
inside one transaction proves nothing about an overlap. The boundary used instead is the
disposable server's lifetime, which ADR-0082 already established for the SQL suite.

It preserves what RULE-01 protects and gives up nothing that matters:

* no production table is touched — the schema pair is `core_dryrun`/`ops_dryrun`, the throwaway
  pair migration 0001 already names; never `core`, never `public`;
* the instance is created by the command (`initdb` into a fresh temporary directory) and
  destroyed before it returns, so no fabricated row survives the run;
* TCP is disabled (`listen_addresses=''`), so nothing else can reach it;
* every child process has `SUPABASE_DB_URL` replaced with an unroutable placeholder.

### 3. No test hook is added to `lib/db.py`

`lib/db.py` connects to Supabase over pinned TLS and to nothing else. The harness points the
real runners at the disposable server by writing a `sitecustomize.py` into **its own temporary
directory** and putting that directory on the children's `PYTHONPATH`. The shipped code
therefore carries no escape hatch at all — deliberately stricter than an environment variable
inside `lib/db.py`, because such a variable, once it exists, can redirect a production run.

### 4. Four defects, repaired

**(a) `--ops` reached the wrapper and not the importer.** `capture_schedule` accepted `--ops`
and used it to ask `<ops>.runs` whether the importer had logged; `import_drop` wrote to a
literal `ops.runs`. Under any non-default pair the lookup found nothing and the wrapper wrote a
second heartbeat for an import that had already recorded itself — `ops.runs` counting one
import twice, which point 2 of the wrapper's own docstring forbids. Not live in production,
which uses both defaults, and live in every other environment. `--ops` and `--schema` are now
passed through.

**(b) A file still being written was imported.** `import_drop` hashes a file, counts its
records, and writes that count into an append-only `core.raw_captures` payload. A file still
being copied into the drop folder is a *shorter* file, and the two failure shapes are not
equally loud: a truncated Apple Health zip raises `BadZipFile` and is reported, while **a
truncated bank CSV parses cleanly** — it commits whatever rows had landed, writes a capture row
whose `records_parsed` is simply wrong, cannot be corrected because RULE-02 permits only
appends, and moves the file to `_done/`. The atoms that never arrived become indistinguishable
from days Joe did not spend.

`settle()` therefore holds a file back until two observations of `(size, mtime)` agree.
Deliberately **not** an mtime-age test: AirDrop, `cp -p`, a Finder copy across volumes and an
iCloud materialisation all preserve the source file's mtime, so a half-copied export can
present an mtime from last Tuesday while bytes are still being written, and any age test passes
it immediately. A file that never settles is left in the folder and reported as
`files_still_arriving` with `status='error'` and exit 1 — never as an empty day.

**(c) An unrecognised file was silent.** A Health export saved as `health.xml`, or a second
download named `statement (1).csv`, is `unrecognised_file_type`: it imports nothing, exits 0,
and sits in the folder being ignored again tomorrow while every line of the summary says the
job succeeded. The count is now on the summary line and in the heartbeat detail. It still does
not fail the run — Joe may keep a note in that folder.

**(d) `PYTHONPATH` was overwritten rather than extended** in the importer's child environment,
so the child's import path depended on which parent started it.

### 5. `check_freshness.py` gains the two things a freshness check could not see

**A dead capture source behind a live metric.** `source_quiet`: the metric is FRESH and one of
the ingress channels that used to supply it has stopped. This is the bank handover — `bank_csv`
died 2026-05-13, `chase_email` took over with a third of the transactions and a seventh of the
value, and `transaction_amount_usd` is fresh throughout, which is true and useless. The set of
channels a metric depends on is derived from evidence (`atoms → raw_captures`, INV-1 read in
the direction it was built for), never from a hand-maintained list. **It reports and does not
fail:** which of two sources to believe is a measurement ruling (RULE-12), and a permanently red
check is an ignored one.

*Scope stated honestly:* the source here is the ingress channel (`raw_captures.source`, an
enum), **not the device**. The Watch-versus-iPhone split is not visible to it — for a file
import both devices arrive under `file_import`, and the instrument survives only inside
`core.atoms.evidence_span` as free text from the export's `sourceName`. That field is a
user-renamable string in a column that also carries merchant descriptors and page titles, and
REQ-NFR-011 forbids an operational alert becoming an egress path. Device-level attribution
remains a real gap; see the batched questions below.

**The local schedule's own silence.** The drop folder is on Joe's Mac and this check runs on a
GitHub runner, so a laptop shut for a week is invisible: a dozen metrics age and the one
sentence explaining all of them appears nowhere. `import_schedule_liveness` mirrors the metric
rule exactly — `not_installed` (never any row) does **not** fail, because ADR-0094 keeps
activation a separate human act and failing would leave the workflow red from the day this
shipped until the day Joe installs the agent; `stale` (reported, then stopped) **does** fail.
The cadence is read from `capture_schedule.launchd_plist()`, not written into the checker.

### 6. REQ-REC-015's second half is connected to the existing dispatcher

`ops/clarification_prompts.py` writes `core.prompt_dispatch` — migration 0009, `SHAPE LOCKED`,
"wired when prompts exist", and until now with **no writer of any kind**. It is the only writer,
because a second prompt mechanism would be a second place for RULE-27 to be true.

* dismissal is permanent (RULE-27), read from every row for the subject rather than the latest,
  so a dismissal cannot be buried by a later row;
* one prompt per subject per day;
* a subject with an open dispatch is not re-asked;
* the daily ceiling reuses `MAX_SCHEDULED_PROMPTS_PER_DAY` from `vision_and_prompts.py` — one
  prompt budget, not one per feature, which is how a system reaches nine prompts a day with
  every component under its own limit;
* the subject key is `clarify:<family>:<subject_day>` — **the question, not the row**. Revision
  is append-only (REQ-REC-011), so keying on `event_id` would ask Joe about Tuesday again every
  time the engine changed its mind: the nag RULE-27 forbids, arriving through a technicality.

**It schedules; it does not deliver.** `delivered_at` stays NULL because REQ-CAP-092 names Web
Push and Web Push is not built. A row means the question is due to be asked, never that Joe was
asked.

## Consequences

* The capture path has process-level evidence for the first time, reproducible by one command.
* Two failure modes that would have produced permanently wrong, uncorrectable rows are closed.
* A green scheduled job can no longer be mistaken for arriving data at three separate levels:
  the metric, the ingress channel and the schedule itself.
* `tools/capture_acceptance.py` needs PostgreSQL 17 locally. Where it is absent, it says so and
  exits rather than pretending.
* **Nothing here is deployed or observed.** The launchd agent is still not installed, no import
  has run on a schedule, and `ops/clarification_prompts.py` has no caller in any workflow.

## Batched for Joe (each holds something; none blocks the rest)

1. **`--at HH:MM` for clarification prompts.** The command refuses `--commit` without it:
   REQ-CAP-087 forbids a randomly chosen time and RULE-27 records 81% compliance for scheduled
   morning prompts against 52% for random pings, so the time matters and it is a preference,
   not a derivation. *Recommendation: 09:00.* Consequence of not answering: reconstruction
   questions are computed and never asked.
2. **Should a quiet ingress channel fail the freshness run?** Today it reports and does not,
   because the only honest response to "the Watch stopped" may be "yes, deliberately" and
   there is nowhere to record that ruling. Making it fail needs a stored acknowledgement —
   a small table, a migration, and therefore main's. *Recommendation: keep it reporting until
   there is somewhere to record the answer.*
3. **Device-level source loss.** Closing it means naming instruments from stored configuration
   rather than parsing `evidence_span`. That is a migration and a measurement decision.
   *Recommendation: defer; it is a named gap, not a silent one.*

## Proposed to main (requirements are main's, per CLAUDE.md)

Two behaviours here have no requirement ID and their tests are named after this ADR rather than
after an invented one:

* **REQ-NFR-015** — the freshness checker SHALL report, for each fresh metric, any ingress
  channel that has supplied it and has now gone quiet past that metric's limit, so that a
  source that has died behind a still-fresh metric is visible.
* **REQ-NFR-016** — the freshness checker SHALL report whether the local import schedule has
  reported inside its own declared cadence, SHALL fail when it reported and then stopped, and
  SHALL NOT fail when it has never reported, so that a scheduler running on a machine the
  checker cannot see is not silently assumed alive.
