"""Spine invariant tests. Named with the rule IDs they cover (DoD item 1/3).

Each test applies the full forward-only migration to a throwaway schema pair
inside ONE transaction and ROLLS BACK — the live database is never mutated and no
data row is ever inserted (RULE-01). The append-only guarantees are proven
behaviourally: the grant path via a service_role privilege denial, the trigger
path via the owner hitting the statement-level append-only trigger — both on empty
tables, so nothing is fabricated.

Run: python3 -m pytest tests/test_spine_invariants.py -v
(Requires SUPABASE_DB_URL in the environment, same as every ETL path.)
"""
import os
import pytest

# _location_fixture owns the whole-chain twin builder; it is no longer specific to
# location, and renaming it is left to the main session to avoid a wide rename here.
from tests._location_fixture import apply_chain
from tests._sql_fixture import connect, requires_disposable
from tools import run_migration, check_invariants

# Applies the migration chain to a throwaway schema pair. That is disposable-server
# work: gated on SUPABASE_DB_URL it ran the DDL against production behind a rollback,
# and it is in OQ-78's list of modules that timed out with 57014 doing so.
pytestmark = requires_disposable

CORE = "core_pytest"
OPS = "ops_pytest"


@pytest.fixture()
def spine_cursor():
    """Apply the migration to a throwaway schema pair in a transaction; roll back."""
    conn = connect()
    cur = conn.cursor()
    try:
        # The full twin chain: Supabase roles, the pre-chain public.* tables, the
        # `extensions` schema, and every migration with its qualified core/ops/analysis
        # references rewritten. run_migration.apply substitutes only the __CORE__/__OPS__
        # placeholders, so 30 files kept naming `core.atoms` and friends OUTRIGHT and
        # those resolved to the REAL schemas -- production, under the live job. Same
        # defect the location family had. apply_chain builds the same twin pair
        # (core_pytest/ops_pytest) this module already names.
        apply_chain(cur)
        yield cur
    finally:
        conn.rollback()   # nothing persists; no schema, no row left behind
        conn.close()


def test_RULE_02_append_only_grants_and_triggers(spine_cursor):
    """RULE-02: no app role may UPDATE/DELETE atoms/raw_captures (grant), and the
    owner is stopped by the append-only trigger. check_invariants proves both and
    also confirms RULE-04 is honestly pending (no derived_measures yet)."""
    assert check_invariants.run_checks(spine_cursor, CORE) is True


def test_RULE_02_atoms_reject_update_as_owner(spine_cursor):
    """RULE-02 trigger path: even the table owner cannot UPDATE atoms."""
    spine_cursor.execute("SAVEPOINT sp")
    with pytest.raises(Exception) as exc:
        spine_cursor.execute(f"UPDATE {CORE}.atoms SET code_version='x'")
    spine_cursor.execute("ROLLBACK TO SAVEPOINT sp")
    assert "RULE-02" in str(exc.value)


def test_RULE_02_raw_captures_reject_delete_as_owner(spine_cursor):
    """RULE-02 trigger path: even the table owner cannot DELETE raw_captures."""
    spine_cursor.execute("SAVEPOINT sp")
    with pytest.raises(Exception) as exc:
        spine_cursor.execute(f"DELETE FROM {CORE}.raw_captures")
    spine_cursor.execute("ROLLBACK TO SAVEPOINT sp")
    assert "RULE-02" in str(exc.value)


def test_REQ_INF_103_hypothesis_register_freezes_prereg_columns(spine_cursor):
    """REQ-INF-103: the pre-registration freeze trigger exists on hypothesis_register."""
    spine_cursor.execute(
        """select count(*) from pg_trigger t
             join pg_class c on c.oid=t.tgrelid
             join pg_namespace n on n.oid=c.relnamespace
            where n.nspname=%s and c.relname='hypothesis_register'
              and t.tgname='hypothesis_register_freeze' and not t.tgisinternal""",
        (CORE,),
    )
    assert spine_cursor.fetchone()[0] == 1
