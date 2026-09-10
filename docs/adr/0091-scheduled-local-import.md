# ADR-0091: The import runs on Joe's Mac on a schedule, and a green run still means nothing

**Status:** Accepted (prepared — the schedule is not installed; see Activation)
**Date:** 2026-09-09
**Amends:** ADR-0057, which listed "watch the folder with a launchd job" as *"compatible with
this and worth adding later… an unattended job that writes to production on a file appearing
deserves its own decision."* This is that decision.
**Related:** ADR-0060 (freshness is a property of the data, not of the job), ADR-0024
(`ops.runs` heartbeat doctrine), REQ-NFR-004, REQ-NFR-007/008/012.

## Context

`tools/import_drop.py` exists, works, and has been run against Joe's real export (33,355
atoms, session 21). It has no schedule. Every import so far has happened because Joe typed
the command.

Three facts constrain where a schedule can live, and the first one eliminates the obvious
answer:

1. **The drop folder is on Joe's Mac.** `~/PersonalOS_Drop` is not reachable from a
   GitHub-hosted runner. A `.github/workflows/import.yml` would check out the repository,
   find an empty folder, exit 0, and do so every night for ever. That is not a partial
   solution; it is a manufactured version of the exact signal this system spent 43 days
   failing to notice — a green job standing over a dead input.
2. **Scheduling an importer does not make a device produce an export.** Apple Health exports
   because Joe opens the Health app and asks for one. The bank CSV downloads because Joe
   downloads it. A schedule automates the *ingestion* of files that appear; it creates no
   file, and it must never be described as though it did.
3. **A successful run is not evidence that data arrived.** "The job ran" and "an
   observation landed" are two facts. Only the second matters to the analysis, and only the
   first is something a scheduler can observe about itself.

`import_drop.py` also has a property that only becomes visible once it runs unattended: its
`ops.runs` row is written *inside its transaction*. A `--dry-run` rolls it back. Its exit-2
failure path rolls it back. An empty folder returns before it ever connects. So the three
outcomes an unattended run most needs recorded are precisely the three it does not record.

## Decision

**A launchd user agent runs `ops/capture_schedule.py --run` daily at 01:40 local.** The
wrapper invokes `tools/import_drop.py` as a subprocess and reimplements none of it.

1. **launchd, not cron, not a workflow.** launchd is macOS's supported scheduler, it is
   already how a user agent runs on this machine, and it costs nothing (RULE-28). `cron` on
   macOS is deprecated and requires Full Disk Access to touch a Documents-adjacent folder. A
   hosted workflow is impossible, per Context 1, and a test asserts that no workflow ever
   gains an `import_drop.py` invocation.

2. **01:40 local, and the local/UTC seam is deliberate.** The freshness check runs at
   08:10 UTC — 04:10 local in EDT, 03:10 in EST. launchd schedules in local time. Choosing an
   import time against the summer offset alone would silently invert the ordering in winter,
   which is the same seasonal seam `check_freshness.py` documents for its own clock. 01:40
   local precedes the freshness check by 150 minutes in summer and 90 in winter, and a test
   asserts the ordering at *both* offsets. The margin is not a guarantee: a sleeping laptop
   runs the job at wake, and a seven-year export can outlast 90 minutes. When the import lands
   after the check, freshness reports one day late — the safe direction of the error, and the
   reason freshness is asked of the data rather than of this job.

3. **One import at a time, by `flock`.** Taken without waiting; a second firing exits 3 having
   attempted nothing. Overlap would not corrupt anything — the file hash and the per-atom
   dedupe key make a re-import a no-op (ADR-0057) — and "it would have deduplicated anyway" is
   not a reason to run two 300 MB parses against the same rows. `flock` and not `lockf`,
   because POSIX record locks are held per process and would let a test prove nothing.

4. **`ops.runs` gets exactly one row per import, and this wrapper writes it only when the
   importer did not.** The rule is *verify, then fill the gap*: after the importer returns,
   query `ops.runs` for a row under `import_drop` newer than a marker taken from the
   **database's** clock; write one under `capture_schedule` only if none appeared. The
   alternative — inferring from the exit code which outcomes log — is true today and becomes
   silently false the first time `import_drop.py` changes when it commits.

   The wrapper's job name is deliberately not `import_drop`. A row under that name means an
   import transaction committed; the wrapper never performs an import, and a fallback row for
   a *failed* import filed under the importer's own name would be indistinguishable from a
   successful one.

5. **The importer's exit code is mapped, with one correction that a double would never have
   found.** Running the real subprocess showed that `import_drop.main()` calls `db.connect()`
   *outside* its guarded block, so an unreachable database from the child is an uncaught
   exception — and the interpreter exits **1** on a traceback, the same code the importer uses
   for "committed, some files failed". Filing that as a partial success would report a
   rolled-back import as a partial import. The per-file JSON lines separate the two: the
   importer prints one for every file before any legitimate exit 1, so exit 1 with nothing
   reported means it never reached its reporting stage and wrote nothing
   (`import_failed_before_reporting`, exit 2). The importer is not edited to fix this; the
   wrapper reads the evidence instead. (A tidier fix — moving `db.connect()` inside the
   guarded block so the failure exits 2 through the redacted path — is offered to the owning
   session in the handoff, not taken here.)

6. **The child's stderr stays local.** A traceback escaping the importer is by definition the
   path that missed its own `redact()`, so it may carry whatever a driver put in an exception
   message, a connection URL included. It is written to `<drop>/_state/schedule.log` and never
   to `ops.runs`; the stored row carries counts, an outcome and an exit status.

7. **"The job ran" and "new data arrived" are separate recorded fields.** Every row carries
   `rows_written` (atoms — 0 when nothing arrived) and an explicit `new_data` boolean in
   `detail`. An empty drop folder is `outcome='no_new_files'`, `status='ok'`, `new_data=false`:
   the job succeeded and capture did not happen, and both halves are stored. Nothing in this
   wrapper reports whether a source is current. That question belongs to
   `tools/check_freshness.py`, is asked of the data, and runs on a schedule this job's death
   cannot take down (ADR-0060).

8. **Prerequisites fail loudly and early.** A missing drop folder, an absent credential and an
   unreachable database each exit non-zero under their own outcome name, before the parse
   starts. The drop folder is checked *before* the lock is taken, because taking the lock
   creates `<drop>/_state` and `mkdir(parents=True)` would otherwise create the missing drop
   folder on its way — converting the prerequisite most likely to be wrong into one that is
   always satisfied and always empty.

9. **The credential is read from a mode-checked env file, never from the plist.** A launchd
   agent inherits no login shell, so `SUPABASE_DB_URL` has to come from somewhere. A plist in
   `~/Library/LaunchAgents` is world-readable by default and is the first file pasted into a
   bug report. So: environment first, then `$PERSONAL_OS_ENV_FILE` or
   `~/.config/personal_os/env`, which lives outside the repository and is **refused, not
   repaired**, if it is group- or world-readable. Repairing it silently would hide that the
   credential had been exposed. Only `SUPABASE_DB_URL` is read out of that file; it is not a
   general environment loader.

10. **Counts on stdout, names in the local log (RULE-29).** Drop-folder file names are close to
   personal data — a bank export is routinely named after the account. stdout and the launchd
   log carry an outcome and four numbers; the importer's per-file JSON goes only to
   `<drop>/_state/schedule.log`, on the Mac, outside the repository, where no commit can reach
   it.

11. **`RunAtLoad` is false.** Bootstrapping the agent would otherwise write to production as a
   side effect of installing a scheduler. Installing the schedule and running the first import
   are two acts, and Joe performs both.

## Activation (not performed)

Nothing here is enabled. `--emit-launchd` prints the job description and installs nothing; a
test asserts that. The steps that turn it on — writing the plist, `launchctl bootstrap`, the
`ops.job_registry` row — are Joe's, and are listed in the session handoff rather than here,
because an ADR that also functions as an install script gets run.

## Consequences

- The drop-folder path stops depending on Joe remembering to run a command. It continues to
  depend on Joe remembering to *export*, which no scheduler can fix and which ADR-0057 already
  recorded as the real weakness.
- `ops.runs` gains rows for outcomes that previously left no trace: the empty folder, the
  rolled-back failure, the dry run.
- A new failure mode is introduced and bounded: a stale lock file would silence the schedule
  permanently. The lock is released in a `finally` and the release is tested; an `flock` is
  also dropped by the kernel when the holding process dies, so a crash cannot leave one held.
- **Unproven until observed.** That the agent fires unattended, that a real export lands
  through it, and that the ordering against the freshness check holds in practice are all
  claims about a running system, and none of them is established by this decision or by its
  tests. The tests prove mechanism. `ops.runs` will prove firing, once it has fired.
