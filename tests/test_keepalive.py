"""Keepalive mechanism tests (REQ-NFR-001..004, ADR-0024).

What these prove and what they cannot:
  - REQ-NFR-001/002 are proven as SCHEDULE MECHANISM by parsing the workflow file:
    the Supabase cron period is <= 3 days, and the stale-commit check period PLUS the
    50-day threshold is < 60 (the real invariant that keeps the schedule alive — a
    monthly check would allow 81 days and disable the workflow). They CANNOT prove an
    on-schedule firing — that evidence is the `trigger=schedule` rows in `ops.runs`
    (Gate 0 CLOSED, verified 2026-08-31; PROGRESS session 14 addendum). Until that
    date F-014/F-015 stayed failing; the ledger runner (tools/update_features.py,
    ADR-0011) now flips them on these named tests, with ops.runs as the on-schedule proof.
  - REQ-NFR-003 (success) and REQ-NFR-004 (failure) are proven BEHAVIOURALLY against a
    disposable ops_pytest schema inside a transaction that is ROLLED BACK (ADR-0022),
    plus a no-DB test that an unreachable database exits non-zero.

Run: python3 -m pytest tests/test_keepalive.py -v   (DB-marked tests need SUPABASE_DB_URL)
"""
import os
import re
import pathlib

import pytest

from lib import db
from tools import run_migration
from ops import keepalive

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "keepalive.yml"

CORE = "core_pytest"
OPS = "ops_pytest"
CHECK_VIOLATION = "23514"   # Postgres SQLSTATE for a CHECK constraint violation

GITHUB_DISABLE_DAYS = 60    # GitHub disables scheduled workflows after 60 days of inactivity
SUPABASE_PAUSE_DAYS = 7     # Supabase Free pauses a project after 7 days of inactivity


# ---------------------------------------------------------------------------
# REQ-NFR-001 / REQ-NFR-002 — schedule mechanism (no DB needed)
# ---------------------------------------------------------------------------

def _crons():
    return re.findall(r"cron:\s*'([^']+)'", WORKFLOW.read_text())


def _max_gap_days(cron):
    """Coarse cadence bound for the simple cron shapes this workflow uses.
    5 fields: min hour dom month dow. Daily (dom=month=dow='*') -> 1 day.
    Monthly (a fixed day-of-month, month='*') -> 31 days (worst case)."""
    m, h, dom, mon, dow = cron.split()
    if dom == "*" and mon == "*" and dow == "*":
        return 1
    if dom.isdigit() and mon == "*":
        return 31
    raise AssertionError(f"cron shape not classified by this test: {cron!r}")


def _threshold():
    m = re.search(r"KEEPALIVE_MAX_COMMIT_AGE_DAYS:\s*\"?(\d+)\"?", WORKFLOW.read_text())
    assert m, "no KEEPALIVE_MAX_COMMIT_AGE_DAYS in keepalive.yml"
    return int(m.group(1))


def test_REQ_NFR_001_supabase_keepalive_period_within_7_days():
    crons = _crons()
    assert crons, "no cron schedules found in keepalive.yml"
    assert min(_max_gap_days(c) for c in crons) <= 3, \
        f"REQ-NFR-001: must run at least every 3 days (<{SUPABASE_PAUSE_DAYS}); crons={crons}"


def test_REQ_NFR_002_stale_commit_fires_before_the_60_day_limit():
    # The invariant that actually keeps the schedule alive: the WORST-CASE staleness at
    # which a heartbeat commit fires is (check period + threshold). It must stay < 60.
    threshold = _threshold()
    check_period = max(_max_gap_days(c) for c in _crons())   # the job runs the stale check
    worst_case_staleness = check_period + threshold
    assert worst_case_staleness < GITHUB_DISABLE_DAYS, (
        f"REQ-NFR-002 UNSOUND: check every {check_period}d + {threshold}d threshold "
        f"= {worst_case_staleness}d can exceed GitHub's {GITHUB_DISABLE_DAYS}d disable limit"
    )


# ---------------------------------------------------------------------------
# REQ-NFR-003 / REQ-NFR-004 — behavioural, disposable schema, rolled back
# ---------------------------------------------------------------------------

needs_db = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — behavioural keepalive tests need the live PG engine",
)


@pytest.fixture(scope="module")
def spine():
    conn = db.connect()
    cur = conn.cursor()
    try:
        run_migration.apply(cur, CORE, OPS)   # creates ops_pytest.runs among others
        yield conn, cur
    finally:
        conn.rollback()      # disposable schema + every row vanish here (ADR-0022)
        conn.close()


@pytest.fixture()
def cur(spine):
    conn, cursor = spine
    cursor.execute("SAVEPOINT test_sp")
    yield cursor
    cursor.execute("ROLLBACK TO SAVEPOINT test_sp")


@needs_db
def test_REQ_NFR_003_run_writes_exactly_one_ops_runs_row_with_real_duration(cur):
    run_id = keepalive.perform(cur, OPS, "keepalive_supabase", "test")
    cur.execute(f"SELECT job_name, status, started_at, finished_at, rows_written "
                f"FROM {OPS}.runs WHERE job_name = 'keepalive_supabase'")
    rows = cur.fetchall()
    assert len(rows) == 1, "REQ-NFR-003: exactly one run row per keepalive execution"
    job_name, status, started_at, finished_at, rows_written = rows[0]
    assert job_name == "keepalive_supabase"
    assert status == "ok"
    assert started_at is not None and finished_at is not None
    # clock_timestamp() reads wall-clock at each statement, and the INSERT -> SELECT 1 ->
    # UPDATE round-trip to Postgres guarantees wall-clock advances between the two stamps,
    # so finished_at is strictly after started_at — a real completion time, not now()==now()
    # (reviewer M2). This is stricter than the schema's `>=` CHECK on purpose: it would
    # catch a regression back to now() (which yields equality).
    assert finished_at > started_at, "finished_at must be a real, later timestamp than started_at"
    assert rows_written == 0, "a keepalive writes no DATA rows (RULE-01)"
    assert run_id is not None


@needs_db
def test_REQ_NFR_004_reachable_failure_records_error_row(cur, monkeypatch):
    # A genuine mid-run failure ABORTS the Postgres transaction (the realistic case: a bad
    # query, a constraint hit). perform() must ROLLBACK TO SAVEPOINT to recover the aborted
    # transaction and still write a status='error' row. Exercise that path, not a Python
    # error raised before any SQL runs (reviewer MINOR 2).
    def boom(cursor, *a, **k):
        cursor.execute(f"SELECT 1 FROM {OPS}.does_not_exist_xyz")   # raises + ABORTS the txn
    monkeypatch.setattr(keepalive, "record_run", boom)
    with pytest.raises(Exception):
        keepalive.perform(cur, OPS, "keepalive_supabase", "test")
    cur.execute(f"SELECT status FROM {OPS}.runs WHERE job_name = 'keepalive_supabase'")
    rows = cur.fetchall()
    assert rows, "REQ-NFR-004: a failure must record a row, not vanish silently"
    assert all(r[0] == "error" for r in rows), "the recorded row must carry status='error'"


@needs_db
def test_REQ_NFR_004_status_check_rejects_unknown_status(cur):
    # the runs.status CHECK is the guard that keeps 'error' meaningful
    cur.execute("SAVEPOINT probe")
    with pytest.raises(Exception) as ei:
        cur.execute(f"INSERT INTO {OPS}.runs (job_name, status) VALUES ('x', 'bogus')")
    cur.execute("ROLLBACK TO SAVEPOINT probe")
    assert CHECK_VIOLATION in str(ei.value)


def test_REQ_NFR_004_unreachable_db_exits_nonzero(monkeypatch):
    # No DB needed: if the database can't be reached, the job must exit non-zero so the
    # failed CI run is the visible signal (there is no ops.runs to write to).
    def down():
        raise RuntimeError("simulated unreachable database")
    monkeypatch.setattr(keepalive.db, "connect", down)
    with pytest.raises(SystemExit) as ei:
        keepalive.main(["--job", "supabase"])
    assert ei.value.code == 1
