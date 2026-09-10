"""Execute focused production SQL in rolled-back schemas (ADR-0022/0082).

An explicit PERSONAL_OS_TEST_SOCKET selects a disposable local server. Otherwise
use the project's normal verified-TLS connection. Application callers never use
this helper. No data is committed and no persistent app table is touched.
"""
import getpass
import os
from pathlib import Path

import pg8000.dbapi
import pytest

from lib import db
from tools.run_migration import split_statements


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sql_connection():
    socket = os.environ.get("PERSONAL_OS_TEST_SOCKET")
    if socket:
        path = Path(socket)
        if not path.is_absolute() or not path.name.startswith(".s.PGSQL."):
            raise ValueError("PERSONAL_OS_TEST_SOCKET must be an absolute PostgreSQL Unix socket path")
        conn = pg8000.dbapi.connect(
            user=getpass.getuser(), database="postgres", unix_sock=str(path), timeout=10,
        )
    elif not os.environ.get("SUPABASE_DB_URL"):
        # NO DATABASE IS REACHABLE AT ALL. That is a skip, and it has to LOOK like one.
        #
        # Previously this fell through to db.connect(), which raised, and pytest reported a
        # fixture ERROR — 313 of them on a developer machine with neither the disposable socket
        # nor the live URL. An error is indistinguishable from a broken test, which is exactly
        # what made the evidence audit's "38 errors against production" so hard to read: real
        # timeouts and merely-unrunnable tests looked identical in the same column.
        #
        # This is deliberately NOT a dependency skip (tests/conftest.py) — no package installs a
        # database. Both CI jobs supply one: `local-sql` sets PERSONAL_OS_TEST_SOCKET and
        # `pytest` sets SUPABASE_DB_URL, so neither can reach this line.
        pytest.skip("no database available: set PERSONAL_OS_TEST_SOCKET (disposable server, "
                    "via tools/test_local_sql.py) or SUPABASE_DB_URL")
    else:
        conn = db.connect()
    try:
        if socket:
            cur = conn.cursor()
            cur.execute("SHOW server_version_num")
            if int(cur.fetchone()[0]) // 10000 != 17:
                raise RuntimeError("Local SQL verification requires PostgreSQL major version 17")
        yield conn
    finally:
        conn.rollback()
        conn.close()


def migration_function(cur, filename, signature, schema="api_pytest"):
    """Run the actual function body, with its API schema rewritten to a twin."""
    statements = split_statements((ROOT / "migrations" / filename).read_text())
    matches = [s for s in statements if f"CREATE OR REPLACE FUNCTION {signature}" in s]
    assert len(matches) == 1, f"Expected exactly one production function: {signature}"
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    cur.execute(matches[0].replace("public.", f"{schema}."))
