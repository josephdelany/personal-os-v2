"""A disposable, production-faithful spine schema for the B13 importer tests.

RULE-01's bounded exception (ADR-0022, OQ-21) permits a behavioural test to build a
**disposable schema** — never `core`, never `public` — insert fixture rows, assert, and roll
the whole transaction back so nothing is committed and no row is ever read as data.

The schema is built by running the *real* migrations with `__CORE__`/`__OPS__` rewritten to
throwaway names, rather than by hand-copying their DDL into a fixture. A hand-copy drifts from
production silently, and a test that passes against a drifted copy of the schema proves
nothing about the schema the importer will actually meet.

Nothing here drops anything. The schema exists only inside the caller's transaction and is gone
when that transaction rolls back, so there is never a prior copy to remove.

An earlier version carried an `assert_disposable_server` guard, because two test files created
schemas literally named `core`, `analysis` and `public` — which RULE-01 forbids — and leaned on
the server being temporary instead. `panel.build` and `check_freshness.check` now take their
schema names as parameters, so every test schema is a throwaway name and the guard had nothing
left to protect. It was removed rather than kept: a guard that guards nothing is the same shape
as the dead range-check this session already had to answer for (OQ-52).
"""
import re
from pathlib import Path

from tools.run_migration import split_statements

ROOT = Path(__file__).resolve().parents[1]

# In dependency order. 0051 is the migration under test.
#
# The three seed migrations are not optional scenery: `core.atoms.metric_key` is a foreign
# key into `metric_registry`, so an atom for an unregistered metric cannot be inserted at
# all. 0022 registers `steps`, `resting_hr`, `hrv_sdnn_ms`, `weight_lb` and the rest of the
# base health set that the Apple Health importer reuses, and 0051 registers the metrics it
# adds. Omitting them makes the importer tests fail on a foreign key — which is the schema
# telling the truth, and the reason the fixture runs the real migrations rather than a
# hand-written approximation of them.
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
         "0011_ops.sql", "0012_grants_and_immutability.sql", "0016_alcohol_metric_seed.sql",
         "0019_checkin_metric_seed.sql", "0022_workout_health_seed.sql",
         "0051_file_import.sql")

# 0012 installs RULE-02's enforcement (revoked grants + the append-only triggers) but also
# grants on `entities`, `links` and `findings`, which belong to migrations this spine does not
# need. Only the statements naming the two append-only tables are applied, so the schema under
# test carries real RULE-02 enforcement without dragging in half the chain. Without this, the
# RULE-02 test ran against a schema with no protection at all and could only grep source text.
PARTIAL = {
    "0012_grants_and_immutability.sql":
        lambda stmt: ("raw_captures" in stmt or "atoms" in stmt
                      or re.search(r"CREATE\s+(OR\s+REPLACE\s+)?FUNCTION", stmt, re.I)
                      or stmt.strip().upper().startswith("DO ")),
}

CORE = "core_import_pytest"
OPS = "ops_import_pytest"

_CREATES_CAPTURE_SOURCE = re.compile(
    r"CREATE\s+TYPE\s+\S*capture_source\s+AS\s+ENUM", re.IGNORECASE)


def _with_file_import(stmt):
    """Add the 'file_import' label to a CREATE TYPE ... capture_source statement.

    The label is inserted before the statement's final ')' rather than by matching the enum
    body, because that body carries a line comment containing parentheses
    ("-- reserved (net-new feeds, Phase 3/4)") and any paren-counting pattern reads it as the
    end of the list.
    """
    i = stmt.rfind(")")
    assert i != -1, stmt
    return stmt[:i] + ", 'file_import'" + stmt[i:]


def _statements(name, core, ops):
    sql = (ROOT / "migrations" / name).read_text().replace("__CORE__", core).replace("__OPS__", ops)
    keep = PARTIAL.get(name)
    for stmt in split_statements(sql):
        if keep is not None and not keep(stmt):
            continue
        s = stmt.strip()
        if not s:
            continue
        # PostgreSQL forbids *using* an enum label in the same transaction that added it with
        # ALTER TYPE ... ADD VALUE. The tests insert a 'file_import' capture, so in the
        # disposable schema the label is folded into the original CREATE TYPE instead. The
        # production path is unaffected — it runs 0051's ALTER in its own committed
        # transaction. `test_migration_0051_adds_the_file_import_label` checks the two agree.
        if re.search(r"ALTER\s+TYPE\s+\S*capture_source\s+ADD\s+VALUE", s, re.IGNORECASE):
            continue
        if _CREATES_CAPTURE_SOURCE.search(s):
            s = _with_file_import(s)
        yield s


# Supabase supplies these; a bare PostgreSQL cluster does not. Migration 0012 grants to them by
# name, so without them RULE-02's enforcement cannot be installed and the schema under test
# would have no append-only protection at all. CREATE ROLE is transactional, so these vanish
# with the rollback like everything else.
SUPABASE_ROLES = ("anon", "authenticated", "service_role")


def build_spine(cur, migrations=SPINE, core=CORE, ops=OPS):
    """Create the disposable spine. Caller owns the transaction and MUST roll it back."""
    for role in SUPABASE_ROLES:
        cur.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""")
    cur.execute(f"CREATE SCHEMA {core}")
    cur.execute(f"CREATE SCHEMA {ops}")
    for name in migrations:
        for stmt in _statements(name, core, ops):
            cur.execute(stmt)
    return core, ops
