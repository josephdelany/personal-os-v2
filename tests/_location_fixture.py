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
import re

from tools import run_migration

CORE, OPS = "core_pytest", "ops_pytest"
LOC_SCHEMA = "restricted_pytest"
ANALYSIS_TWIN = "analysis_pytest"

_LOC_WORD = re.compile(r"\brestricted\b")            # the schema name, wherever it appears
_VIEW = re.compile(r"\banalysis\.(visits_public|watch_progress|spec_curves|brief_notes|render_violations)\b")


def apply_chain(cur):
    """Apply 0001..latest to the twins on an open cursor. Caller rolls back."""
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {ANALYSIS_TWIN}")
    files = sorted(run_migration.MIG_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    n = 0
    for f in files:
        sql = f.read_text().replace("__CORE__", CORE).replace("__OPS__", OPS)
        sql = _LOC_WORD.sub(LOC_SCHEMA, sql)
        sql = _VIEW.sub(lambda m: f"{ANALYSIS_TWIN}.{m.group(1)}", sql)
        for s in run_migration.split_statements(sql):
            cur.execute(s)
            n += 1
    return n


def as_owner(cur):
    cur.execute("""select set_config('request.jwt.claims',
                   '{"email":"joseph.delany21@gmail.com"}', true)""")
