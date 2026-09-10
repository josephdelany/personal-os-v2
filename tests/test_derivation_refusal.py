"""INTENT_COVERAGE R7: an uncatalogued derivation is refused, never approximated.

The failure this guards against is not a wrong number. It is a RIGHT number wearing the wrong
label — a count of browser visits returned as "screen hours" — which no downstream check can
detect, because the value is internally consistent and only the unit is a lie.
"""
import datetime as dt
import json
import os
import re

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements

S = "deriv_core_pytest"


def rebind(sql):
    sql = sql.replace("__CORE__", S).replace("__OPS__", "ops_pytest")
    for schema in ("public", "analysis", "config", "auth"):
        sql = re.sub(rf"\b{schema}\.", f"{schema}_pytest.", sql)
        sql = re.sub(rf"\bSCHEMA {schema}\b", f"SCHEMA {schema}_pytest", sql)
    return sql


@pytest.fixture
def cur(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (S, "config_pytest", "analysis_pytest", "auth_pytest", "public_pytest",
                   "ops_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    c.execute("""CREATE FUNCTION auth_pytest.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$
        SELECT nullif(current_setting('request.jwt.claims', true), '')::jsonb $$""")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    for f in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
              "0053_source_inventory.sql", "0068_derivation_refusal.sql"):
        for stmt in split_statements((ROOT / "migrations" / f).read_text()):
            c.execute(rebind(stmt))
    for key, name in (("browser_visits", "Browser visits"), ("screen_hours", "Screen hours")):
        c.execute(f"""INSERT INTO {S}.metric_registry
                      (metric_key, display_name, family, unit, state_class)
                      VALUES (%s,%s,'device','count','total') ON CONFLICT DO NOTHING""",
                  (key, name))
    # One CATALOGUED derivation. `screen_hours` is deliberately registered and NOT catalogued:
    # that is the exact state R7 describes — the measure is a known name, and this system has
    # no way to derive it.
    c.execute("""INSERT INTO config_pytest.derivation_catalogue
        (measure, input_fields, method, method_version, unit, time_specification,
         missingness_rule, earliest_supported_event_date, analytical_consumers, owner)
        VALUES ('browser_visits', ARRAY['history.visit_time'], 'count_of_visit_rows', 'v1',
                'count', 'subject_day_aggregate',
                'A day with no history rows is unknown, not zero.', '2026-07-01',
                ARRAY['panel'], 'backend')""")
    c.execute("SELECT set_config('request.jwt.claims', %s, true)",
              ('{"email":"joseph.delany21@gmail.com"}',))
    return c


def support(c, measure):
    c.execute("SELECT public_pytest.derivation_support(%s)", (measure,))
    out = c.fetchone()[0]
    return json.loads(out) if isinstance(out, str) else out


def test_REQ_REC_004_a_catalogued_measure_returns_its_whole_derivation(cur):
    """The missingness rule travels with the number. Without it a caller cannot tell a real
    zero from an absent day, and "missing is not zero" becomes advice rather than a rule."""
    out = support(cur, "browser_visits")
    assert out["supported"] is True
    assert out["method"] == "count_of_visit_rows"
    assert out["method_version"] == "v1"
    assert out["time_specification"] == "subject_day_aggregate"
    assert "not zero" in out["missingness_rule"]
    assert out["input_fields"] == ["history.visit_time"]


def test_REQ_REC_003_a_registered_measure_with_no_derivation_is_refused_by_name(cur):
    """`screen_hours` is a known metric this system cannot derive. That is a different
    disposition from a measure nobody has heard of, and it has a different owner."""
    out = support(cur, "screen_hours")
    assert out["supported"] is False
    assert out["reason"] == "registered_metric_without_a_catalogued_derivation"


def test_REQ_REC_003_an_unknown_measure_is_refused_as_unknown(cur):
    out = support(cur, "mood_index_9000")
    assert out["supported"] is False
    assert out["reason"] == "unknown_measure"


def test_R7_a_refusal_never_hands_back_a_substitute_measure(cur):
    """The whole scenario in one assertion.

    Asked for screen hours with only visit timestamps available, the system must not answer
    with visits. A count of visits is not a duration, whatever unit is attached to it.
    """
    out = support(cur, "screen_hours")
    assert "substitute" in out, "the key must be present so a caller does not improvise one"
    assert out["substitute"] is None
    # What it MAY say is what it can derive — a fact about the boundary, under a key that
    # cannot be mistaken for an answer to the question asked.
    assert out["supported_derivations"] == ["browser_visits"]
    assert out["measure"] == "screen_hours", "the refusal is about the measure that was ASKED for"
    assert "may not be relabelled" in out["note"]


def test_R7_the_refusal_is_owner_only_like_every_other_read_path(cur):
    cur.execute("SELECT set_config('request.jwt.claims', %s, true)", ('{"email":"nope@x.com"}',))
    with pytest.raises(Exception, match="owner only"):
        cur.execute("SELECT public_pytest.derivation_support(%s)", ("browser_visits",))
