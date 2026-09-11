#!/usr/bin/env python3
"""The capture path, end to end, as PROCESSES — not as assertions about functions.

    python3 tools/capture_acceptance.py              # every case
    python3 tools/capture_acceptance.py --case 5     # one case
    python3 tools/capture_acceptance.py --list

**Why this exists as a runnable command rather than as more unit tests.** Every scheduling
behaviour in `tests/test_capture_schedule.py` is driven with an injected `runner` and an
injected `connect`: no importer subprocess, no database. That is the right shape for proving
what the wrapper does with an exit code, and it cannot prove the thing Joe actually needs
proven — that a file landing in a folder becomes rows, that running the command twice does not
double them, and that two copies of the command firing at once do not both import. A `flock`
tested against a fake is a test of the fake. The precedent is
`tools/reconstruction_acceptance.py`: a command that runs and reports, not a claim.

**What is real here.** The real `ops/capture_schedule.py` and the real `tools/import_drop.py`
run as separate operating-system processes, take a real `flock`, execute real SQL against a
real PostgreSQL 17 server, and their exit codes are read from the processes. The real
`tools/check_freshness.py` then reads back what landed.

**What is not real, and how it is contained.** The server is disposable: `initdb` into a
temporary directory this command creates, TCP disabled (`listen_addresses=''`), stopped and
deleted before the command returns. The fixture files are generated here, in that directory,
and are synthetic by construction — a step count and a heart rate on invented days. Nothing
outside the temporary directory is written and no production credential is used: every child
process gets `SUPABASE_DB_URL` replaced with an unroutable placeholder, and the shim below
refuses to start if a real one is still in the environment.

**RULE-01 and why this commits rather than rolls back (ADR-0140).** The constitution's bounded
exception for fixtures is a *transaction* that rolls back, and that boundary cannot express
what is under test here: case 5 is two processes, and two processes cannot share an uncommitted
transaction — an overlap test inside one transaction proves nothing about an overlap. The
isolation boundary used instead is the *server's lifetime*, which ADR-0082 already established
for the SQL suite. It is stronger in the ways that matter to RULE-01 and weaker in none: no
production table is touched, the instance is created by this command, it cannot be reached over
a network, and it is destroyed before the command exits, so no fabricated row can ever be read
as data. The schema pair is `core_dryrun`/`ops_dryrun`, the throwaway pair migration 0001
already names — never `core`, never `public`.

**How the real runners are pointed at the disposable server.** `lib/db.py` connects to Supabase
over pinned TLS and to nothing else, which is correct and stays correct: no test hook is added
to it. Instead this command writes a `sitecustomize.py` into its own temporary directory and
puts that directory on the children's `PYTHONPATH`. The shipped code therefore carries no
escape hatch at all — which is deliberately stricter than an environment variable inside
`lib/db.py` would be, because such a variable, once it exists, can redirect a production run.

Exit code 0 when every case passed, 1 otherwise.
"""
import argparse
import datetime as dt
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._import_fixture import SPINE, build_spine       # noqa: E402  (read-only reuse)

ROOT = Path(__file__).resolve().parents[1]
CORE = "core_dryrun"
OPS = "ops_dryrun"
ANALYSIS = "analysis_dryrun"            # deliberately never created: the panel is optional
PLACEHOLDER_URL = "postgresql://acceptance@127.0.0.1:1/disposable"

SHIM = '''\
"""Written by tools/capture_acceptance.py into its own temporary directory.

Redirects `lib.db.connect` at interpreter start to the disposable server named by
PERSONAL_OS_ACCEPTANCE_SOCKET. This file never exists inside the repository and is on the
path of no process but the harness's own children.
"""
import getpass
import os

_socket = os.environ.get("PERSONAL_OS_ACCEPTANCE_SOCKET")
if _socket:
    _url = os.environ.get("SUPABASE_DB_URL", "")
    if "supabase" in _url.lower():
        raise SystemExit(
            "capture_acceptance: a production URL is still in the child environment; refusing")
    import pg8000.dbapi
    import lib.db

    def _connect():
        return pg8000.dbapi.connect(user=getpass.getuser(), database="postgres",
                                    unix_sock=_socket, timeout=10)

    lib.db.connect = _connect
'''


# --------------------------------------------------------------------------- fixtures

def health_export(records):
    body = "\n".join(records)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<HealthData locale="en_US">\n'
            f' <ExportDate value="2026-01-01 12:00:00 -0500"/>\n{body}\n</HealthData>\n')


def step_record(day, value, hour=10):
    """One synthetic StepCount. `day` is a date; the value is invented."""
    stamp = f"{day.isoformat()} {hour:02d}:00:00 -0400"
    return (f' <Record type="HKQuantityTypeIdentifierStepCount" sourceName="AcceptanceHarness" '
            f'unit="count" creationDate="{stamp}" startDate="{stamp}" endDate="{stamp}" '
            f'value="{value}"/>')


def hr_record(day, value=55, hour=7):
    """One synthetic RestingHeartRate. Inside the registry's 20..200 plausible range."""
    stamp = f"{day.isoformat()} {hour:02d}:00:00 -0400"
    return (f' <Record type="HKQuantityTypeIdentifierRestingHeartRate" '
            f'sourceName="AcceptanceHarness" unit="count/min" creationDate="{stamp}" '
            f'startDate="{stamp}" endDate="{stamp}" value="{value}"/>')


def write_export(path, days, first_value=1000):
    path.write_text(health_export(
        [step_record(d, first_value + 10 * i) for i, d in enumerate(days)]))
    return path


# --------------------------------------------------------------------------- the server

class Disposable:
    """A PostgreSQL 17 server that exists only for the duration of this command."""

    def __init__(self, root):
        self.root = Path(root)
        self.data = self.root / "data"
        self.sockets = self.root / "socket"
        self.binaries = pg_bin()
        self.socket = None
        self.started = False

    def start(self):
        self.sockets.mkdir(mode=0o700, parents=True)
        subprocess.run([str(self.binaries / "initdb"), "-D", str(self.data),
                        "--auth-local=trust", "--auth-host=reject", "--encoding=UTF8",
                        "--no-locale"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run([str(self.binaries / "pg_ctl"), "-D", str(self.data), "-l",
                        str(self.root / "server.log"), "-o",
                        f"-k {self.sockets} -p 55433 -c listen_addresses=''", "start"],
                       check=True, stdout=subprocess.DEVNULL)
        self.socket = self.sockets / ".s.PGSQL.55433"
        self.started = True
        return self

    def stop(self):
        """Returns True when the server is proven down (or was never up)."""
        if not self.started:
            return True                 # nothing was started, so nothing can still be running
        stopped = subprocess.run([str(self.binaries / "pg_ctl"), "-D", str(self.data),
                                  "-m", "fast", "stop"], stdout=subprocess.DEVNULL)
        # Never delete a data directory whose server might still be running.
        return stopped.returncode == 0

    def connect(self):
        import pg8000.dbapi
        return pg8000.dbapi.connect(user=getpass.getuser(), database="postgres",
                                    unix_sock=str(self.socket), timeout=10)


def pg_bin():
    located = shutil.which("initdb")
    candidates = ([str(Path(located).parent)] if located else []) + [
        "/opt/homebrew/opt/postgresql@17/bin", "/usr/local/opt/postgresql@17/bin"]
    for base in candidates:
        binary = Path(base) / "initdb"
        if binary.exists():
            version = subprocess.run([str(binary), "--version"], check=True,
                                     capture_output=True, text=True).stdout
            if re.search(r"\(PostgreSQL\) 17[. ]", version):
                return Path(base)
    raise RuntimeError("PostgreSQL 17 binaries are required to run the capture acceptance "
                       "cases; install them, or run this where they exist.")


# --------------------------------------------------------------------------- the harness

class Harness:
    def __init__(self, root, server):
        self.root = Path(root)
        self.server = server
        self.drop = self.root / "drop"
        self.shim_dir = self.root / "shim"
        self.shim_dir.mkdir(parents=True, exist_ok=True)
        (self.shim_dir / "sitecustomize.py").write_text(SHIM)
        self.drop.mkdir(parents=True, exist_ok=True)

    # -- environment -------------------------------------------------------
    def env(self):
        env = dict(os.environ)
        # The production URL is inherited by every shell in this project (OQ-80). It is
        # removed and replaced rather than merely removed, because `capture_schedule`'s
        # prerequisite check requires the variable to be PRESENT; a placeholder satisfies
        # that check and connects to nothing, and the shim refuses to start if a real one
        # somehow survives.
        env["SUPABASE_DB_URL"] = PLACEHOLDER_URL
        env["PERSONAL_OS_ACCEPTANCE_SOCKET"] = str(self.server.socket)
        env["PYTHONPATH"] = os.pathsep.join([str(self.shim_dir), str(ROOT)])
        env["PERSONAL_OS_DROP"] = str(self.drop)
        env.pop("PERSONAL_OS_TEST_SOCKET", None)
        env.pop("PERSONAL_OS_ENV_FILE", None)
        return env

    # -- the real commands -------------------------------------------------
    def schedule(self, *args, **kwargs):
        return self._run([sys.executable, str(ROOT / "ops" / "capture_schedule.py"), "--run",
                          "--drop", str(self.drop), "--schema", CORE, "--ops", OPS, *args],
                         **kwargs)

    def freshness(self, *args):
        return self._run([sys.executable, str(ROOT / "tools" / "check_freshness.py"),
                          "--core", CORE, "--analysis", ANALYSIS, "--ops", OPS, *args])

    def _run(self, cmd, **kwargs):
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                              env=self.env(), **kwargs)

    def spawn_schedule(self):
        return subprocess.Popen(
            [sys.executable, str(ROOT / "ops" / "capture_schedule.py"), "--run",
             "--drop", str(self.drop), "--schema", CORE, "--ops", OPS],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(ROOT), env=self.env())

    # -- reading the result ------------------------------------------------
    def scalar(self, sql, args=()):
        conn = self.server.connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def rows(self, sql, args=()):
        conn = self.server.connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            return cur.fetchall()
        finally:
            conn.close()

    def atoms(self):
        return self.scalar(f"select count(*) from {CORE}.atoms")

    def captures(self):
        return self.scalar(f"select count(*) from {CORE}.raw_captures")

    def runs(self, job=None):
        if job:
            return self.rows(f"select status, rows_written, detail from {OPS}.runs "
                             f"where job_name = %s order by finished_at", (job,))
        return self.rows(f"select job_name, status, rows_written from {OPS}.runs "
                         f"order by finished_at")

    def done_dir(self):
        return self.drop / "_done"


def build_schema(server):
    """The spine, COMMITTED, from the real migration files (see the module docstring)."""
    conn = server.connect()
    try:
        cur = conn.cursor()
        build_spine(cur, SPINE, CORE, OPS)
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- cases

class Failure(AssertionError):
    pass


def require(condition, message):
    if not condition:
        raise Failure(message)


def case_1_new_input_is_discovered_and_processed(h, today):
    """A supported file appears in the drop folder and becomes atoms."""
    days = [today - dt.timedelta(days=n) for n in (2, 1)]
    write_export(h.drop / "export.xml", days)

    proc = h.schedule()
    require(proc.returncode == 0, f"expected exit 0, got {proc.returncode}: {proc.stderr}")
    require("imported" in proc.stdout, f"expected an 'imported' outcome: {proc.stdout}")
    require("new_data=yes" in proc.stdout, f"expected new_data=yes: {proc.stdout}")

    require(h.atoms() == 2, f"expected 2 atoms, found {h.atoms()}")
    require(h.captures() == 1, f"expected 1 capture row, found {h.captures()}")
    require((h.done_dir() / "export.xml").is_file(),
            "the imported file was not moved to _done/")
    require(not (h.drop / "export.xml").exists(),
            "the imported file is still in the drop folder and would be re-read")

    importer = h.runs("import_drop")
    require(len(importer) == 1, f"expected one import_drop run row, found {len(importer)}")
    require(importer[0][0] == "ok", f"import_drop row is not ok: {importer[0]}")
    require(importer[0][1] == 2, f"import_drop row claims {importer[0][1]} rows, expected 2")
    require(not h.runs("capture_schedule"),
            "the wrapper wrote a second heartbeat for an import the importer already logged")
    return f"2 atoms from 1 file; ops.runs: 1 import_drop row, 0 duplicate heartbeats"


def case_2_repeated_input_is_not_duplicated(h, today):
    """The same export is dropped again. Nothing is written twice."""
    before_atoms, before_captures = h.atoms(), h.captures()
    days = [today - dt.timedelta(days=n) for n in (2, 1)]
    write_export(h.drop / "export.xml", days)          # byte-identical to case 1

    proc = h.schedule()
    require(proc.returncode == 0, f"expected exit 0, got {proc.returncode}: {proc.stderr}")
    require("new_data=no" in proc.stdout,
            f"a re-import of the same file reported new data: {proc.stdout}")
    require(h.atoms() == before_atoms,
            f"atoms moved from {before_atoms} to {h.atoms()} on a duplicate import")
    require(h.captures() == before_captures,
            f"a second capture row was written for the same file and window")
    return f"atoms unchanged at {before_atoms}; capture rows unchanged at {before_captures}"


def case_2b_overlapping_window_adds_only_what_is_new(h, today):
    """A wider export covering the same days plus one more adds one atom, not three."""
    before = h.atoms()
    days = [today - dt.timedelta(days=n) for n in (2, 1, 0)]
    # `classify()` recognises `export.xml` and `*_export.xml`, and nothing else ending in
    # `.xml`. A name outside that set is `unrecognised_file_type` — see case 4.
    write_export(h.drop / "wider_export.xml", days)

    proc = h.schedule()
    require(proc.returncode == 0, f"expected exit 0, got {proc.returncode}: {proc.stderr}")
    require(h.atoms() == before + 1,
            f"expected exactly one new atom, atoms went {before} -> {h.atoms()}")
    require(not list(h.drop.glob("*.xml")), "the wider export was not filed away")
    return f"atoms {before} -> {h.atoms()}: the two overlapping days were recognised"


def case_3_missing_input_is_not_a_successful_capture(h, today):
    """Three shapes of 'nothing arrived', each reported as itself."""
    # (a) an empty drop folder: the job succeeded, capture did not happen.
    proc = h.schedule()
    require(proc.returncode == 0, f"empty folder should exit 0, got {proc.returncode}")
    require("no_new_files" in proc.stdout, f"expected no_new_files: {proc.stdout}")
    require("new_data=no" in proc.stdout, f"expected new_data=no: {proc.stdout}")
    heartbeats = h.runs("capture_schedule")
    require(heartbeats, "an empty run wrote no heartbeat at all — it would be invisible")
    status, rows_written, detail = heartbeats[-1]
    require(status == "ok" and rows_written == 0,
            f"empty-folder heartbeat should be ok with 0 rows, got {status}/{rows_written}")
    payload = detail if isinstance(detail, dict) else json.loads(detail)
    require(payload["new_data"] is False,
            "the heartbeat does not say new_data=false, so 'the job ran' and 'data arrived' "
            "are not separable from the row")

    # (b) a drop folder that does not exist is a broken arrangement, not an empty day.
    missing = h.root / "nowhere"
    proc = h._run([sys.executable, str(ROOT / "ops" / "capture_schedule.py"), "--run",
                   "--drop", str(missing), "--schema", CORE, "--ops", OPS])
    require(proc.returncode == 2, f"a missing drop folder should exit 2, got {proc.returncode}")
    require(not missing.exists(), "the missing drop folder was CREATED, hiding the fault")

    # (c) an unreadable file is a failure, not an absence.
    bad = h.drop / "unreadable_export.xml"
    write_export(bad, [today])
    bad.chmod(0o000)
    try:
        proc = h.schedule()
        require(proc.returncode == 1,
                f"an unreadable file should exit 1 (partial), got {proc.returncode}")
        require(bad.exists(), "an unreadable file was moved out of the drop folder")
    finally:
        bad.chmod(0o600)
        bad.unlink()
    return "empty=0/no_new_files, missing folder=2 and not created, unreadable=1 and retained"


def case_3b_an_unrecognised_file_is_reported_not_silently_ignored(h, today):
    """A misnamed export imports nothing, exits 0, stays put — and SAYS SO."""
    before = h.atoms()
    stray = h.drop / "health.xml"                 # not export.xml, not *_export.xml
    write_export(stray, [today - dt.timedelta(days=1)], first_value=9000)

    proc = h.schedule()
    require(proc.returncode == 0,
            f"an unrecognised file is not a failure; got exit {proc.returncode}")
    require("unrecognised=1" in proc.stdout,
            f"the run did not report the unrecognised file: {proc.stdout!r}. A misnamed "
            f"export would sit in the drop folder being ignored every night while every "
            f"line of the summary said the job succeeded.")
    require(h.atoms() == before, f"an unrecognised file wrote atoms: {before} -> {h.atoms()}")
    require(stray.exists(), "an unrecognised file was moved out of the drop folder")
    stray.unlink()
    return "exit 0, 0 atoms, file retained, and 'unrecognised=1' on the summary line"


def case_4_processing_failure_is_visible_and_retryable(h, today):
    """A corrupt file fails loudly, stays put, and the next run imports its replacement."""
    before = h.atoms()
    corrupt = h.drop / "export.zip"
    corrupt.write_bytes(b"PK\x03\x04 this is not a zip file")

    proc = h.schedule()
    require(proc.returncode == 1, f"a corrupt file should exit 1, got {proc.returncode}")
    require(h.atoms() == before, f"a failed file wrote atoms: {before} -> {h.atoms()}")
    require(corrupt.exists(), "a failed file was moved to _done/ and would never be retried")
    failed = [r for r in h.runs() if r[1] == "error"]
    require(failed, "a failed import left no error row in ops.runs — it is invisible")

    corrupt.unlink()
    replacement = write_export(h.drop / "export.xml", [today - dt.timedelta(days=5)])
    proc = h.schedule()
    require(proc.returncode == 0, f"the retry should exit 0, got {proc.returncode}: {proc.stderr}")
    require(h.atoms() == before + 1, f"the retry imported nothing: {before} -> {h.atoms()}")
    require((h.done_dir() / replacement.name).is_file(), "the retried file was not filed away")
    return f"corrupt: exit 1, 0 atoms, file retained, error row written; retry: exit 0, +1 atom"


def case_5_concurrent_invocation_does_not_double_process(h, today):
    """Two real processes fire at once. One imports; the other imports nothing."""
    before = h.atoms()
    days = [today - dt.timedelta(days=n) for n in (12, 11, 10, 9, 8, 7)]
    write_export(h.drop / "export.xml", days, first_value=5000)

    first = h.spawn_schedule()
    second = h.spawn_schedule()
    out1, err1 = first.communicate(timeout=180)
    out2, err2 = second.communicate(timeout=180)
    codes = sorted([first.returncode, second.returncode])

    require(3 in codes,
            f"neither process was locked out; exit codes {codes}. stdout: {out1!r} {out2!r}")
    require(codes.count(3) == 1, f"both processes were locked out; exit codes {codes}")
    require("skipped_locked" in (out1 + out2),
            f"the locked-out run did not say so: {out1!r} {out2!r}")
    require(h.atoms() == before + len(days),
            f"expected {len(days)} new atoms, got {h.atoms() - before} — a double import "
            f"writes more, a lost import writes fewer")
    imports = [r for r in h.runs() if r[0] == "import_drop"]
    require(len([r for r in imports if r[2]]) >= 1, "no import row recorded the atoms")
    return (f"exit codes {codes}; {len(days)} atoms written exactly once by one of two "
            f"simultaneous processes")


def case_6_a_file_still_arriving_is_not_imported(h, today):
    """A file still being written is left alone and reported, then imported once it finishes.

    The wait is real: a writer process appends to the file for roughly twenty seconds while the
    scheduler watches it with a three-second patience. The first run must refuse it; the second,
    after the writer has finished, must take it.
    """
    before_atoms, before_captures = h.atoms(), h.captures()
    growing = h.drop / "slow_export.xml"
    day = today - dt.timedelta(days=20)
    growing.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<HealthData locale="en_US">\n')

    writer = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import time
            for i in range(20):
                with open({str(growing)!r}, "a") as fh:
                    fh.write({step_record(day, 0)!r}.replace('value="0"',
                             'value="%d"' % (3000 + i)).replace('10:00:00',
                             '%02d:00:00' % i) + "\\n")
                    fh.flush()
                time.sleep(1)
            with open({str(growing)!r}, "a") as fh:
                fh.write("</HealthData>\\n")
        """)])
    try:
        proc = h.schedule("--settle-interval", "1", "--settle-timeout", "3")
        require(proc.returncode == 1,
                f"a drop folder holding only a growing file should exit 1, got "
                f"{proc.returncode}: {proc.stdout} {proc.stderr}")
        require("files_still_arriving" in (proc.stdout + proc.stderr),
                f"the outcome does not name the condition: {proc.stdout} {proc.stderr}")
        require(h.atoms() == before_atoms,
                f"a partially written file was imported: atoms {before_atoms} -> {h.atoms()}")
        require(h.captures() == before_captures,
                "an append-only capture row was written for a file still being written")
        require(growing.exists(), "the unfinished file was moved out of the drop folder")
        errors = [r for r in h.runs("capture_schedule") if r[0] == "error"]
        require(errors,
                "a stuck file left no error row — it is indistinguishable from an empty day")
    finally:
        writer.wait(timeout=120)

    # The writer has finished. The same file, untouched, now imports.
    proc = h.schedule("--settle-interval", "1", "--settle-timeout", "30")
    require(proc.returncode == 0,
            f"the settled retry exited {proc.returncode}: {proc.stdout} {proc.stderr}")
    require(h.captures() == before_captures + 1,
            f"the finished file was not imported on the later run: capture rows "
            f"{before_captures} -> {h.captures()}")
    require(h.atoms() > before_atoms,
            f"the finished file produced no atoms: {before_atoms} -> {h.atoms()}")
    return (f"growing: exit 1, 0 atoms, 0 capture rows, error row written; "
            f"finished: exit 0, +{h.atoms() - before_atoms} atoms")


def case_7_heartbeat_success_does_not_conceal_stale_evidence(h, today):
    """The job says ok. The data says stale. Both are true and only one is about capture."""
    for leftover in list(h.drop.glob("*")):
        if leftover.is_file():
            leftover.unlink()
    # `resting_hr` (limit 3 days) rather than `steps`: earlier cases wrote steps for days near
    # today, so steps is legitimately fresh and proving anything with it would require first
    # arranging for it not to be. The point of the case is the RELATIONSHIP between a green job
    # and a stale series, and it needs a series only this case writes.
    old_day = today - dt.timedelta(days=40)
    (h.drop / "export.xml").write_text(health_export([hr_record(old_day)]))

    proc = h.schedule()
    require(proc.returncode == 0, f"the import should succeed, got {proc.returncode}: {proc.stderr}")
    require("new_data=yes" in proc.stdout, f"expected new data: {proc.stdout}")
    ok_rows = [r for r in h.runs() if r[1] == "ok"]
    require(ok_rows, "no successful run row exists to be misread as evidence of freshness")

    fresh = h.freshness()
    require(fresh.returncode == 1,
            f"freshness exited {fresh.returncode}; a 40-day-old resting_hr series must fail. "
            f"stdout: {fresh.stdout} stderr: {fresh.stderr}")
    require("resting_hr" in fresh.stdout, f"the stale metric is not named: {fresh.stdout}")
    require("STALE" in fresh.stdout, f"the report does not say STALE: {fresh.stdout}")

    report = json.loads(h.freshness("--json", "--no-log").stdout)
    row = [r for r in report["stale"] if r["metric"] == "resting_hr"]
    require(row, f"resting_hr is not in the stale list: {report['counts']}")
    require(row[0]["elapsed_days"] >= 40,
            f"elapsed days reported as {row[0]['elapsed_days']}, expected at least 40")
    require(report["import_schedule"]["state"] == "fresh",
            f"the schedule has reported in this run and should be fresh: "
            f"{report['import_schedule']}")
    return (f"capture_schedule ok and new_data=yes, while check_freshness exits 1 with "
            f"resting_hr {row[0]['elapsed_days']}d stale")


def case_8_a_dry_run_writes_nothing_and_says_so(h, today):
    """The read-only mode is read-only, as a process, against a real database."""
    before_atoms, before_captures = h.atoms(), h.captures()
    write_export(h.drop / "export.xml", [today - dt.timedelta(days=3)], first_value=4242)

    proc = h.schedule("--dry-run")
    require(proc.returncode == 0, f"a dry run should exit 0, got {proc.returncode}: {proc.stderr}")
    require("dry_run" in proc.stdout, f"the outcome is not dry_run: {proc.stdout}")
    require(h.atoms() == before_atoms, f"a dry run wrote atoms: {before_atoms} -> {h.atoms()}")
    require(h.captures() == before_captures, "a dry run wrote a capture row")
    require((h.drop / "export.xml").exists(), "a dry run moved the file to _done/")
    (h.drop / "export.xml").unlink()
    return f"atoms and capture rows unchanged at {before_atoms}/{before_captures}"


CASES = [
    ("new input is discovered and processed", case_1_new_input_is_discovered_and_processed),
    ("repeated input is not duplicated", case_2_repeated_input_is_not_duplicated),
    ("an overlapping window adds only what is new", case_2b_overlapping_window_adds_only_what_is_new),
    ("an unrecognised file is reported, not silently ignored",
     case_3b_an_unrecognised_file_is_reported_not_silently_ignored),
    ("missing or unreadable input is not a successful capture",
     case_3_missing_input_is_not_a_successful_capture),
    ("processing failure is visible and retryable",
     case_4_processing_failure_is_visible_and_retryable),
    ("concurrent invocation does not double-process",
     case_5_concurrent_invocation_does_not_double_process),
    ("a file still arriving is not imported", case_6_a_file_still_arriving_is_not_imported),
    ("heartbeat success does not conceal stale evidence",
     case_7_heartbeat_success_does_not_conceal_stale_evidence),
    ("a dry run writes nothing", case_8_a_dry_run_writes_nothing_and_says_so),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=int, action="append",
                    help="run only this case number (repeatable). Cases share state and run "
                         "in order; a later case run alone may have nothing to build on.")
    ap.add_argument("--list", action="store_true", help="list the cases and exit")
    ap.add_argument("--keep", action="store_true",
                    help="keep the temporary directory (it holds the server log)")
    a = ap.parse_args(argv)

    if a.list:
        for n, (name, _) in enumerate(CASES, 1):
            print(f"  {n}  {name}")
        return 0

    selected = [(n, name, fn) for n, (name, fn) in enumerate(CASES, 1)
                if not a.case or n in a.case]

    # `/tmp`, not the platform default. On macOS TMPDIR is a long `/var/folders/...` path and
    # the resulting Unix socket exceeds `sun_path`'s 103-byte limit, so the server refuses to
    # start with no log to say why. `tools/test_local_sql.py` pins the same directory for the
    # same reason.
    root = Path(tempfile.mkdtemp(prefix="cap-acc-", dir="/tmp"))
    server = Disposable(root)
    results, failures = [], 0
    started = time.time()
    print(f"capture acceptance — disposable PostgreSQL, {len(selected)} case(s)")
    print(f"  temporary root: {root}")
    try:
        server.start()
        build_schema(server)
        h = Harness(root, server)
        today = h.scalar("select current_date")
        for n, name, fn in selected:
            try:
                detail = fn(h, today)
                results.append((n, name, "PASS", detail))
                print(f"  PASS  {n}. {name}\n          {detail}")
            except Exception as exc:
                failures += 1
                results.append((n, name, "FAIL", f"{type(exc).__name__}: {exc}"))
                print(f"  FAIL  {n}. {name}\n          {type(exc).__name__}: {exc}")
    finally:
        down = server.stop()
        if a.keep or not down:
            print(f"  temporary root retained: {root}"
                  + ("" if down else "  (SHUTDOWN UNPROVEN — do not reuse this directory)"))
        else:
            shutil.rmtree(root, ignore_errors=True)

    elapsed = time.time() - started
    passed = len(results) - failures
    print(f"\n{passed} of {len(results)} acceptance cases passed in {elapsed:.0f}s")
    if failures:
        print("NOT ACCEPTED — the capture path does not do what the cases require.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
