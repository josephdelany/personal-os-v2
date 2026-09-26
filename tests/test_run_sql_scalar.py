"""ADR-0173 activation gap: the hourly visits step must not fail before 0096 is applied."""
import json
from pathlib import Path

from tools import run_sql_scalar

ROOT = Path(__file__).resolve().parents[1]


class FakeCursor:
    def __init__(self, exists):
        self.exists, self.executed, self.row = exists, [], None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "to_regprocedure" in sql:
            self.row = (self.exists,)
        elif sql.startswith("select"):
            self.row = (7,)

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, exists):
        self.cur, self.committed = FakeCursor(exists), False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


ARGS = ["run_sql_scalar.py", "select public.new_fn()", "derive_visits",
        "--requires", "public.new_fn()", "--otherwise", "select old_fn()"]


def run(exists):
    conn = FakeConn(exists)
    code = run_sql_scalar.main(ARGS, connect=lambda: conn)
    statements = [sql for sql, _ in conn.cur.executed]
    runs = [p for sql, p in conn.cur.executed if "ops.runs" in sql]
    return code, statements, json.loads(runs[-1][2])


def test_ADR_0173_preferred_statement_runs_when_the_function_exists():
    code, statements, detail = run(True)
    assert code == 0
    assert "select public.new_fn()" in statements and "select old_fn()" not in statements
    assert detail == {"scalar": "7", "path": "preferred"}


def test_ADR_0173_fallback_runs_and_is_recorded_when_the_function_is_missing():
    code, statements, detail = run(False)
    assert code == 0
    assert "select old_fn()" in statements and "select public.new_fn()" not in statements
    assert detail["path"] == "fallback: public.new_fn() missing"


def test_ADR_0173_plain_invocation_is_unchanged():
    conn = FakeConn(True)
    assert run_sql_scalar.main(["x", "select 1", "job"], connect=lambda: conn) == 0
    assert not any("to_regprocedure" in sql for sql, _ in conn.cur.executed)


def test_ADR_0173_incomplete_bridge_arguments_refuse_before_connecting():
    def never():
        raise AssertionError("must not connect")
    assert run_sql_scalar.main(["x", "select 1", "job", "--requires", "f()"], connect=never) == 2
    assert run_sql_scalar.main(["x", "select 1", "job", "--otherwise"], connect=never) == 2


def test_ADR_0173_extract_workflow_bridges_the_visits_refresh():
    workflow = (ROOT / ".github/workflows/extract.yml").read_text()
    assert "--requires 'public.refresh_v0_visits()'" in workflow
    assert "--otherwise" in workflow
