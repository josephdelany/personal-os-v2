"""B14R step 1-2: the source inventory and derivation catalogue (REQ-REC-001..004).

The value of this unit is that the inventory cannot hold a comfortable falsehood. These
tests are therefore mostly about what the table REFUSES, not what it stores.
"""
import os
import re

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements


def rebind(sql):
    sql = sql.replace("__CORE__", "inv_core_pytest")
    return re.sub(r"\bconfig\.", "config_pytest.", sql)


@pytest.fixture
def inv_cur(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    cur = sql_connection.cursor()
    for schema in ("inv_core_pytest", "config_pytest"):
        cur.execute(f"CREATE SCHEMA {schema}")
    # The migration REVOKEs from Supabase's API roles; the disposable server has no PostgREST.
    for role in ("anon", "authenticated"):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE ROLE {role}")
    for filename in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
                     "0053_source_inventory.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            cur.execute(rebind(statement))
    cur.execute("""INSERT INTO inv_core_pytest.metric_registry
                   (metric_key, display_name, family, unit, state_class)
                   VALUES ('steps','Steps','activity','count','measurement')
                   ON CONFLICT DO NOTHING""")
    return cur


def insert(cur, **kw):
    base = dict(source_family="apple_health", record_type="T", availability="verified_present",
                disposition="pending_implementation",
                disposition_reason="a reason long enough to be a reason",
                owner="B13", parser_supported=False, metric_key=None, record_count=None,
                event_date_from=None, event_date_to=None, count_in_window=None,
                import_status="not imported", duplicate_of=None, scan_method="test")
    base.update(kw)
    cols = ", ".join(base)
    marks = ", ".join(
        f"%s::config_pytest.source_{c}" if c in ("availability", "disposition") else "%s"
        for c in base)
    cur.execute(f"INSERT INTO config_pytest.source_inventory ({cols}) VALUES ({marks})",
                tuple(base.values()))


def test_REQ_REC_003_a_source_cannot_be_used_without_a_parser_that_reads_it(inv_cur):
    """The prose inventory this replaces described types as in use that no parser mapped.
    A CHECK constraint is the difference between an inventory and a wish."""
    inv_cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        insert(inv_cur, disposition="used", parser_supported=False, metric_key="steps")
    assert "used_requires_a_parser" in str(e.value)
    inv_cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_003_used_must_name_the_metric_it_becomes(inv_cur):
    inv_cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        insert(inv_cur, disposition="used", parser_supported=True, metric_key=None)
    assert "used_requires_a_parser" in str(e.value)
    inv_cur.execute("ROLLBACK TO SAVEPOINT s")
    insert(inv_cur, disposition="used", parser_supported=True, metric_key="steps")


def test_REQ_REC_002_an_unverified_asset_may_not_report_a_record_count(inv_cur):
    """The historical design documents are full of confident volumes for assets nobody has
    located. An asset named only in one of them carries NULL counts or it does not go in."""
    inv_cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        insert(inv_cur, source_family="concept_only", record_type="Spotify listening history",
               availability="unverified_mentioned", record_count=50000)
    assert "unverified_carries_no_numbers" in str(e.value)
    inv_cur.execute("ROLLBACK TO SAVEPOINT s")
    insert(inv_cur, source_family="concept_only", record_type="Spotify listening history",
           availability="unverified_mentioned")


def test_REQ_REC_003_a_disposition_carries_a_substantive_reason_and_a_named_owner(inv_cur):
    for bad, constraint in ((dict(disposition_reason="n/a"), "reason_is_substantive"),
                            (dict(owner=" "), "owner_is_named")):
        inv_cur.execute("SAVEPOINT s")
        with pytest.raises(Exception) as e:
            insert(inv_cur, **bad)
        assert constraint in str(e.value), str(e.value)
        inv_cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_008_a_duplicate_must_name_what_it_duplicates(inv_cur):
    """Unnamed duplication is how the same records get counted as independent corroboration."""
    inv_cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        insert(inv_cur, disposition="duplicate", duplicate_of=None)
    assert "duplicate_names_its_original" in str(e.value)
    inv_cur.execute("ROLLBACK TO SAVEPOINT s")


def test_RULE_04_a_scan_cannot_report_records_dated_after_the_scan(inv_cur):
    inv_cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        insert(inv_cur, event_date_from="2026-01-01", event_date_to="2099-01-01")
    assert "no_future_coverage" in str(e.value)
    inv_cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_004_a_derived_measure_states_its_time_specification(inv_cur):
    """RULE-08. OQ-54 exists because 14,640 imported atoms recorded an interval quantity as
    an instant; the catalogue makes that claim explicit instead of implicit."""
    inv_cur.execute("SAVEPOINT s")
    with pytest.raises(Exception):
        inv_cur.execute("""INSERT INTO config_pytest.derivation_catalogue
            (measure, input_fields, method, method_version, unit, time_specification,
             missingness_rule, owner)
            VALUES ('steps', ARRAY['value'], 'sum', 'v1', 'count', 'whenever',
                    'absent days are unknown', 'B13')""")
    inv_cur.execute("ROLLBACK TO SAVEPOINT s")
    inv_cur.execute("""INSERT INTO config_pytest.derivation_catalogue
        (measure, input_fields, method, method_version, unit, time_specification,
         missingness_rule, owner)
        VALUES ('steps', ARRAY['value'], 'sum', 'v1', 'count', 'interval',
                'absent days are unknown, never zero', 'B13')""")


def test_REQ_REC_004_a_measure_with_no_named_inputs_is_not_a_derivation(inv_cur):
    inv_cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        inv_cur.execute("""INSERT INTO config_pytest.derivation_catalogue
            (measure, input_fields, method, method_version, unit, time_specification,
             missingness_rule, owner)
            VALUES ('steps', ARRAY[]::text[], 'sum', 'v1', 'count', 'interval',
                    'absent days are unknown', 'B13')""")
    assert "inputs_are_named" in str(e.value)
    inv_cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_001_parser_support_is_read_from_the_importer_not_asserted(inv_cur):
    """The seed file carries its own parser_supported flag, written by another process on
    another day. build_inventory.py reads the importer instead and stops on disagreement —
    a mismatch means either the inventory or the importer is misdescribing the system."""
    from tools.build_inventory import rows_from_seed, parser_support
    supported, metric_of = parser_support()
    seed = {"health_record_types": {
                "HKQuantityTypeIdentifierStepCount": {
                    "count": 10, "from": "2020-01-01", "to": "2026-01-01",
                    "since_2026_07_01": 5, "parser_supported": False}},  # the lie
            "archives": [], "concept_only_unverified": []}
    _, disagreements, _ = rows_from_seed(seed, supported, metric_of, {})
    assert disagreements == [("HKQuantityTypeIdentifierStepCount", False, True)], disagreements


def test_REQ_REC_002_an_unlocated_asset_is_never_given_a_disposition_of_available(inv_cur):
    from tools.build_inventory import rows_from_seed, parser_support
    supported, metric_of = parser_support()
    seed = {"health_record_types": {}, "archives": [],
            "concept_only_unverified": ["old-workspace bank exports"]}
    rows, _, _ = rows_from_seed(seed, supported, metric_of, {})
    row, = rows
    assert row["availability"] == "unverified_mentioned"
    assert row["record_count"] is None and row["count_in_window"] is None
    assert row["disposition"] != "used"


def test_REQ_REC_003_an_unparsed_type_with_no_ruling_is_owned_by_joe_not_a_build_unit(inv_cur):
    """Assigning an undecided measurement to a build unit silently converts a question Joe
    has never been asked into committed work. It stays his."""
    from tools.build_inventory import rows_from_seed, parser_support
    supported, metric_of = parser_support()
    seed = {"health_record_types": {
                "HKQuantityTypeIdentifierPhysicalEffort": {
                    "count": 8577, "from": "2024-06-24", "to": "2026-08-21",
                    "since_2026_07_01": 8577, "parser_supported": False}},
            "archives": [], "concept_only_unverified": []}
    rows, disagreements, unassigned = rows_from_seed(seed, supported, metric_of, {})
    assert disagreements == []
    assert rows[0]["owner"] == "Joe (scope ruling)", rows[0]
    assert unassigned == [("HKQuantityTypeIdentifierPhysicalEffort", 8577)]
