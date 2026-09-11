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
from tests._import_fixture import SUPABASE_ROLES
from tools.run_migration import split_statements


ROOT = Path(__file__).resolve().parents[1]


def disposable_socket():
    """The disposable PostgreSQL 17 socket, or None."""
    socket = os.environ.get("PERSONAL_OS_TEST_SOCKET")
    if not socket:
        return None
    path = Path(socket)
    if not path.is_absolute() or not path.name.startswith(".s.PGSQL."):
        raise ValueError("PERSONAL_OS_TEST_SOCKET must be an absolute PostgreSQL Unix socket path")
    return path


# For modules that BUILD SCHEMA. Applying migration DDL is a disposable-server operation and
# nothing else; gating it on SUPABASE_DB_URL is what had CI running hundreds of DDL statements
# through the pooler against production, and is the origin of OQ-78's 57014 timeouts.
requires_disposable = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds schemas from migration DDL; disposable local server only "
           "(tools/test_local_sql.py)",
)


def ensure_supabase_roles(cur):
    """Create anon/authenticated/service_role if absent. Transactional; gone at rollback.

    Supabase supplies them and a bare PostgreSQL 17 cluster does not, while 31 migrations grant
    to them by name. Same pattern and same reason as tests/_import_fixture.py. Added here for
    modules that drive tools/run_migration.apply directly, which is a runtime tool and is not
    the place to teach about test roles.
    """
    for role in SUPABASE_ROLES:
        cur.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""")


def apply_legacy_prerequisites(cur):
    """Create the 34 pre-chain public.* tables the numbered migrations never create.

    "These tables predate the migration chain and no migration file creates them, so a rebuild
    from empty is impossible without them" (ADR-0088). Production has them, which is what hid
    the dependency: the chain applied there and failed on a bare cluster. Column names and
    types only -- no row is read or written.
    """
    legacy = ROOT / "migrations" / "_legacy_prerequisites.sql"
    for statement in split_statements(legacy.read_text()):
        cur.execute(statement)


def connect():
    """Connect to the disposable server. Never to production — see `requires_disposable`."""
    path = disposable_socket()
    if path is None:
        pytest.skip("no disposable server: set PERSONAL_OS_TEST_SOCKET via tools/test_local_sql.py")
    conn = pg8000.dbapi.connect(
        user=getpass.getuser(), database="postgres", unix_sock=str(path), timeout=10,
    )
    cur = conn.cursor()
    cur.execute("SHOW server_version_num")
    if int(cur.fetchone()[0]) // 10000 != 17:
        conn.close()
        raise RuntimeError("Local SQL verification requires PostgreSQL major version 17")
    return conn


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
    if disposable_socket() is None:
        # `sql_connection` hands back a PRODUCTION connection whenever SUPABASE_DB_URL is set,
        # and this helper then ran CREATE SCHEMA on it. The same shape as the test_status_sql.py
        # defect the audit found, left standing in the generic helper after that one module was
        # fixed. Structural, so forgetting a mark cannot reintroduce it.
        raise RuntimeError(
            "migration_function creates a schema and must only ever run against the disposable "
            "PostgreSQL 17 server. PERSONAL_OS_TEST_SOCKET is not set. "
            "Run these tests via tools/test_local_sql.py."
        )
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    cur.execute(matches[0].replace("public.", f"{schema}."))
