#!/usr/bin/env python3
"""The scheduled local import (ADR-0094). Wraps `tools/import_drop.py`; replaces nothing.

    PYTHONPATH=. python3 ops/capture_schedule.py --run           # the scheduled action
    PYTHONPATH=. python3 ops/capture_schedule.py --run --dry-run # invoke the importer read-only
    PYTHONPATH=. python3 ops/capture_schedule.py --preflight     # prerequisites only, no import
    PYTHONPATH=. python3 ops/capture_schedule.py --emit-launchd  # print the plist; install nothing

**Why this exists and why it is here rather than in a workflow.** The drop folder is on Joe's
Mac. A GitHub-hosted runner cannot see `~/PersonalOS_Drop`, so no `.github/workflows/*.yml`
can ever run this import, however convenient that would be. The scheduler therefore has to be
local, and on macOS that is launchd. `--emit-launchd` writes the job description; it does not
install it (ADR-0094: activation is Joe's, and it is a production-writing job).

**What it adds to `import_drop.py`, which is not edited and not reimplemented.**

1. *One import at a time.* An `flock` on `<drop>/_state/import.lock`, taken without waiting.
   A second firing while a 300 MB Apple Health parse is still running exits immediately and
   imports nothing. Overlapping runs would not corrupt anything — the file hash and the
   per-atom dedupe key make a re-import a no-op (ADR-0057) — but they would double the
   parse cost and interleave two transactions writing the same atoms, and "it would have been
   deduplicated anyway" is not a reason to run two of them.

2. *A heartbeat in exactly the cases the importer leaves silent.* `import_drop.py` writes its
   own `ops.runs` row, and that row is the record of an import — this wrapper never writes a
   second one describing the same work. But the importer's row is written inside its
   transaction and is therefore lost whenever that transaction rolls back: a `--dry-run`, an
   unhandled failure (its exit 2), and an empty drop folder (it returns before it connects).
   Those are precisely the outcomes an unattended run must not swallow. So the rule here is
   *verify, then fill the gap*: after the importer returns, ask `ops.runs` whether a row
   appeared; write one under `capture_schedule` only when none did.

3. *"The job ran" and "new data arrived" are never the same sentence.* This is the whole
   lesson of 2026-07-28, when every scheduled job wrote `status='ok'` for 43 days while its
   inputs were dead. A successful run over an empty drop folder is a success of the job and a
   *failure of capture*, and it is recorded as `outcome='no_new_files'`, `rows_written=0`,
   `new_data=false`. Nothing here reports on whether a source is current: that is
   `tools/check_freshness.py`'s question, it is asked of the data rather than of the job, and
   it runs on its own schedule so that this job's death cannot take the alarm down with it
   (ADR-0060).

**Credentials.** `SUPABASE_DB_URL` from the environment, exactly as `lib/db.py` requires. A
launchd agent inherits no login shell, so when the variable is absent an env file is read —
`$PERSONAL_OS_ENV_FILE`, else `~/.config/personal_os/env`. It lives outside the repository,
must not be group- or world-readable, and is never printed, logged or placed in the plist.

**Output.** Counts, never contents (RULE-29): the file *names* in the drop folder can
themselves be identifying — a bank export is routinely named after the account — so stdout
carries an outcome and numbers, and the importer's per-file JSON goes only to
`<drop>/_state/schedule.log`, on the Mac, outside the repository, never committed.

Exit codes, which are what launchd and a human both read:

    0  completed — imported, or nothing was pending
    1  the import committed but at least one file failed or was quarantined, OR every
       pending file was still being written and none could be imported
    2  a prerequisite is missing, the database is unreachable, or the import rolled back
    3  another run holds the lock; nothing was attempted
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path

from lib import db

CODE_VERSION = "capture-schedule-v1"

# The wrapper's own job name in ops.runs. Deliberately NOT 'import_drop': a row under that
# name means "an import transaction committed", and this wrapper never performs an import.
JOB_NAME = "capture_schedule"
IMPORTER_JOB_NAME = "import_drop"          # the name import_drop.py writes under

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DROP = Path(os.environ.get("PERSONAL_OS_DROP", Path.home() / "PersonalOS_Drop"))
STATE_DIRNAME = "_state"
LOCK_NAME = "import.lock"
LOG_NAME = "schedule.log"

DEFAULT_ENV_FILE = Path.home() / ".config" / "personal_os" / "env"
CREDENTIAL_VAR = "SUPABASE_DB_URL"

LAUNCHD_LABEL = "com.personalos.import"
# 01:40 *local*. The freshness check runs at 08:10 UTC, which is 04:10 local in EDT and 03:10
# local in EST, so the import precedes it by 150 minutes in summer and 90 in winter — the
# ordering holds in both halves of the year rather than in one of them, which is the mistake
# a fixed-UTC local schedule would make. The gap is a margin, not a guarantee: a laptop asleep
# at 01:40 runs this at wake, and a seven-year export takes longer than 90 minutes. When the
# import lands after the check, freshness reports one day late. That is the safe direction of
# the error and the reason freshness is asked of the data rather than of this job.
LAUNCHD_HOUR = 1
LAUNCHD_MINUTE = 40

# A file is READY when two observations of (size, mtime) taken this far apart agree.
#
# Deliberately NOT "mtime is older than N seconds". A file arriving by AirDrop, `cp -p`, a
# Finder copy from another volume or an iCloud materialisation keeps the SOURCE file's mtime,
# so a half-copied 300 MB export can present an mtime from last Tuesday while bytes are still
# being written. An age test passes that file immediately. Size stability across two
# observations is the property that actually distinguishes a finished file from a growing one.
SETTLE_INTERVAL_SECONDS = 5
SETTLE_TIMEOUT_SECONDS = 120

# Outcomes. Every scheduled firing ends as exactly one of these.
# `files_still_arriving` is deliberately absent: it is a fault, and it writes status='error'.
OK_OUTCOMES = ("imported", "no_new_files", "imported_no_new_atoms", "dry_run")
EXIT_OK, EXIT_PARTIAL, EXIT_FAILED, EXIT_LOCKED = 0, 1, 2, 3

IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class Locked(Exception):
    """Another run holds the import lock."""


class PrerequisiteMissing(Exception):
    """A precondition for importing is absent. Carries an outcome name."""

    def __init__(self, outcome, message):
        super().__init__(message)
        self.outcome = outcome


# --------------------------------------------------------------------------- prerequisites

def state_dir(drop):
    """`<drop>/_state`. A directory, so `import_drop.py`'s `p.is_file()` scan never sees it,
    and inside the drop folder, so the lock and the log follow the data they describe rather
    than living in the repository where a log of file names must never go (RULE-29)."""
    return Path(drop) / STATE_DIRNAME


def load_credential(env=None, env_file=None):
    """Ensure `SUPABASE_DB_URL` is in the environment. Returns where it came from.

    The value is never returned, printed or logged — only the word 'env' or 'env_file'.
    """
    env = os.environ if env is None else env
    if env.get(CREDENTIAL_VAR):
        return "env"
    path = Path(env_file or env.get("PERSONAL_OS_ENV_FILE") or DEFAULT_ENV_FILE)
    if not path.is_file():
        raise PrerequisiteMissing(
            "missing_credential",
            f"{CREDENTIAL_VAR} is not set and no env file at {path}. A launchd agent inherits "
            f"no login shell, so the schedule needs one or the other.")
    mode = path.stat().st_mode
    if mode & 0o077:
        # Refusing is the point: a credential readable by every process on the machine is a
        # leaked credential, and repairing it silently would hide that it ever happened.
        raise PrerequisiteMissing(
            "credential_file_permissions",
            f"{path} is group- or world-readable (mode {mode & 0o777:03o}). "
            f"Run: chmod 600 {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep or key.strip() != CREDENTIAL_VAR:
            continue                      # only this one variable is ever read out of the file
        value = value.strip().strip('"').strip("'")
        if value:
            env[CREDENTIAL_VAR] = value
            return "env_file"
    raise PrerequisiteMissing(
        "missing_credential", f"{path} contains no {CREDENTIAL_VAR} assignment")


def pending_files(drop):
    """The files `import_drop.py` would consider, by its own rule: files in the drop folder,
    not dotfiles, not directories. Counted here so an empty folder can be reported as a
    capture outcome without spawning a process to discover it."""
    drop = Path(drop)
    if not drop.is_dir():
        raise PrerequisiteMissing(
            "missing_drop_dir",
            f"drop folder does not exist: {drop}. Scheduling an importer does not make a "
            f"device produce an export; this is a missing prerequisite, not an empty day.")
    return sorted(p for p in drop.iterdir() if p.is_file() and not p.name.startswith("."))


def settle(files, interval=None, timeout=None, sleeper=time.sleep, clock=time.monotonic):
    """Split `files` into (ready, still_arriving). A file still being written is NOT imported.

    **The failure this closes.** `import_drop.py` hashes a file, counts its records, and writes
    that count into a `core.raw_captures` payload which RULE-02 makes append-only. A file that
    is still being copied into the drop folder is a shorter file than the one Joe dropped, and
    the two failure shapes are not equally loud:

    * An Apple Health `export.zip` truncated mid-copy raises `BadZipFile`, is reported
      `failed`, and stays in the drop folder for the next run. That one is fine already.
    * A bank CSV truncated mid-copy **parses cleanly**. It yields whatever rows had landed,
      commits them, writes a capture row whose `records_parsed` is simply wrong, and moves the
      file to `_done/`. Nothing is flagged, the atoms that never arrived are indistinguishable
      from days Joe did not spend, and the capture row cannot be corrected because appending is
      the only operation the spine allows. That is a permanent, silent, wrong number, which is
      exactly the class of failure this whole path exists to stop.

    A file that never settles is left in the drop folder and reported, not imported. Waiting is
    the safe direction of the error: an import that happens one run late is recoverable and an
    append-only capture row describing a partial file is not.

    `interval` and `timeout` default to the module constants at CALL time rather than at
    definition time, so a test can shorten the wait by setting them without reaching into a
    function's default arguments. `sleeper` and `clock` are injected for the same reason.
    """
    interval = SETTLE_INTERVAL_SECONDS if interval is None else interval
    timeout = SETTLE_TIMEOUT_SECONDS if timeout is None else timeout
    pending = {p: _fingerprint(p) for p in files}
    ready, gone = [], []
    deadline = clock() + timeout
    while pending:
        sleeper(interval)
        for path, before in list(pending.items()):
            after = _fingerprint(path)
            if after is None:                 # vanished between observations
                gone.append(path)
                del pending[path]
            elif after == before:
                ready.append(path)
                del pending[path]
            else:
                pending[path] = after
        if pending and clock() >= deadline:
            break
    return sorted(ready), sorted(pending)


def _fingerprint(path):
    """(size, mtime_ns) or None if the file is no longer there."""
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


@contextlib.contextmanager
def exclusive_lock(path):
    """A non-blocking `flock`. Raises `Locked` rather than queueing.

    `flock` and not `lockf`: POSIX record locks are held per *process*, so a second attempt
    inside one process would succeed and the overlap test would prove nothing. `flock` is held
    per open file description and conflicts even with itself.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Locked(f"another import holds {path}")
        try:
            yield handle
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


# --------------------------------------------------------------------------- the importer

def import_command(repo_root=ROOT, drop=None, commit=True, since=None, until=None,
                   schema=None, ops=None, files=None):
    """The exact argv this wrapper runs. `tools/import_drop.py` is invoked, never imported and
    never reimplemented: it owns idempotency, quarantine, the capture row and the move to
    `_done/`, and a second copy of any of that would be a second thing to keep correct.

    `schema` and `ops` are passed through rather than left to the importer's defaults. They had
    to be: this wrapper already accepted `--ops` and used it to ask `<ops>.runs` whether the
    importer had logged, while the importer always logged to a hardcoded `ops.runs`. Under any
    non-default pair the wrapper found no importer row and wrote a second heartbeat for the
    same import — `ops.runs` counting one import twice, which point 2 of this module's
    docstring says is the thing it exists to avoid.

    `files` names an explicit subset, used when some files in the drop folder are still being
    written (`settle`). Leaving the importer to scan the folder would import them anyway.
    """
    cmd = [sys.executable, str(Path(repo_root) / "tools" / "import_drop.py")]
    if drop is not None:
        cmd += ["--drop", str(drop)]
    if since:
        cmd += ["--since", since]
    if until:
        cmd += ["--until", until]
    if schema:
        cmd += ["--schema", schema]
    if ops:
        cmd += ["--ops", ops]
    for f in files or ():
        cmd += ["--file", str(f)]
    if commit:
        cmd.append("--commit")
    return cmd


def parse_importer_output(stdout):
    """`import_drop.py` prints one JSON object per file, then a prose summary line.

    Returns (atoms_written, per-file result dicts). Unparseable output yields zero atoms and
    no results, so a run whose output could not be read never claims that data arrived.
    """
    results = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            results.append(json.loads(line))
        except ValueError:
            continue
    return sum(int(r.get("atoms_written") or 0) for r in results), results


def classify(returncode, atoms, commit, reported):
    """(outcome, exit_code) for a completed importer process.

    The importer's exit codes are its contract — 0 clean, 1 per-file failures with the rest
    committed, 2 rolled back — and they are mapped rather than reinterpreted. With one
    correction, found by running the real subprocess rather than a double: an *uncaught*
    exception in `import_drop.main()` also leaves 1, because that is what the interpreter
    exits with on a traceback. `db.connect()` sits outside its guarded block, so an
    unreachable database from the child is exactly that shape.

    Treating that as "committed, some files failed" would report a rolled-back import as a
    partial success, which is the one thing this wrapper must never do. `reported` — the
    number of per-file JSON lines — separates them: the importer prints one for every file
    before it exits 1 legitimately, so exit 1 with nothing reported means it died before it
    got there, and nothing was written.
    """
    if returncode == 0:
        if not commit:
            return "dry_run", EXIT_OK
        return ("imported", EXIT_OK) if atoms else ("imported_no_new_atoms", EXIT_OK)
    if returncode == 1 and reported:
        return "partial_failure", EXIT_PARTIAL
    if returncode == 1:
        return "import_failed_before_reporting", EXIT_FAILED
    return "import_failed", EXIT_FAILED


# --------------------------------------------------------------------------- ops.runs

def db_now(cur):
    """The database's clock, not the laptop's. The marker that decides whether the importer
    logged has to be comparable with `started_at`, which Postgres stamps; a Mac whose clock
    has drifted a few seconds would otherwise miss the importer's row and write a duplicate."""
    cur.execute("select now()")
    return cur.fetchone()[0]


def importer_logged_since(cur, marker, ops="ops"):
    """The importer's own run row, if it wrote one after `marker`. Else None."""
    cur.execute(
        f"""select run_id from {ops}.runs
             where job_name = %s and started_at >= %s
             order by started_at desc limit 1""",
        (IMPORTER_JOB_NAME, marker))
    row = cur.fetchone()
    return row[0] if row else None


def write_heartbeat(cur, outcome, detail, rows_written, status, ops="ops"):
    """One row, under this wrapper's own job name, recording an outcome the importer did not.

    `rows_written` is atoms — 0 whenever nothing arrived, which is the number that must not be
    confused with "the job ran". The detail carries `new_data` explicitly rather than leaving
    a reader to infer it from a status, because inferring it from a status is the mistake that
    cost 43 days.
    """
    payload = dict(detail)
    payload.update({"outcome": outcome, "code_version": CODE_VERSION,
                    "new_data": bool(rows_written)})
    cur.execute(
        f"""insert into {ops}.runs (job_name, finished_at, status, rows_written, detail)
            values (%s, now(), %s, %s, %s) returning run_id""",
        (JOB_NAME, status, rows_written, json.dumps(payload)))
    return cur.fetchone()[0]


# --------------------------------------------------------------------------- the run

def log_line(log_path, record, importer_stdout=None):
    """Append to the local log. Outside the repository, on the Mac, never committed."""
    if log_path is None:
        return
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
        if importer_stdout:
            for line in importer_stdout.splitlines():
                fh.write("    " + line + "\n")


def run(drop=None, repo_root=ROOT, commit=True, since=None, until=None, ops="ops",
        connect=db.connect, runner=subprocess.run, log_path=None, env=None, schema=None,
        settler=settle):
    """One scheduled firing. Returns a record dict; raises nothing for ordinary failures.

    Caller supplies `connect` and `runner` so the whole path — success, failure, empty folder,
    unreachable database — is drivable in a test without a production database and without an
    importer subprocess.
    """
    env = os.environ if env is None else env
    if not IDENTIFIER.match(ops):
        # Interpolated into SQL below; a schema name cannot be a bind parameter.
        raise ValueError(f"not a plain schema identifier: {ops!r}")
    drop = Path(drop) if drop is not None else DEFAULT_DROP
    started = dt.datetime.now(dt.timezone.utc)
    record = {"job": JOB_NAME, "code_version": CODE_VERSION,
              "started_at": started.isoformat(), "drop": str(drop), "committed": bool(commit)}

    # The drop folder is checked BEFORE the lock is taken, because taking the lock creates
    # `<drop>/_state` and would therefore create the missing drop folder on the way — turning
    # the one prerequisite most likely to be wrong into a silently satisfied one. Nothing is
    # logged to a file here either: the log lives under the folder that does not exist.
    if not drop.is_dir():
        record.update({
            "outcome": "missing_drop_dir", "exit_code": EXIT_FAILED, "files_seen": None,
            "atoms_written": 0, "new_data": False, "heartbeat": None,
            "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "error": f"drop folder does not exist: {drop}. Scheduling an importer does not "
                     f"make a device produce an export."})
        return record

    try:
        with exclusive_lock(state_dir(drop) / LOCK_NAME):
            return _locked_run(record, drop, repo_root, commit, since, until, ops,
                               connect, runner, log_path, env, schema, settler)
    except Locked:
        # Not an error and not a success: nothing was attempted. No ops.runs row is written,
        # because the run that holds the lock is the one that will write it — a row here would
        # be a second record of a single import.
        record.update({"outcome": "skipped_locked", "exit_code": EXIT_LOCKED,
                       "files_seen": None, "atoms_written": 0, "new_data": False,
                       "heartbeat": None,
                       "note": "another import holds the lock; nothing was attempted"})
        log_line(log_path, record)
        return record


def _locked_run(record, drop, repo_root, commit, since, until, ops, connect, runner,
                log_path, env, schema=None, settler=settle):
    def finish(outcome, exit_code, **extra):
        # The importer's stdout is taken out of `extra` BEFORE it reaches the record: it is
        # per-file JSON carrying file names, it belongs in the log's indented block and in no
        # case in the one-line record that `render()` and the log's first line both read.
        stdout = extra.pop("importer_stdout", None)
        record.update({"outcome": outcome, "exit_code": exit_code,
                       "finished_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        record.update(extra)
        record.setdefault("new_data", bool(record.get("atoms_written")))
        log_line(log_path, record, stdout)
        return record

    # 1. Prerequisites, before anything expensive. A missing drop folder and an absent
    #    credential are failures of the *arrangement*, and they exit non-zero: a scheduled job
    #    that cannot possibly import must not report a quiet success.
    try:
        credential_source = load_credential(env)
        files = pending_files(drop)
    except PrerequisiteMissing as exc:
        return finish(exc.outcome, EXIT_FAILED, files_seen=None, atoms_written=0,
                      heartbeat=None, error=str(exc))
    record["credential_source"] = credential_source
    record["files_seen"] = len(files)

    # 1b. Which of those files have finished arriving. A file still being written is left
    #     where it is and reported; see `settle` for why waiting is the safe direction.
    ready, arriving = settler(files) if files else ([], [])
    record["files_ready"] = len(ready)
    record["files_still_arriving"] = len(arriving)

    # 2. Reach the database before spending twenty minutes parsing an export. An unreachable
    #    database is reported as itself and never as an empty day; with no database there is
    #    nowhere to write a heartbeat, so the non-zero exit and the local log are the signal.
    try:
        conn = connect()
    except Exception as exc:
        return finish("db_unreachable", EXIT_FAILED, atoms_written=0, heartbeat=None,
                      error=f"{type(exc).__name__}")
    try:
        marker = db_now(conn.cursor())
    except Exception as exc:
        _close(conn)
        return finish("db_unreachable", EXIT_FAILED, atoms_written=0, heartbeat=None,
                      error=f"{type(exc).__name__}")

    # 3. Nothing importable. Two different sentences, and they must not be one row.
    #
    #    An EMPTY drop folder is a successful run over no input: the job worked and capture did
    #    not happen. The importer returns before it connects so it writes no row, which is one
    #    of the gaps this wrapper exists to fill.
    #
    #    A drop folder holding only files that are STILL ARRIVING is a fault, not an empty day.
    #    It is reported with `status='error'` and a non-zero exit, because a file that never
    #    settles — a stalled iCloud materialisation, an interrupted AirDrop — would otherwise
    #    be indistinguishable from no file at all for as long as it stayed stuck, and that is
    #    the 43-day failure in miniature.
    if not ready:
        empty = not files
        outcome = "no_new_files" if empty else "files_still_arriving"
        detail = {"files_seen": len(files), "files_ready": 0,
                  "files_still_arriving": len(arriving), "atoms_written": 0,
                  "reason": "drop folder empty" if empty
                            else "every pending file was still being written",
                  "credential_source": credential_source}
        try:
            run_id = write_heartbeat(conn.cursor(), outcome, detail, 0,
                                     "ok" if empty else "error", ops)
            conn.commit()
        except Exception as exc:
            _rollback(conn)
            _close(conn)
            return finish("heartbeat_failed", EXIT_FAILED, atoms_written=0, heartbeat=None,
                          error=f"{type(exc).__name__}")
        _close(conn)
        if empty:
            return finish("no_new_files", EXIT_OK, atoms_written=0, heartbeat=str(run_id),
                          note="the job ran; no export was waiting. Whether a source has gone "
                               "quiet is check_freshness.py's question, not this one.")
        return finish("files_still_arriving", EXIT_PARTIAL, atoms_written=0,
                      heartbeat=str(run_id),
                      note="pending file(s) were still being written and were not imported; "
                           "they stay in the drop folder and the next run retries them.")
    _close(conn)

    # 4. The import itself, in its own process, with its own exit code. The ready files are
    #    named explicitly whenever the folder also holds files that are still arriving —
    #    otherwise the importer scans the folder and imports them anyway, and the settle gate
    #    would be a check whose result nothing acted on.
    proc = runner(import_command(repo_root, drop, commit, since, until, schema, ops,
                                 files=ready if arriving else None),
                  capture_output=True, text=True,
                  cwd=str(repo_root), env=_child_env(env, repo_root))
    atoms, per_file = parse_importer_output(proc.stdout)
    outcome, exit_code = classify(proc.returncode, atoms, commit, len(per_file))
    # A file the importer does not recognise is not a failure — it is left where it is, the
    # run exits 0, and the next run looks at it again. What it must not be is SILENT. The
    # importer prints `unrecognised_file_type` in its per-file JSON, which goes only to the
    # private log, so a misnamed export — `statement (1).csv`, a `.numbers` file, a Health
    # export saved as `health.xml` — would sit in the drop folder being ignored every night
    # while every summary line above it said the job succeeded. That is the shape of the
    # failure this whole path exists to catch, in miniature, so the count is surfaced.
    unrecognised = sum(1 for r in per_file if r.get("status") == "unrecognised_file_type")
    record.update({"atoms_written": atoms, "importer_exit": proc.returncode,
                   "unrecognised_files": unrecognised,
                   "files": [r.get("status") for r in per_file]})

    # 5. Fill the heartbeat gap, having first asked whether there is one. The importer's row
    #    is the record of an import; a second row describing the same import would make
    #    ops.runs count one import twice.
    conn = None
    try:
        conn = connect()
        cur = conn.cursor()
        importer_run = importer_logged_since(cur, marker, ops)
        if importer_run is None:
            detail = {"files_seen": len(files), "files_ready": len(ready),
                      "files_still_arriving": len(arriving),
                      "unrecognised_files": unrecognised, "atoms_written": atoms,
                      "importer_exit": proc.returncode, "committed": bool(commit),
                      "file_statuses": [r.get("status") for r in per_file],
                      "reason": "the importer's transaction wrote no run row",
                      "credential_source": credential_source}
            heartbeat = str(write_heartbeat(
                cur, outcome, detail, atoms,
                "ok" if outcome in OK_OUTCOMES else "error", ops))
            conn.commit()
        else:
            heartbeat = None
            record["import_drop_run_id"] = str(importer_run)
        _close(conn)
    except Exception as exc:
        if conn is not None:
            _rollback(conn)
            _close(conn)
        return finish(outcome, max(exit_code, EXIT_FAILED), heartbeat=None,
                      error=f"heartbeat write failed: {type(exc).__name__}",
                      importer_stdout=proc.stdout)

    return finish(outcome, exit_code, heartbeat=heartbeat, importer_stdout=proc.stdout,
                  stderr_tail=(proc.stderr or "").strip().splitlines()[-3:])


def _child_env(env, repo_root):
    """The importer's environment: repo root FIRST on PYTHONPATH, whatever was already there
    kept behind it. Overwriting PYTHONPATH outright was wrong in both directions — it discarded
    an entry the agent's own environment had set, and it made the child's import path depend on
    which parent started it. The repo still wins, which is the only part that mattered."""
    child = dict(env)
    root = str(repo_root)
    rest = [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p and p != root]
    child["PYTHONPATH"] = os.pathsep.join([root, *rest])
    return child


def _close(conn):
    with contextlib.suppress(Exception):
        conn.close()


def _rollback(conn):
    with contextlib.suppress(Exception):
        conn.rollback()


# --------------------------------------------------------------------------- launchd

def launchd_plist(repo_root=ROOT, drop=None, python=None, hour=LAUNCHD_HOUR,
                  minute=LAUNCHD_MINUTE):
    """The launchd job description, as a dict. Carries no credential, by construction.

    `SUPABASE_DB_URL` is deliberately absent: a plist in `~/Library/LaunchAgents` is
    world-readable by default and is exactly the kind of file that gets copied into a gist
    when something breaks. The agent reads the credential from the env file instead
    (`load_credential`), which is mode-checked at every run.
    """
    drop = Path(drop) if drop is not None else DEFAULT_DROP
    state = state_dir(drop)
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [python or sys.executable,
                             str(Path(repo_root) / "ops" / "capture_schedule.py"), "--run"],
        "WorkingDirectory": str(repo_root),
        "EnvironmentVariables": {"PYTHONPATH": str(repo_root), "PERSONAL_OS_DROP": str(drop)},
        "StartCalendarInterval": {"Hour": int(hour), "Minute": int(minute)},
        # RunAtLoad would fire an import the moment the agent is bootstrapped — a production
        # write as a side effect of installing a scheduler. Activation and the first import
        # are separate acts.
        "RunAtLoad": False,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(state / "launchd.out"),
        "StandardErrorPath": str(state / "launchd.err"),
    }


def emit_launchd(**kwargs):
    return plistlib.dumps(launchd_plist(**kwargs)).decode()


# --------------------------------------------------------------------------- cli

def render(record):
    """Counts and an outcome. Never a file name, never a value (RULE-29)."""
    parts = [f"{JOB_NAME}: {record['outcome']}",
             f"files_seen={record.get('files_seen')}",
             f"atoms_written={record.get('atoms_written', 0)}",
             f"new_data={'yes' if record.get('new_data') else 'no'}"]
    if record.get("files_still_arriving"):
        parts.append(f"still_arriving={record['files_still_arriving']}")
    if record.get("unrecognised_files"):
        parts.append(f"unrecognised={record['unrecognised_files']}")
    if record.get("heartbeat"):
        parts.append(f"ops.runs={record['heartbeat']}")
    if record.get("import_drop_run_id"):
        parts.append(f"import_drop.run={record['import_drop_run_id']}")
    if record.get("error"):
        parts.append(f"error={record['error']}")
    return "  ".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true", help="perform the scheduled import")
    ap.add_argument("--preflight", action="store_true",
                    help="check prerequisites and report; import nothing")
    ap.add_argument("--emit-launchd", action="store_true",
                    help="print the launchd plist on stdout. Installs nothing.")
    ap.add_argument("--dry-run", action="store_true",
                    help="invoke the importer without --commit (it rolls back)")
    ap.add_argument("--drop", default=None, help="drop folder (default ~/PersonalOS_Drop)")
    ap.add_argument("--since", help="earliest subject day, YYYY-MM-DD, passed through")
    ap.add_argument("--until", help="latest subject day, YYYY-MM-DD, passed through")
    ap.add_argument("--ops", default="ops", help="ops schema name (default: ops)")
    ap.add_argument("--schema", default=None, choices=("core", "core_dryrun"),
                    help="core schema passed to the importer (default: the importer's own)")
    # Operationally real, not test scaffolding: a drop folder on a network volume or an
    # iCloud-materialised directory settles more slowly than a local copy, and the numbers
    # that suit an SSD are not the numbers that suit either of those.
    ap.add_argument("--settle-interval", type=float, default=None, metavar="SECONDS",
                    help=f"seconds between the two observations that decide a file has "
                         f"finished arriving (default {SETTLE_INTERVAL_SECONDS})")
    ap.add_argument("--settle-timeout", type=float, default=None, metavar="SECONDS",
                    help=f"give up waiting for a file to stop growing after this long and "
                         f"report it instead of importing it (default {SETTLE_TIMEOUT_SECONDS})")
    a = ap.parse_args(argv)

    if a.emit_launchd:
        sys.stdout.write(emit_launchd(drop=a.drop))
        return EXIT_OK

    if a.preflight:
        drop = Path(a.drop) if a.drop else DEFAULT_DROP
        try:
            source = load_credential()
            files = pending_files(drop)
        except PrerequisiteMissing as exc:
            print(f"{JOB_NAME}: PREREQUISITE MISSING ({exc.outcome}): {exc}", file=sys.stderr)
            return EXIT_FAILED
        ready, arriving = settle(files) if files else ([], [])
        print(f"{JOB_NAME}: preflight ok  drop={drop}  pending_files={len(files)}  "
              f"ready={len(ready)}  still_arriving={len(arriving)}  credential={source}")
        print("  a pending file count is not freshness; check_freshness.py answers that.")
        return EXIT_OK

    if not a.run:
        ap.print_help()
        return EXIT_FAILED

    drop = Path(a.drop) if a.drop else DEFAULT_DROP
    settler = (lambda files: settle(files, a.settle_interval, a.settle_timeout)) \
        if (a.settle_interval is not None or a.settle_timeout is not None) else settle
    record = run(drop=drop, commit=not a.dry_run, since=a.since, until=a.until, ops=a.ops,
                 schema=a.schema, log_path=state_dir(drop) / LOG_NAME, settler=settler)
    stream = sys.stdout if record["exit_code"] in (EXIT_OK, EXIT_LOCKED) else sys.stderr
    print(render(record), file=stream)
    return record["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
