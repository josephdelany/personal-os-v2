"""Disposable-schema fixture for the location tests (B5; RULE-01 / ADR-0022).

RULE-01's one bounded exception lets a behavioural test INSERT fixture rows only into a
DISPOSABLE schema — never core, never public — inside a transaction that is rolled back.
The location migrations name their schemas literally, so this helper applies the whole
forward-only chain with every schema rewritten into a throwaway twin:

    core -> core_pytest · ops -> ops_pytest · the location store -> restricted_pytest ·
    analysis.visits_public -> analysis_pytest.visits_public

The public.* RPCs are re-created (inside the same transaction) pointing at the twins, so
a test exercises the real function bodies against tables that vanish at rollback. The
test coordinates are ocean points with at most three decimals (0.0, 0.01, …), never a
real place. This file rewrites migration TEXT; it never reads a coordinate and never
names a location table of its own (ADR-0044 lint).
"""
import getpass
import os
import re
from pathlib import Path

import pg8000.dbapi
import pytest

from tests._import_fixture import SUPABASE_ROLES
from tests._sql_fixture import connect, disposable_socket, requires_disposable  # noqa: F401
from tools import run_migration

CORE, OPS = "core_pytest", "ops_pytest"
LOC_SCHEMA = "restricted_pytest"
ANALYSIS_TWIN = "analysis_pytest"

_LOC_WORD = re.compile(r"\brestricted\b")            # the schema name, wherever it appears

# Literal schema-qualified references. The placeholders (__CORE__/__OPS__) only cover the files
# that use them: 30 numbered migrations name `core.atoms`, `analysis.panel`, `config.*` and
# friends OUTRIGHT. Those were never rewritten, so against production they resolved to the REAL
# schemas — the twins were only ever partly disposable, contrary to this module's own docstring
# and to RULE-01 ("never core, never public"). A rollback contained it; it was still production
# core being read and written. Rewriting every qualified reference is what makes "throwaway
# twin" true. `core_pytest.` cannot re-match `\bcore\.` (the next character is `_`), so running
# these after the placeholder substitution is safe and idempotent.
# core/ops/analysis are twinned because every engine and test parameterises them
# (`recommend.run(..., core=, panel_schema=)`). `config` and `auth` are NOT: migration 0034
# creates `config` and seeds it, engines default to `config_schema="config"`, and it holds
# configuration — vocabulary, catalogues, allowlists — not personal rows, so RULE-01's
# "disposable schema, never core, never public" is not in play. On a server that exists only
# for this process there is nothing to protect them from, and using their real names is what
# makes the twin faithful instead of merely isolated.
_QUALIFIED = re.compile(r"\b(core|ops|analysis)\.")
_TWIN_OF = {"core": CORE, "ops": OPS, "analysis": ANALYSIS_TWIN}



def apply_chain(cur):
    """Apply 0001..latest to the twins on an open cursor. Caller rolls back.

    Refuses outright without a disposable server. This is the structural half of the guard: a
    new module that forgets `requires_disposable` cannot quietly reintroduce production DDL,
    which is exactly how `test_status_sql.py` came to run CREATE SCHEMA against production while
    a workflow comment asserted that job skipped such tests.
    """
    if disposable_socket() is None:
        raise RuntimeError(
            "apply_chain builds the full migration chain and must only ever run against the "
            "disposable PostgreSQL 17 server. PERSONAL_OS_TEST_SOCKET is not set. "
            "Run these tests via tools/test_local_sql.py."
        )
    # Supabase supplies these; a bare PostgreSQL 17 cluster does not, and 31 migrations grant to
    # them by name. Without them the chain dies on `role "anon" does not exist` and the location
    # grants under test are never installed — REQ-LOC-001 asserts the restricted schema grants
    # NOTHING to these roles, which is only a meaningful assertion where they exist. Same
    # idempotent, transactional pattern as tests/_import_fixture.py; they vanish at rollback.
    for role in SUPABASE_ROLES:
        cur.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""")
    # The numbered chain does not create the pre-chain public.* tables (public.checkins and 33
    # others); production already has them, so applying the chain there masked the dependency.
    # From empty it is "impossible without them" (ADR-0088) — the same file and the same reason
    # tools/verify_migration_chain.py applies it. Pure public.*, no twin placeholders, so it is
    # applied verbatim.
    legacy = run_migration.MIG_DIR / "_legacy_prerequisites.sql"
    for s_ in run_migration.split_statements(legacy.read_text()):
        cur.execute(s_)
    # Supabase keeps pg_trgm in a schema called `extensions`; migrations 0035/0036 install it
    # there by name (`extensions.similarity`, `extensions.gin_trgm_ops`). A bare cluster has no
    # such schema. Created under its real name so the migration text stays untouched — on a
    # disposable server there is nothing to protect it from.
    cur.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {ANALYSIS_TWIN}")
    # Supabase supplies auth.jwt(); the owner checks read the same JWT setting. A test
    # prerequisite, not a claim about external authentication (as in tests/_ask_fixture.py).
    cur.execute("CREATE SCHEMA IF NOT EXISTS auth")
    cur.execute("""CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE
        AS $$ SELECT nullif(current_setting('request.jwt.claims', true), '')::jsonb $$""")
    files = sorted(run_migration.MIG_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    n = 0
    for f in files:
        sql = f.read_text().replace("__CORE__", CORE).replace("__OPS__", OPS)
        sql = _LOC_WORD.sub(LOC_SCHEMA, sql)
        sql = _QUALIFIED.sub(lambda m: f"{_TWIN_OF[m.group(1)]}.", sql)
        for s in run_migration.split_statements(sql):
            try:
                cur.execute(s)
            except Exception as e:
                # Which statement, in which migration. A bare DatabaseError here names neither,
                # and the chain is 573 statements long.
                raise RuntimeError(
                    f"{f.name}: statement {n + 1} failed: {type(e).__name__}: {e}\n"
                    f"--- SQL ---\n{s[:600]}"
                ) from e
            n += 1
    return n


def as_owner(cur):
    cur.execute("""select set_config('request.jwt.claims',
                   '{"email":"joseph.delany21@gmail.com"}', true)""")
