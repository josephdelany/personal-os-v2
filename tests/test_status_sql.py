"""REQ-NFR-003/004: real status SQL, actual ops DDL, rolled-back test rows.

Closes the cursor-double query gap called out by the September 8 review.
"""
import os

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements
from tools.status import report_liveness


class OpsTwinCursor:
    """Only rebind the schema; execute the production query unchanged otherwise."""
    def __init__(self, cur):
        self.cur = cur

    def execute(self, query):
        self.cur.execute(query.replace("ops.runs", "ops_pytest.runs"))

    def fetchall(self):
        return self.cur.fetchall()


@pytest.fixture
def cur(sql_connection):
    # RULE-01. This fixture runs CREATE SCHEMA and migration DDL on whatever connection it is
    # given. Every other sql_connection fixture guards on the disposable socket; this one did
    # not, so in CI's `pytest` job — where SUPABASE_DB_URL IS set — it executed DDL against
    # PRODUCTION and relied entirely on the rollback to undo it. The workflow's comment claimed
    # that job skipped these tests. It did not; nothing made it true. Found by the evidence
    # audit, not by a failure, because a rolled-back CREATE SCHEMA leaves no trace to notice.
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds ops DDL; disposable local server only (tools/test_local_sql.py)")
    cur = sql_connection.cursor()
    cur.execute("CREATE SCHEMA ops_pytest")
    sql = (ROOT / "migrations/0011_ops.sql").read_text().replace("__OPS__", "ops_pytest")
    for statement in split_statements(sql):
        cur.execute(statement)
    return cur


def test_REQ_NFR_004_sql_missing_jobs_are_not_lost_by_join(cur, capsys):
    assert report_liveness(OpsTwinCursor(cur)) is False
    output = capsys.readouterr().out
    assert output.count("[MISSING]") == 3
    for job in ("keepalive_supabase", "keepalive_github", "extract_checkins"):
        assert job in output


def test_REQ_NFR_004_sql_new_failure_wins_over_old_success(cur, capsys):
    cur.execute("""INSERT INTO ops_pytest.runs(job_name, started_at, finished_at, status)
        VALUES ('keepalive_supabase', now() - interval '2 hours', now() - interval '1 hour', 'ok'),
               ('keepalive_supabase', now() - interval '2 minutes', now() - interval '1 minute', 'error')""")
    assert report_liveness(OpsTwinCursor(cur)) is False
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if "keepalive_supabase" in line)
    assert "[NOT OK: error]" in line
    assert "never" not in line


def test_REQ_NFR_004_sql_future_run_is_not_a_successful_finish(cur, capsys):
    cur.execute("""INSERT INTO ops_pytest.runs(job_name, started_at, finished_at, status)
        VALUES ('keepalive_supabase', now(), now() + interval '1 day', 'ok')""")
    assert report_liveness(OpsTwinCursor(cur)) is False
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if "keepalive_supabase" in line)
    assert "last successful finish: never" in line
    assert "[INVALID: run timestamps]" in line


def test_REQ_NFR_003_sql_success_after_transaction_start_is_healthy(cur, capsys):
    # clock_timestamp is later than transaction now(); this reproduces the
    # original timing defect without threads or production writes.
    cur.execute("""INSERT INTO ops_pytest.runs(job_name, started_at, finished_at, status)
        SELECT job, now(), clock_timestamp(), 'ok'
          FROM unnest(ARRAY['keepalive_supabase','keepalive_github','extract_checkins']) AS job""")
    assert report_liveness(OpsTwinCursor(cur)) is True
    assert capsys.readouterr().out.count("[ok]") == 3
