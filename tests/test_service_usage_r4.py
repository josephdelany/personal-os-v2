"""R4: a recurring service, and whether a silence is Joe's or the logger's.

    recurring charge atoms -> recurrence.detect -> usage_status -> registered method -> event

REQ-FIN-110..116, REQ-REC-004/005/009; INTENT_COVERAGE R4; ADR-0140.

THE ONE SENTENCE THESE TESTS DEFEND. **An outage is not proof of nonuse.** The engine used to
return 'unused' whenever the newest usage evidence was older than the threshold, with no concept
of whether anything had been watching. In a system whose Watch stopped in five stages ending
2026-08-21 and whose bank CSV export died 2026-05-13, that reads a broken logger as a statement
about Joe's life.

Every database test enters through `tools/service_usage.py` -- `assess`, `rows_for` and the
`write` it calls -- rather than through the engines directly, because the engines already had
passing tests and no caller, which is exactly the state that let this defect survive.
"""
import datetime as dt
import os
import re
import uuid

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.engines import usage_status
from tools.reconstruct_run import load_method, write
from tools.run_migration import split_statements
from tools.service_usage import assess, rows_for, source_last_seen, streams

S = "svc_core_pytest"
AS_OF = dt.date(2026, 9, 11)


def rebind(sql):
    sql = sql.replace("__CORE__", S).replace("__OPS__", "ops_pytest")
    for schema in ("public", "analysis", "config", "auth"):
        sql = re.sub(rf"\b{schema}\.", f"{schema}_pytest.", sql)
        sql = re.sub(rf"\bSCHEMA {schema}\b", f"SCHEMA {schema}_pytest", sql)
    return sql


@pytest.fixture
def svc(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (S, "analysis_pytest", "config_pytest", "auth_pytest", "public_pytest",
                   "ops_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    for f in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
              # 0051 adds `file_import` to the capture_source enum, which is how a bank export
              # arrives. 0004 alone has no value for it.
              "0051_file_import.sql",
              "0054_inferred_events.sql", "0066_inferred_inputs.sql",
              "0069_discriminating_evidence.sql",
              "0073_service_usage_method.sql"):
        for stmt in split_statements((ROOT / "migrations" / f).read_text()):
            c.execute(rebind(stmt))
    for key, unit, state in (("transaction_amount_usd", "usd", "total"),
                             ("visit", "count", "total")):
        c.execute(f"""INSERT INTO {S}.metric_registry
                      (metric_key, display_name, family, unit, state_class)
                      VALUES (%s,%s,'finance',%s,%s) ON CONFLICT DO NOTHING""",
                  (key, key, unit, state))
    return c


def _capture(c):
    cid = uuid.uuid4()
    c.execute(f"""INSERT INTO {S}.raw_captures (capture_id, source, captured_at, payload,
                  trust_level) VALUES (%s,'file_import',%s,'{{}}'::jsonb,'trusted')""",
              (cid, dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)))
    return cid


def charge(c, *, day, merchant, amount=-45.0):
    """One recurring charge, in the atom lane the real tool reads."""
    cid, aid = _capture(c), uuid.uuid4()
    ts = dt.datetime.combine(day, dt.time(12), dt.timezone.utc)
    c.execute(f"""INSERT INTO {S}.atoms
        (id, raw_capture_id, kind, metric_key, occurred_at, subject_day,
         subject_day_rule_version, recorded_at, presence, value_low, value_point, value_high,
         estimate_method, unit, state_class, value_type, trust_level, provenance,
         evidence_span, code_version)
        VALUES (%s,%s,'transaction','transaction_amount_usd',%s,%s,'v1',%s,'observed',
                %s,%s,%s,'measured','usd','total','numeric','trusted','extracted',%s,'test')""",
        (aid, cid, ts, day, ts + dt.timedelta(days=1), amount, amount, amount,
         f"legacy:chase;legacy_id={aid};merchant={merchant};descriptor={merchant}"))


def visit(c, *, day, merchant, kind="place_visit"):
    """One explicit usage evidence row (REQ-FIN-111)."""
    cid, aid = _capture(c), uuid.uuid4()
    ts = dt.datetime.combine(day, dt.time(18), dt.timezone.utc)
    c.execute(f"""INSERT INTO {S}.atoms
        (id, raw_capture_id, kind, metric_key, occurred_at, subject_day,
         subject_day_rule_version, recorded_at, presence, value_low, value_point, value_high,
         estimate_method, unit, state_class, value_type, trust_level, provenance,
         evidence_span, code_version)
        VALUES (%s,%s,%s,'visit',%s,%s,'v1',%s,'observed',1,1,1,'measured','count','total',
                'numeric','trusted','extracted',%s,'test')""",
        (aid, cid, kind, ts, day, ts + dt.timedelta(days=1), f"place={merchant}"))


def monthly(c, merchant, *, n=8, last=AS_OF, amount=-45.0):
    for i in range(n):
        charge(c, day=last - dt.timedelta(days=30 * i), merchant=merchant, amount=amount)


# --- the engines reach the tool at all --------------------------------------------------

def test_REQ_FIN_130_recurring_charges_become_a_stream_through_the_real_reader(svc):
    """`recurrence.detect` had no non-test caller. This is the caller."""
    monthly(svc, "CITY GYM", n=8)
    found = streams(svc, core=S, as_of=AS_OF)
    assert len(found) == 1
    s = found[0]
    assert s.merchant == "CITY GYM"
    assert s.occurrences == 8
    assert s.maturity == "mature"
    assert s.lifecycle == "active"


# --- INTENT_COVERAGE R4 -----------------------------------------------------------------

def test_REQ_REC_009_a_logging_outage_is_unknown_not_unused(svc):
    """THE R4 CASE, through the tool.

    Joe visited the gym until 2026-05-01. The visit logger also stopped on 2026-05-01. Four
    months later there are no visits — and no reason to believe that says anything about Joe.
    """
    monthly(svc, "CITY GYM", n=8)
    for i in range(6):
        visit(svc, day=dt.date(2026, 5, 1) - dt.timedelta(days=7 * i), merchant="CITY GYM")
    assessed, watching = assess(svc, core=S, as_of=AS_OF)
    assert watching == dt.date(2026, 5, 1), "the source died the day of the last visit"
    _, status, _ = assessed[0]
    assert status.tier == "unknown"
    assert status.tier != "unused"
    assert "the gap is the source's" in status.evidence
    assert status.confidence == 0.0


def test_REQ_FIN_111_a_watching_source_that_saw_nothing_reports_unused(svc):
    """The other half. An engine that can never say 'unused' has replaced one wrong answer with
    another, so the watched-and-empty window must still reach that tier."""
    monthly(svc, "CITY GYM", n=8)
    for i in range(6):
        visit(svc, day=dt.date(2026, 5, 1) - dt.timedelta(days=7 * i), merchant="CITY GYM")
    # A DIFFERENT place keeps logging right up to the present, so the instrument is demonstrably
    # alive and simply never saw Joe at the gym again.
    visit(svc, day=AS_OF - dt.timedelta(days=2), merchant="THE LIBRARY")
    assessed, watching = assess(svc, core=S, as_of=AS_OF)
    assert watching == AS_OF - dt.timedelta(days=2)
    gym = next(s for st, s, _ in assessed if st.merchant == "CITY GYM")
    assert gym.tier == "unused"
    assert "kept recording for" in gym.evidence


def test_REQ_FIN_111_recent_use_reports_used(svc):
    monthly(svc, "CITY GYM", n=8)
    visit(svc, day=AS_OF - dt.timedelta(days=3), merchant="CITY GYM")
    assessed, _ = assess(svc, core=S, as_of=AS_OF)
    assert assessed[0][1].tier == "used"


def test_REQ_FIN_111_no_usage_source_at_all_is_unknown_for_every_service(svc):
    """The current state of this database: no place_visit, media_play or web_visit has ever been
    written. Every service is 'unknown', and that is a true statement about the record."""
    monthly(svc, "CITY GYM", n=8)
    monthly(svc, "STREAMING CO", n=8, amount=-15.0)
    assert source_last_seen(svc, core=S, as_of=AS_OF) is None
    assessed, watching = assess(svc, core=S, as_of=AS_OF)
    assert watching is None
    assert len(assessed) == 2
    assert {s.tier for _, s, _ in assessed} == {"unknown"}


# --- what reaches the event table -------------------------------------------------------

def test_REQ_REC_009_an_outage_stores_no_event_and_names_the_missing_input(svc):
    """The outage is a MISSING REQUIRED INPUT, not a branch someone remembered to write.

    `usage_observation_window` is emitted only when the source produced something after the last
    recorded use, so a dead source cannot produce it and the engine's existing REQ-REC-009 path
    returns unknown with the input named. There is no code path from a dead sensor to a
    conclusion.
    """
    monthly(svc, "CITY GYM", n=8)
    for i in range(6):
        visit(svc, day=dt.date(2026, 5, 1) - dt.timedelta(days=7 * i), merchant="CITY GYM")
    m = load_method(svc, "service_usage", core=S, config="config_pytest")
    coverage = []
    rows, _, _ = rows_for(svc, m, core=S, as_of=AS_OF, coverage=coverage)
    assert rows == [], "nothing concluded"
    assert len(coverage) == 1
    merchant, tier, missing = coverage[0]
    assert merchant == "CITY GYM" and tier == "unknown"
    assert "usage_observation_window" in missing
    svc.execute(f"SELECT count(*) FROM {S}.inferred_events")
    assert svc.fetchone()[0] == 0


def test_REQ_REC_005_an_observed_use_is_stored_as_an_occurred_event(svc):
    monthly(svc, "CITY GYM", n=8)
    visit(svc, day=AS_OF - dt.timedelta(days=40), merchant="CITY GYM")
    visit(svc, day=AS_OF - dt.timedelta(days=2), merchant="CITY GYM")
    m = load_method(svc, "service_usage", core=S, config="config_pytest")
    rows, _, _ = rows_for(svc, m, core=S, as_of=AS_OF)
    assert len(rows) == 1
    assert write(svc, rows, core=S) == 1
    svc.execute(f"""SELECT event_family, method_key, presence FROM {S}.inferred_events""")
    assert [list(r) for r in svc.fetchall()] == [
        ["service_usage", "service_usage", "occurred"]]


def test_REQ_REC_009_no_row_ever_asserts_nonuse(svc):
    """'unused' is not an event and is never stored. It is the absence of a class of events over
    a window, and a table of them would assert nothing while burying what does."""
    monthly(svc, "CITY GYM", n=8)
    for i in range(6):
        visit(svc, day=dt.date(2026, 5, 1) - dt.timedelta(days=7 * i), merchant="CITY GYM")
    visit(svc, day=AS_OF - dt.timedelta(days=2), merchant="THE LIBRARY")
    m = load_method(svc, "service_usage", core=S, config="config_pytest")
    rows, assessed, _ = rows_for(svc, m, core=S, as_of=AS_OF)
    gym = next(s for st, s, _ in assessed if st.merchant == "CITY GYM")
    assert gym.tier == "unused", "the tier is reported"
    write(svc, rows, core=S)
    svc.execute(f"""SELECT count(*) FROM {S}.inferred_events
                     WHERE presence = 'did_not_occur'""")
    assert svc.fetchone()[0] == 0, "and it is never stored as an event"


def test_REQ_REC_004_service_usage_is_read_from_the_registry(svc):
    m = load_method(svc, "service_usage", core=S, config="config_pytest")
    assert m.event_family == "service_usage"
    assert "usage_observation_window" in m.required_evidence
    assert m.permissible_outputs == ("occurred",)
    assert "did_not_occur" not in m.permissible_outputs


def test_REQ_FIN_112_no_status_this_tool_produces_carries_a_banned_word(svc):
    """Written, stored, displayed or exported are the same check, and it runs on every tier."""
    monthly(svc, "CITY GYM", n=8)
    for i in range(6):
        visit(svc, day=dt.date(2026, 5, 1) - dt.timedelta(days=7 * i), merchant="CITY GYM")
    visit(svc, day=AS_OF - dt.timedelta(days=2), merchant="THE LIBRARY")
    assessed, _ = assess(svc, core=S, as_of=AS_OF)
    for _, status, _ in assessed:
        assert usage_status.guard_words(status.evidence) is True
        assert usage_status.guard_words(status.subject) is True


def test_REQ_FIN_113_no_tier_is_ever_reported_without_its_evidence(svc):
    """"Unused" alone is an accusation. Every tier this tool produces names what produced it."""
    monthly(svc, "CITY GYM", n=8)
    visit(svc, day=AS_OF - dt.timedelta(days=3), merchant="CITY GYM")
    assessed, _ = assess(svc, core=S, as_of=AS_OF)
    for _, status, _ in assessed:
        assert status.evidence and len(status.evidence) > 20
        assert status.tier in usage_status.TIERS
