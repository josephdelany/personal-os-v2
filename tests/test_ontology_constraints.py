"""REQ-ONT — the taxonomy and lane constraints the database already enforces.

The requirement audit showed 3 of 17 REQ-ONT requirements proven. Most of the rest are
enforced by constraints that have simply never had a test carrying their ID — the database
refuses the wrong row today and nothing said so.

These tests do not add enforcement. They record which enforcement exists, so that removing a
constraint fails here instead of silently widening what the system will accept (RULE-00).
"""
import datetime as dt
import os
import re
import uuid

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements

S = "ont_core_pytest"


@pytest.fixture
def cur(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    c.execute(f"CREATE SCHEMA {S}")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    for filename in ("0002_metric_registry.sql", "0003_entities.sql", "0004_raw_captures.sql",
                     "0005_atoms.sql", "0014_ontology_checks.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            if filename == "0014_ontology_checks.sql" and "__CORE__." not in statement:
                continue
            c.execute(statement.replace("__CORE__", S))
    c.execute(f"""INSERT INTO {S}.metric_registry (metric_key, display_name, family, unit,
                  state_class) VALUES ('steps','Steps','activity','count','total')""")
    c.execute(f"""INSERT INTO {S}.raw_captures (capture_id, source, captured_at, payload,
                  trust_level) VALUES (gen_random_uuid(),'shortcut_text', now(), '{{}}', 'trusted')
                  RETURNING capture_id""")
    c._capture = c.fetchone()[0]
    return c


def enum_members(c, name):
    c.execute(f"SELECT unnest(enum_range(NULL::{S}.{name}))::text")
    return [r[0] for r in c.fetchall()]


def atom(c, **kw):
    base = dict(raw_capture_id=c._capture, kind="activity_sample", metric_key="steps",
                occurred_at=dt.datetime(2026, 9, 1, 12, tzinfo=dt.timezone.utc),
                time_precision="exact", subject_day=dt.date(2026, 9, 1),
                subject_day_rule_version="v1", presence="observed",
                value_low=1, value_point=1, value_high=1, estimate_method="measured",
                unit="count", state_class="total", value_type="numeric",
                trust_level="trusted", provenance="extracted", code_version="t")
    base.update(kw)
    cols = ", ".join(base)
    marks = ", ".join(
        # `value_type` is a plain text column, not an enum — casting it fails at parse time
        # and masks whatever the test was actually checking.
        f"%s::{S}.{c2}" if c2 in ("presence", "provenance", "state_class",
                                  "time_precision", "trust_level") else "%s"
        for c2 in base)
    c.execute(f"INSERT INTO {S}.atoms ({cols}) VALUES ({marks})", tuple(base.values()))


def refuses(c, fragment, **kw):
    c.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        atom(c, **kw)
    assert fragment in str(e.value), str(e.value)
    c.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_ONT_008_presence_is_exactly_three_valued(cur):
    """A logged absence and an unlogged day must never collapse into the same value (RULE-07).
    Two values would force one of them to masquerade as the other."""
    assert enum_members(cur, "presence") == ["observed", "observed_absent", "unknown"]


def test_REQ_ONT_009_provenance_is_the_closed_three(cur):
    assert enum_members(cur, "provenance") == ["extracted", "inferred", "defaulted"]


def test_REQ_ONT_010_state_class_is_the_closed_three(cur):
    """The database can then refuse an aggregation the class forbids — summing a measurement
    is the error this vocabulary exists to make expressible."""
    assert enum_members(cur, "state_class") == ["measurement", "total", "total_increasing"]


def test_REQ_ONT_003_a_metric_key_must_reference_the_registry(cur):
    """A measure is a registry reference, never a new `kind`. Without the foreign key a typo
    becomes a new metric that looks real and aggregates to nothing."""
    refuses(cur, "foreign key", metric_key="steps_typo")


def test_REQ_ONT_011_an_unknown_presence_cannot_carry_a_value(cur):
    """"Not known" must never be stored as a number — that is how a gap becomes a zero."""
    refuses(cur, "atoms_unknown_has_no_value", presence="unknown")
    atom(cur, presence="unknown", value_low=None, value_point=None, value_high=None,
         estimate_method=None, state_class=None)


def test_REQ_ONT_012_a_stored_value_must_carry_its_lane(cur):
    """A measured value and an inferred value never share a column (INV-5). The lane is the
    estimate_method and the state_class, and a value without both is unclassifiable."""
    refuses(cur, "atoms_value_has_lane", estimate_method=None)
    refuses(cur, "atoms_value_has_lane", state_class=None)


def test_REQ_ONT_013_every_atom_traces_to_a_raw_capture(cur):
    """INV-1. An atom with no capture is a number with no origin, which is the shape a
    fabricated row takes."""
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        atom(cur, raw_capture_id=None)
    assert "null value" in str(e.value).lower() or "not-null" in str(e.value).lower()
    cur.execute("ROLLBACK TO SAVEPOINT s")
    refuses(cur, "foreign key", raw_capture_id=uuid.uuid4())


def test_REQ_ONT_014_a_subject_day_carries_the_rule_version_that_produced_it(cur):
    """A future change to the 04:00 boundary must be visible in the data rather than silently
    reinterpreting every historical day."""
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        atom(cur, subject_day_rule_version=None)
    assert "subject_day_rule_version" in str(e.value)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_ONT_006_an_entity_type_outside_the_closed_set_is_rejected(cur):
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        cur.execute(f"""INSERT INTO {S}.entities (entity_type, canonical_name, provenance)
                        VALUES ('spaceship','X','human')""")
    assert "entities_type_taxonomy" in str(e.value)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_ONT_001_a_kind_outside_the_closed_taxonomy_is_rejected(cur):
    """The taxonomy is closed so that a new kind is a migration and an ADR, never a typo that
    quietly becomes a category."""
    refuses(cur, "atoms_kind_taxonomy", kind="vibes")
