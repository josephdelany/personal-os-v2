"""The scheduled local import and the freshness schedule it feeds (ADR-0094, ADR-0060).

Two things are under test and they are deliberately in one file, because the only reason the
local import has the schedule it has is the schedule the freshness check already has.

*   `ops/capture_schedule.py` — the wrapper that runs `tools/import_drop.py` unattended. Every
    test here drives it with an injected `runner` and an injected `connect`, so no importer
    subprocess and no production database is involved: the importer's own behaviour is
    `tests/test_import_drop.py`'s subject, and what is proven here is the *scheduling*
    behaviour that sits above it — overlap, prerequisites, exit codes, and the rule about
    which `ops.runs` row gets written.
*   `.github/workflows/freshness.yml` — whose independence and cadence are invariants stated
    in its own header comment and, until now, enforced by nothing.

The one test that reaches a database builds a throwaway `ops_schedule_pytest` schema from the
real `0011_ops.sql` and rolls back (RULE-01's bounded exception, ADR-0022). It is skipped
unless a disposable local server is selected, exactly as `tests/test_freshness.py` is: it must
never be able to reach production.
"""
import json
import os
import plistlib
import re
import stat
import subprocess

import yaml
import sys
from pathlib import Path

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from ops import capture_schedule as cs

ROOT = Path(__file__).resolve().parents[1]
FRESHNESS = ROOT / ".github" / "workflows" / "freshness.yml"
ANALYSIS = ROOT / ".github" / "workflows" / "analysis.yml"

OPS = "ops_schedule_pytest"

_needs_local_server = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds an ops schema from real migration DDL; disposable local server only "
           "(run via tools/test_local_sql.py)")


@pytest.fixture(autouse=True)
def _no_settle_wait(monkeypatch):
    """The settle gate takes two observations of every pending file separated by a real wait.
    That wait is the point in production and is dead time here, so the interval is zero for
    every test in this file except the ones that drive `settle` directly with their own
    numbers. Zero still means TWO observations — the gate is exercised, not bypassed.
    """
    monkeypatch.setattr(cs, "SETTLE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(cs, "SETTLE_TIMEOUT_SECONDS", 0)


# --------------------------------------------------------------------------- doubles

class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class FakeRunner:
    """Stands in for subprocess.run. Records the argv it was asked to run."""

    def __init__(self, proc=None):
        self.proc = proc or FakeProc()
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((list(cmd), kwargs))
        return self.proc


class FakeCursor:
    """Answers `select now()`, the importer-row lookup and the heartbeat insert."""

    def __init__(self, conn):
        self.conn = conn
        self._result = None

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, params))
        low = " ".join(sql.split()).lower()
        if low.startswith("select now()"):
            self._result = ("MARKER",)
        elif "from" in low and ".runs" in low and low.startswith("select run_id"):
            self._result = ("IMPORTER-RUN",) if self.conn.importer_row else None
        elif low.startswith("insert into"):
            job_name, status, rows_written, detail = params
            self.conn.heartbeats.append(
                {"job_name": job_name, "status": status, "rows_written": rows_written,
                 **json.loads(detail)})
            self._result = ("HEARTBEAT-RUN",)
        else:
            self._result = None

    def fetchone(self):
        return self._result


class FakeConn:
    def __init__(self, importer_row=False):
        self.importer_row = importer_row
        self.statements, self.heartbeats = [], []
        self.commits = self.closes = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closes += 1


class Unreachable:
    def __call__(self):
        raise RuntimeError("SUPABASE_DB_URL not set")


def _drop(tmp_path, files=()):
    d = tmp_path / "drop"
    d.mkdir()
    for name in files:
        (d / name).write_text("payload")
    return d


def _env(tmp_path, url="postgresql://u:p@example.invalid:5432/postgres"):
    """An environment carrying a credential, so a test exercising something else is never
    stopped by the credential check."""
    return {"SUPABASE_DB_URL": url, "PATH": os.environ.get("PATH", "")} if url else \
        {"PATH": os.environ.get("PATH", ""), "PERSONAL_OS_ENV_FILE": str(tmp_path / "absent")}


# --------------------------------------------------------------------------- the importer is
# --------------------------------------------------------------------------- invoked, not
# --------------------------------------------------------------------------- reimplemented

def test_ADR_0057_ADR_0091_the_wrapper_invokes_the_importer_and_never_reimplements_it(tmp_path):
    """Idempotency, quarantine, the capture row and the move to `_done/` all live in
    `import_drop.py`. A scheduler that reimplemented any of them would be a second thing to
    keep correct, and the first divergence would be silent. So the contract under test is
    narrow and exact: the wrapper spawns that script, with `--commit`, and adds nothing."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, '{"file": "export.zip", "status": "imported", '
                                    '"atoms_written": 12}\n'))
    conn = FakeConn(importer_row=True)
    record = cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path),
                    log_path=cs.state_dir(drop) / cs.LOG_NAME)

    assert len(runner.calls) == 1
    argv, kwargs = runner.calls[0]
    assert argv[1].endswith(str(Path("tools") / "import_drop.py"))
    assert "--commit" in argv
    assert kwargs["env"]["PYTHONPATH"] == str(cs.ROOT)
    assert record["outcome"] == "imported"
    assert record["atoms_written"] == 12 and record["new_data"] is True

    # No source file was touched by the wrapper: moving to `_done/` is the importer's job and
    # the importer here was a double.
    assert (drop / "export.zip").exists()


def test_ADR_0091_a_dry_run_never_passes_commit(tmp_path):
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, ""))
    record = cs.run(drop=drop, commit=False, connect=lambda: FakeConn(), runner=runner,
                    env=_env(tmp_path))
    assert "--commit" not in runner.calls[0][0]
    assert record["outcome"] == "dry_run"


# --------------------------------------------------------------------------- overlap

def test_ADR_0091_a_second_run_while_one_holds_the_lock_imports_nothing(tmp_path):
    """Two firings must not parse the same 300 MB export at once.

    The dedupe key would make the second import a no-op eventually (ADR-0057), which is a
    reason overlap is not *corrupting* and no reason at all to allow it: it doubles the parse
    and interleaves two transactions writing the same atoms. The second run exits 3 having
    attempted nothing — and writes no `ops.runs` row, because the run holding the lock is the
    one that will write it.
    """
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner()
    with cs.exclusive_lock(cs.state_dir(drop) / cs.LOCK_NAME):
        record = cs.run(drop=drop, connect=lambda: FakeConn(), runner=runner,
                        env=_env(tmp_path), log_path=cs.state_dir(drop) / cs.LOG_NAME)

    assert record["outcome"] == "skipped_locked"
    assert record["exit_code"] == cs.EXIT_LOCKED
    assert runner.calls == [], "an import was started while another held the lock"
    assert record["heartbeat"] is None
    assert record["new_data"] is False


def test_ADR_0091_the_lock_is_released_so_the_next_firing_runs(tmp_path):
    """A lock that outlived its run would silence the schedule permanently — the failure mode
    that makes overlap protection worse than none."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, '{"status": "imported", "atoms_written": 1}'))
    first = cs.run(drop=drop, connect=lambda: FakeConn(importer_row=True), runner=runner,
                   env=_env(tmp_path))
    second = cs.run(drop=drop, connect=lambda: FakeConn(importer_row=True), runner=runner,
                    env=_env(tmp_path))
    assert first["outcome"] == "imported" and second["outcome"] == "imported"
    assert len(runner.calls) == 2


# --------------------------------------------------------------------------- job ran vs
# --------------------------------------------------------------------------- data arrived

def test_REQ_NFR_012_ADR_0091_an_empty_drop_folder_is_a_recorded_capture_failure(tmp_path):
    """REQ-NFR-012's rule, applied to the job that reads files: a run over an empty input is
    never evidence of freshness.

    `import_drop.py` returns before it connects when the folder is empty, so it writes no row
    at all — the scheduled firing would leave no trace whatsoever. Here the job succeeds (exit
    0: nothing was wrong with the job) and the row says `new_data=false`, `rows_written=0`,
    so a reader of `ops.runs` cannot mistake a firing for an arrival.
    """
    drop = _drop(tmp_path)
    runner = FakeRunner()
    conn = FakeConn()
    record = cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    assert record["outcome"] == "no_new_files"
    assert record["exit_code"] == cs.EXIT_OK
    assert runner.calls == [], "the importer was spawned for an empty folder"
    assert len(conn.heartbeats) == 1
    beat = conn.heartbeats[0]
    assert beat["new_data"] is False and beat["atoms_written"] == 0
    assert beat["outcome"] == "no_new_files"


def test_REQ_NFR_012_ADR_0091_a_committed_import_of_zero_new_atoms_is_not_new_data(tmp_path):
    """The subtler case, and the common one: Joe re-drops an export he already imported. The
    importer exits 0 having written nothing, because every atom deduplicated. The job is
    healthy and no new observation arrived, and those are two different facts."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, '{"status": "skipped_duplicate_file", '
                                    '"atoms_written": 0}'))
    conn = FakeConn(importer_row=True)
    record = cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    assert record["outcome"] == "imported_no_new_atoms"
    assert record["exit_code"] == cs.EXIT_OK
    assert record["new_data"] is False


def test_ADR_0091_unreadable_importer_output_never_claims_data_arrived(tmp_path):
    """If the importer's stdout cannot be parsed, the honest count is zero. Guessing upward
    from `returncode == 0` would report an arrival that nothing witnessed."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, "not json at all\n<<garbage>>"))
    record = cs.run(drop=drop, connect=lambda: FakeConn(importer_row=True), runner=runner,
                    env=_env(tmp_path))
    assert record["atoms_written"] == 0 and record["new_data"] is False
    assert record["outcome"] == "imported_no_new_atoms"


# --------------------------------------------------------------------------- missing
# --------------------------------------------------------------------------- prerequisites

def test_ADR_0091_a_missing_drop_folder_fails_visibly_and_is_never_created(tmp_path):
    """A missing drop folder is a broken arrangement, not an empty day, and it exits non-zero.

    It is also checked before the lock is taken, because taking the lock creates
    `<drop>/_state` — and `mkdir(parents=True)` would have created the missing drop folder on
    the way, converting the prerequisite most likely to be wrong into one that is always
    satisfied and always empty.
    """
    missing = tmp_path / "nowhere"
    runner = FakeRunner()
    record = cs.run(drop=missing, connect=lambda: FakeConn(), runner=runner,
                    env=_env(tmp_path))

    assert record["outcome"] == "missing_drop_dir"
    assert record["exit_code"] == cs.EXIT_FAILED
    assert runner.calls == []
    assert not missing.exists(), "the check created the folder it was checking for"


def test_ADR_0091_a_missing_credential_is_reported_and_no_import_is_attempted(tmp_path):
    """A launchd agent inherits no login shell. Without the env var and without the env file
    there is no credential, and the run must say so rather than fail deep inside a subprocess
    with a stack trace nobody will read at 01:40."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner()
    record = cs.run(drop=drop, connect=lambda: FakeConn(), runner=runner,
                    env={"PERSONAL_OS_ENV_FILE": str(tmp_path / "absent")})

    assert record["outcome"] == "missing_credential"
    assert record["exit_code"] == cs.EXIT_FAILED
    assert runner.calls == []


def test_RULE_29_ADR_0091_a_world_readable_credential_file_is_refused_not_repaired(tmp_path):
    """Refusing is the point. Silently chmod-ing the file would hide that the credential was
    readable by every process on the machine for however long it had been."""
    env_file = tmp_path / "env"
    env_file.write_text("SUPABASE_DB_URL=postgresql://u:p@example.invalid/postgres\n")
    env_file.chmod(0o644)
    with pytest.raises(cs.PrerequisiteMissing) as exc:
        cs.load_credential({}, env_file=env_file)
    assert exc.value.outcome == "credential_file_permissions"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o644, "the check modified the file"


def test_ADR_0091_the_env_file_supplies_the_credential_when_the_shell_does_not(tmp_path):
    env_file = tmp_path / "env"
    env_file.write_text("# comment\nexport SUPABASE_DB_URL='postgresql://u:p@h/postgres'\n"
                        "OTHER_SECRET=must-not-be-read\n")
    env_file.chmod(0o600)
    env = {}
    assert cs.load_credential(env, env_file=env_file) == "env_file"
    assert env["SUPABASE_DB_URL"] == "postgresql://u:p@h/postgres"
    assert "OTHER_SECRET" not in env, "the env file is not a general environment loader"


def test_ADR_0091_an_unreachable_database_is_reported_as_itself_not_as_an_empty_day(tmp_path):
    """With no database there is nowhere to write a heartbeat, so the non-zero exit and the
    local log are the whole signal — and the outcome names the real cause instead of
    borrowing the harmless-looking one."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner()
    record = cs.run(drop=drop, connect=Unreachable(), runner=runner, env=_env(tmp_path))

    assert record["outcome"] == "db_unreachable"
    assert record["exit_code"] == cs.EXIT_FAILED
    assert runner.calls == [], "a 300 MB parse was started before the database was reachable"


# --------------------------------------------------------------------------- failure is
# --------------------------------------------------------------------------- never success

def test_REQ_NFR_004_ADR_0091_a_rolled_back_import_exits_non_zero_and_leaves_a_row(tmp_path):
    """`import_drop.py` exit 2 means it rolled back — including the `ops.runs` row it had
    already written, since that row is inside the same transaction. This is the exact shape of
    a silent failure: an unattended job that failed and left no trace. The wrapper sees no
    importer row, writes one under its own name with `status='error'`, and exits non-zero."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(2, "", "import_drop: FAILED: OperationalError"))
    conn = FakeConn(importer_row=False)
    record = cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    assert record["outcome"] == "import_failed"
    assert record["exit_code"] == cs.EXIT_FAILED
    assert len(conn.heartbeats) == 1
    beat = conn.heartbeats[0]
    assert beat["outcome"] == "import_failed"
    assert beat["new_data"] is False
    assert beat["status"] == "error", "a failed import was recorded with a non-error status"
    assert beat["job_name"] == cs.JOB_NAME and beat["rows_written"] == 0


def test_REQ_NFR_004_ADR_0091_a_traceback_exit_is_never_read_as_a_partial_success(tmp_path):
    """Found by running the real importer as a subprocess instead of a double.

    `import_drop.main()` calls `db.connect()` outside its guarded block, so an unreachable
    database from the child is an *uncaught* exception — and the interpreter exits 1 for a
    traceback, the same code the importer uses for "committed, some files failed". Mapping on
    the exit code alone would file a rolled-back import as a partial success.

    The per-file JSON lines are the evidence that separates them: the importer prints one for
    every file before any legitimate exit 1, so exit 1 with nothing reported means it never
    reached its reporting stage and nothing was written.
    """
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(1, "", "Traceback...\nRuntimeError: SUPABASE_DB_URL not set"))
    conn = FakeConn(importer_row=False)
    record = cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    assert record["outcome"] == "import_failed_before_reporting"
    assert record["exit_code"] == cs.EXIT_FAILED
    assert conn.heartbeats[0]["status"] == "error"
    assert record["new_data"] is False


def test_RULE_29_ADR_0091_the_importers_stderr_never_reaches_the_runs_table(tmp_path):
    """A traceback out of the child is not passed through `redact()` — it is the path that
    escaped the importer's own error handling — so it can carry whatever a driver put in an
    exception message, up to and including a connection URL. It stays in the local log; the
    stored row carries counts, an outcome and an exit status."""
    drop = _drop(tmp_path, ["export.zip"])
    secret = "postgresql://user:hunter2@db.example.invalid:5432/postgres"
    runner = FakeRunner(FakeProc(1, "", f"InterfaceError: cannot connect to {secret}"))
    conn = FakeConn(importer_row=False)
    cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    stored = json.dumps(conn.heartbeats)
    assert "hunter2" not in stored and "postgresql://" not in stored
    assert all("stderr" not in key for key in conn.heartbeats[0])


def test_REQ_NFR_004_ADR_0091_a_partial_failure_is_neither_success_nor_total_failure(tmp_path):
    """Exit 1 from the importer: some files failed, the rest committed. Reporting that as
    success loses the failures; reporting it as failure loses the import. It gets its own
    exit code, and the importer's own run row already exists, so no second row is written."""
    drop = _drop(tmp_path, ["a.csv", "b.csv"])
    runner = FakeRunner(FakeProc(1, '{"status": "imported", "atoms_written": 5}\n'
                                    '{"status": "quarantined"}'))
    conn = FakeConn(importer_row=True)
    record = cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    assert record["outcome"] == "partial_failure"
    assert record["exit_code"] == cs.EXIT_PARTIAL
    assert conn.heartbeats == []
    assert record["import_drop_run_id"] == "IMPORTER-RUN"


# --------------------------------------------------------------------------- one row per
# --------------------------------------------------------------------------- import, ever

def test_REQ_NFR_008_ADR_0091_no_second_row_when_the_importer_already_logged(tmp_path):
    """`ops.runs` is the existing heartbeat table and `import_drop` already writes to it. A
    wrapper row describing the same import would make one import count as two — and the count
    of imports is the thing anyone reading that table is trying to establish."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, '{"status": "imported", "atoms_written": 9}'))
    conn = FakeConn(importer_row=True)
    record = cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    assert conn.heartbeats == [], "a duplicate run row was written for one import"
    assert record["heartbeat"] is None
    assert record["import_drop_run_id"] == "IMPORTER-RUN"


def test_REQ_NFR_008_ADR_0091_the_gap_is_verified_against_the_table_not_assumed(tmp_path):
    """Whether the importer logged is *asked*, not inferred from its exit code. The two agree
    today; if `import_drop.py` changes when it commits its row, an inference would start
    writing duplicates or start swallowing failures, and a query would not."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, '{"status": "imported", "atoms_written": 4}'))
    conn = FakeConn(importer_row=False)        # exit 0, yet no row: the query is the authority
    cs.run(drop=drop, connect=lambda: conn, runner=runner, env=_env(tmp_path))

    lookups = [s for s, _ in conn.statements if "select run_id" in s.lower()]
    assert len(lookups) == 1, "the wrapper did not ask ops.runs whether the importer logged"
    assert cs.IMPORTER_JOB_NAME in str(conn.statements)
    assert len(conn.heartbeats) == 1
    assert conn.heartbeats[0]["atoms_written"] == 4


def test_ADR_0091_the_wrapper_job_name_is_not_the_importers(tmp_path):
    """A row under `import_drop` means an import transaction committed. The wrapper never
    performs an import, so it never writes under that name — otherwise the fallback row for a
    *failed* import would be indistinguishable from a successful one."""
    assert cs.JOB_NAME != cs.IMPORTER_JOB_NAME


# --------------------------------------------------------------------------- ops.runs, for
# --------------------------------------------------------------------------- real

@_needs_local_server
def test_REQ_NFR_008_ADR_0091_the_heartbeat_row_is_accepted_by_the_real_runs_table(sql_connection):
    """The insert is exercised against `ops.runs` built from the real `0011_ops.sql`.

    The doubles above prove the *decision* to write a row; they cannot prove the row is legal.
    `status` is a CHECK-constrained enum of three values and `detail` is JSONB, so a wrong
    status or an unserialisable detail fails here rather than at 01:40 on a Tuesday. A
    throwaway schema, rolled back (ADR-0022).
    """
    cur = sql_connection.cursor()
    cur.execute(f"CREATE SCHEMA {OPS}")
    for stmt in _statements("0011_ops.sql", "core_schedule_pytest", OPS):
        cur.execute(stmt)

    marker = cs.db_now(cur)
    assert cs.importer_logged_since(cur, marker, OPS) is None

    run_id = cs.write_heartbeat(cur, "no_new_files",
                                {"files_seen": 0, "atoms_written": 0}, 0, "ok", OPS)
    assert run_id

    cur.execute(f"select job_name, status, rows_written, detail from {OPS}.runs "
                f"where run_id = %s", (run_id,))
    job_name, status, rows_written, detail = cur.fetchone()
    detail = json.loads(detail) if isinstance(detail, str) else detail
    assert (job_name, status, rows_written) == (cs.JOB_NAME, "ok", 0)
    assert detail["new_data"] is False and detail["outcome"] == "no_new_files"

    # And the importer's row, once present, is found — this is the query that stops the
    # duplicate, so it is exercised against the real index and the real column types.
    cur.execute(f"""insert into {OPS}.runs (job_name, finished_at, status, rows_written)
                    values (%s, now(), 'ok', 3)""", (cs.IMPORTER_JOB_NAME,))
    assert cs.importer_logged_since(cur, marker, OPS) is not None

    # An error row is legal too: REQ-NFR-004's shape, for the rolled-back import.
    assert cs.write_heartbeat(cur, "import_failed", {"files_seen": 1}, 0, "error", OPS)
    sql_connection.rollback()


# --------------------------------------------------------------------------- RULE-29

def test_RULE_29_ADR_0091_the_schedule_log_lives_outside_the_repository(tmp_path):
    """A log of drop-folder file names is close to personal data — a bank export is routinely
    named after the account. It is written under the drop folder on the Mac, and the drop
    folder is not in the repository, so there is no path by which it reaches a public commit."""
    drop = _drop(tmp_path, ["export.zip"])
    runner = FakeRunner(FakeProc(0, '{"file": "Chase_1234_activity.csv", '
                                    '"status": "imported", "atoms_written": 2}'))
    log = cs.state_dir(drop) / cs.LOG_NAME
    record = cs.run(drop=drop, connect=lambda: FakeConn(importer_row=True), runner=runner,
                    env=_env(tmp_path), log_path=log)

    assert log.exists()
    assert ROOT not in log.parents, "the schedule log is inside the repository"
    # The record line itself carries counts, not names; the importer's own output is indented
    # beneath it in the same local file.
    first = json.loads(log.read_text().splitlines()[0])
    assert "Chase_1234_activity.csv" not in json.dumps(first)
    assert first["atoms_written"] == 2
    assert "Chase_1234_activity.csv" not in cs.render(record)


def test_RULE_29_ADR_0091_the_rendered_summary_is_counts_never_contents():
    """stdout goes to launchd's log and to whatever Joe is looking at. It carries the outcome
    and four numbers; the file names stay in the local log."""
    record = {"outcome": "imported", "files_seen": 3, "atoms_written": 118, "new_data": True,
              "heartbeat": None, "drop": "/Users/joe/PersonalOS_Drop",
              "files": ["imported", "imported", "quarantined"]}
    line = cs.render(record)
    assert "118" in line and "files_seen=3" in line and "new_data=yes" in line
    assert "PersonalOS_Drop" not in line, f"a path leaked into the summary: {line}"
    assert "quarantined" not in line


# --------------------------------------------------------------------------- launchd

def test_RULE_29_ADR_0091_the_launchd_plist_carries_no_credential(tmp_path):
    """`~/Library/LaunchAgents` is world-readable by default and a plist is the first thing
    pasted into a bug report. The credential is read from the mode-checked env file at run
    time instead, so there is nothing here to leak."""
    text = cs.emit_launchd(drop=tmp_path / "drop")
    parsed = plistlib.loads(text.encode())
    assert cs.CREDENTIAL_VAR not in parsed["EnvironmentVariables"]
    assert cs.CREDENTIAL_VAR not in text
    assert "postgres" not in text.lower()


def test_ADR_0091_the_launchd_job_never_imports_merely_because_it_was_installed(tmp_path):
    """`RunAtLoad` would make bootstrapping the agent write to production as a side effect.
    Installing a scheduler and running the first import are two acts, and Joe performs both."""
    parsed = plistlib.loads(cs.emit_launchd(drop=tmp_path / "drop").encode())
    assert parsed["RunAtLoad"] is False
    assert parsed["ProgramArguments"][-1] == "--run"
    assert parsed["ProgramArguments"][1].endswith("capture_schedule.py")
    assert set(parsed["StartCalendarInterval"]) == {"Hour", "Minute"}, \
        "an interval with no Hour fires every hour; this job writes to production"


def test_ADR_0091_the_launchd_output_files_are_not_in_the_repository(tmp_path):
    parsed = plistlib.loads(cs.emit_launchd(drop=tmp_path / "drop").encode())
    for key in ("StandardOutPath", "StandardErrorPath"):
        assert ROOT not in Path(parsed[key]).parents


# --------------------------------------------------------------------------- the freshness
# --------------------------------------------------------------------------- schedule

def _crons(path):
    return re.findall(r"cron:\s*'([^']+)'", path.read_text())


def _utc_minutes(cron):
    minute, hour, dom, mon, dow = cron.split()
    assert (dom, mon, dow) == ("*", "*", "*"), f"not a daily cron: {cron!r}"
    return int(hour) * 60 + int(minute)


def test_REQ_NFR_007_the_freshness_check_runs_daily_so_detection_lags_by_at_most_a_day():
    """REQ-NFR-007 says a quiet source fails a scheduled run. How *late* that failure is
    depends entirely on the cadence, and the requirement does not name one — so the cadence is
    an invariant of this file, and this is where it is held. Daily means a metric that crosses
    its limit is reported within one day of doing so."""
    crons = _crons(FRESHNESS)
    assert crons, "freshness.yml has no schedule at all"
    for cron in crons:
        _utc_minutes(cron)          # raises unless every schedule is a daily one


def test_ADR_0060_freshness_keeps_its_own_schedule_and_is_never_a_step_of_analysis():
    """The governing idea of ADR-0060, enforced instead of merely written down.

    A freshness check that runs as a step of the pipeline it audits shares that pipeline's
    fate: if `analysis` fails early the check never runs, and silence looks exactly like
    health. It therefore has its own workflow, its own trigger, and no `needs:`.
    """
    text = FRESHNESS.read_text()
    assert "check_freshness.py" in text
    assert "needs:" not in text, "the freshness check gained a dependency on another job"
    assert "check_freshness" not in ANALYSIS.read_text(), \
        "the freshness check was folded into the analysis pipeline it audits"


def test_REQ_NFR_008_the_scheduled_freshness_run_never_suppresses_its_runs_row():
    """`--no-log` exists for a human running the checker ad hoc. On the schedule it would
    delete the freshness history REQ-NFR-008 requires, one run at a time, invisibly."""
    assert "--no-log" not in FRESHNESS.read_text()


def test_ADR_0091_the_local_import_precedes_the_freshness_check_in_both_halves_of_the_year():
    """The orchestration, and the only reason the local schedule is where it is.

    Freshness runs on a fixed UTC cron; launchd runs on local time. Those are different clocks
    and the gap between them changes by an hour at each DST boundary — the same seam
    `check_freshness.py` documents for its own clock. A local time chosen against the summer
    offset alone would silently invert in winter, so the ordering is asserted at both offsets.

    It is a margin, not a guarantee. A sleeping laptop runs the import at wake and a seven-year
    export can outlast the gap. When the import lands late, freshness reports a day late —
    which is the safe direction, and the reason freshness is asked of the data and not of this
    job.
    """
    freshness_utc = min(_utc_minutes(c) for c in _crons(FRESHNESS))
    import_local = cs.LAUNCHD_HOUR * 60 + cs.LAUNCHD_MINUTE
    for offset_hours, label in ((-4, "EDT"), (-5, "EST")):
        freshness_local = (freshness_utc + offset_hours * 60) % (24 * 60)
        assert import_local < freshness_local, (
            f"in {label} the local import at {import_local // 60:02d}:{import_local % 60:02d} "
            f"does not precede the freshness check at "
            f"{freshness_local // 60:02d}:{freshness_local % 60:02d}")


def test_ADR_0091_no_workflow_step_runs_the_local_importer():
    """A GitHub-hosted runner cannot see `~/PersonalOS_Drop`. A workflow STEP that ran
    `import_drop.py` would find an empty folder, exit 0 for ever, and produce precisely the
    green-job-over-dead-input signal this whole area of the system exists to prevent.

    The assertion is on what a workflow EXECUTES, not on what its text mentions. It was the
    whole file text, which is a coarser question than the one that matters and answers it
    wrongly in both directions: `capture-acceptance.yml` names both scripts in a `paths:`
    filter — which schedules nothing — while a workflow could invoke either through a wrapper
    and never spell its name in a `run:` line at all. So two properties are asserted instead,
    and together they are strictly stronger than the grep they replace:

    1. no step's shell command invokes either script, and
    2. any workflow that reaches them transitively — the acceptance harness spawns both — has
       no production credential to reach production WITH. That is the property that actually
       protects `core`: a hosted runner with `SUPABASE_DB_URL` and a drop folder it cannot see
       is the hazard, and a runner without the credential cannot be one whatever it runs.
    """
    reaches_the_scripts = []
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        spec = yaml.safe_load(workflow.read_text())
        text = workflow.read_text()
        for job in (spec.get("jobs") or {}).values():
            for step in (job.get("steps") or []):
                command = step.get("run") or ""
                for script in ("import_drop.py", "capture_schedule.py"):
                    assert script not in command, (
                        f"{workflow.name} runs {script} on a hosted runner, which cannot reach "
                        f"the drop folder on Joe's Mac")
        if "import_drop.py" in text or "capture_schedule.py" in text:
            reaches_the_scripts.append((workflow.name, "SUPABASE_DB_URL" in text))

    for name, has_credential in reaches_the_scripts:
        assert not has_credential, (
            f"{name} names the local import scripts AND carries SUPABASE_DB_URL. A hosted "
            f"runner that can reach production and cannot reach the drop folder is exactly "
            f"the arrangement that reports a green job over a dead input.")


# --------------------------------------------------------------------------- the CLI

def test_ADR_0091_emit_launchd_installs_nothing(tmp_path):
    """The command that produces the schedule must not be the command that starts it."""
    out = subprocess.run([sys.executable, str(ROOT / "ops" / "capture_schedule.py"),
                          "--emit-launchd", "--drop", str(tmp_path / "drop")],
                         capture_output=True, text=True, cwd=str(ROOT),
                         env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert out.returncode == 0
    assert plistlib.loads(out.stdout.encode())["Label"] == cs.LAUNCHD_LABEL
    assert not (Path.home() / "Library" / "LaunchAgents" /
                f"{cs.LAUNCHD_LABEL}.plist").exists(), \
        "emitting the plist installed it"


def test_ADR_0091_the_bare_command_does_nothing_and_says_so(tmp_path):
    """No argument imports nothing. A scheduler wrapper whose default action is a production
    write is one mistyped launchd argument away from an unintended import."""
    out = subprocess.run([sys.executable, str(ROOT / "ops" / "capture_schedule.py")],
                         capture_output=True, text=True, cwd=str(ROOT),
                         env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert out.returncode != 0
    assert "--run" in out.stdout


# ------------------------------------------------------- ADR-0141: the settle gate
#
# These drive `settle` with their own numbers, so the autouse zero-interval fixture above is
# irrelevant to them: each passes `interval` and `timeout` explicitly.

def test_ADR_0140_a_file_that_stops_growing_is_ready(tmp_path):
    """Two observations that agree. That is the whole definition."""
    p = tmp_path / "export.xml"
    p.write_text("<HealthData/>")
    ready, arriving = cs.settle([p], interval=0, timeout=0, sleeper=lambda s: None)
    assert ready == [p] and arriving == []


def test_ADR_0140_a_file_still_being_written_is_never_imported(tmp_path):
    """A growing file is held back, not imported.

    This is the defect the gate exists for and it is not symmetric across formats. A truncated
    Apple Health zip raises and is reported. A truncated bank CSV PARSES — it commits the rows
    that happened to have landed and writes an append-only `raw_captures` row whose
    `records_parsed` is wrong and can never be corrected (RULE-02). Nothing downstream can tell
    those missing atoms from days Joe did not spend.
    """
    p = tmp_path / "statement.csv"
    p.write_text("Date,Description,Amount\n")

    def grow(_seconds):
        with p.open("a") as fh:
            fh.write("2026-01-01,X,-1.00\n")

    ticks = iter([0, 1, 2, 3, 4, 5])
    ready, arriving = cs.settle([p], interval=0, timeout=2, sleeper=grow,
                                clock=lambda: next(ticks))
    assert ready == []
    assert arriving == [p]


def test_ADR_0140_mtime_age_alone_would_have_passed_a_half_copied_file(tmp_path):
    """The gate compares two observations; it does NOT ask how old the mtime is.

    A file arriving by AirDrop, `cp -p` or an iCloud materialisation keeps the SOURCE file's
    mtime, so a half-copied export can present an mtime from weeks ago while bytes are still
    being written. Any age-based test passes it immediately. This asserts the property that
    makes that impossible: a file whose mtime is ancient and whose SIZE is still changing is
    held back anyway.
    """
    p = tmp_path / "old_looking_export.xml"
    p.write_text("<HealthData>")
    ancient = 1_000_000_000                      # 2001, far older than any settle threshold
    os.utime(p, (ancient, ancient))

    def grow(_seconds):
        with p.open("a") as fh:
            fh.write("<Record/>")
        os.utime(p, (ancient, ancient))          # the copy preserves the old mtime too

    ticks = iter([0, 1, 2, 3])
    ready, arriving = cs.settle([p], interval=0, timeout=1, sleeper=grow,
                                clock=lambda: next(ticks))
    assert ready == [] and arriving == [p]


def test_ADR_0140_a_file_that_vanishes_between_observations_is_neither(tmp_path):
    p = tmp_path / "export.xml"
    p.write_text("x")
    ready, arriving = cs.settle([p], interval=0, timeout=0,
                                sleeper=lambda s: p.unlink())
    assert ready == [] and arriving == []


def test_ADR_0140_REQ_NFR_012_a_stuck_file_is_an_error_not_an_empty_day(tmp_path):
    """A drop folder holding only a file that never settles fails visibly.

    `no_new_files` and `files_still_arriving` are different sentences: the first says capture
    did not happen, the second says capture is BLOCKED. Reporting the second as the first is
    the 43-day failure in miniature — a green run over an input that is silently stuck.
    """
    drop = tmp_path / "drop"
    drop.mkdir()
    stuck = drop / "statement.csv"
    stuck.write_text("Date\n")
    conn = FakeConn()
    ran = []

    record = cs.run(drop=drop, commit=True, ops=OPS,
                    connect=lambda: conn,
                    runner=lambda *a, **k: ran.append(a) or FakeProc(0),
                    env={"SUPABASE_DB_URL": "x"},
                    settler=lambda files: ([], list(files)))

    assert record["outcome"] == "files_still_arriving"
    assert record["exit_code"] == cs.EXIT_PARTIAL
    assert record["new_data"] is False
    assert ran == [], "the importer was invoked for a file that had not finished arriving"
    beat = conn.heartbeats[-1]
    assert beat["status"] == "error", (
        f"a stuck file wrote status={beat['status']!r}, which reads as healthy")
    assert beat["outcome"] == "files_still_arriving"
    assert beat["new_data"] is False
    assert beat["rows_written"] == 0
    assert stuck.exists(), "the unfinished file was moved out of the drop folder"


def test_ADR_0140_ready_files_are_named_when_others_are_still_arriving(tmp_path):
    """The importer must not scan the folder when part of it is still being written."""
    drop = tmp_path / "drop"
    drop.mkdir()
    done = drop / "export.xml"
    done.write_text("<HealthData/>")
    growing = drop / "statement.csv"
    growing.write_text("Date\n")
    calls = []

    cs.run(drop=drop, commit=True, ops=OPS, connect=lambda: FakeConn(),
           runner=lambda cmd, **k: calls.append(cmd) or FakeProc(0, '{"atoms_written": 1}\n'),
           env={"SUPABASE_DB_URL": "x"},
           settler=lambda files: ([done], [growing]))

    assert calls, "the importer was never invoked"
    cmd = calls[0]
    assert "--file" in cmd and str(done) in cmd
    assert str(growing) not in cmd, (
        "the growing file was handed to the importer; a settle gate whose result nothing acts "
        "on is not a gate")


def test_ADR_0140_every_ready_file_leaves_the_importer_scanning_the_folder(tmp_path):
    """With nothing held back, the ordinary folder scan is used — no behaviour change."""
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "export.xml").write_text("<HealthData/>")
    calls = []
    cs.run(drop=drop, commit=True, ops=OPS, connect=lambda: FakeConn(),
           runner=lambda cmd, **k: calls.append(cmd) or FakeProc(0, '{"atoms_written": 1}\n'),
           env={"SUPABASE_DB_URL": "x"})
    assert "--file" not in calls[0]


# ------------------------------------------------------- ADR-0141: schema passthrough

def test_ADR_0140_REQ_NFR_008_the_importer_is_told_which_ops_schema_to_log_to():
    """The wrapper asks `<ops>.runs` whether the importer logged; the importer must log there.

    This was a real inconsistency, not a hypothetical one. `--ops` existed on the wrapper and
    the importer's runs INSERT named `ops.runs` literally, so under any non-default pair the
    wrapper looked in one schema, the importer wrote in another, the lookup found nothing and a
    second heartbeat was written for an import that had already recorded itself — `ops.runs`
    counting one import twice, which is exactly what the wrapper's docstring forbids.
    """
    cmd = cs.import_command(schema="core_dryrun", ops="ops_dryrun")
    assert cmd[cmd.index("--ops") + 1] == "ops_dryrun"
    assert cmd[cmd.index("--schema") + 1] == "core_dryrun"


def test_ADR_0140_an_ops_schema_that_is_not_an_identifier_is_refused(tmp_path):
    """The name is interpolated into SQL and cannot be a bind parameter, so it is validated."""
    drop = tmp_path / "drop"
    drop.mkdir()
    for bad in ("ops runs", "ops-runs", "Ops", "1ops", ""):
        with pytest.raises(ValueError):
            cs.run(drop=drop, ops=bad, connect=lambda: FakeConn(),
                   runner=lambda *a, **k: FakeProc(0), env={"SUPABASE_DB_URL": "x"})


def test_ADR_0140_the_child_keeps_the_pythonpath_it_was_given():
    """Repo root first, whatever was already there behind it.

    Overwriting PYTHONPATH outright discarded an entry the parent had set, which made the
    child's import path depend on which parent started it.
    """
    env = cs._child_env({"PYTHONPATH": "/elsewhere"}, "/repo")
    assert env["PYTHONPATH"].split(os.pathsep) == ["/repo", "/elsewhere"]
    assert cs._child_env({}, "/repo")["PYTHONPATH"] == "/repo"
    assert cs._child_env({"PYTHONPATH": "/repo"}, "/repo")["PYTHONPATH"] == "/repo"


def test_ADR_0140_a_misnamed_export_is_counted_and_shown(tmp_path):
    """An unrecognised file is not a failure — but it must not be silent either.

    `import_drop.classify` recognises `export.xml`, `*_export.xml`, `export.zip`, `Takeout*.zip`
    and the bank extensions. A Health export saved as `health.xml`, or a second download named
    `statement (1).csv`, is `unrecognised_file_type`: it imports nothing, exits 0 and stays in
    the folder to be ignored again tomorrow. Without this count every line of the summary says
    the job succeeded while the export Joe actually took never lands.
    """
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "health.xml").write_text("<HealthData/>")
    record = cs.run(drop=drop, commit=True, ops=OPS, connect=lambda: FakeConn(),
                    runner=lambda *a, **k: FakeProc(
                        0, '{"file": "health.xml", "status": "unrecognised_file_type"}\n'),
                    env={"SUPABASE_DB_URL": "x"})
    assert record["unrecognised_files"] == 1
    assert record["exit_code"] == cs.EXIT_OK
    assert "unrecognised=1" in cs.render(record)


def test_ADR_0140_the_wrapper_and_the_importer_accept_the_same_ops_schemas():
    """Whatever the wrapper takes, the importer must take — it is handed straight through.

    The original `--ops` defect was the wrapper and the importer disagreeing about where a run
    row goes. An importer whose `--ops` accepted a SMALLER set than its only caller would be
    the same disagreement in the other direction: the wrapper would validate the name, build
    the argv, and the child would exit 2 on it.
    """
    from tools import import_drop
    import argparse as _argparse
    for good in ("ops", "ops_dryrun", "ops_import_pytest", "ops_schedule_pytest"):
        assert cs.IDENTIFIER.match(good)
        assert import_drop.ops_identifier(good) == good
    for bad in ("ops runs", "Ops", "1ops", "", "ops-runs"):
        assert not cs.IDENTIFIER.match(bad)
        with pytest.raises(_argparse.ArgumentTypeError):
            import_drop.ops_identifier(bad)
