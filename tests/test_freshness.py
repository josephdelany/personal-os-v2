"""Feed freshness — REQ-NFR-005..014, Gate 4.

Every schema here is a **throwaway name** (`core_fresh_pytest`, `analysis_fresh_pytest`), never
`core`, `analysis` or `public`. `check_freshness` takes its schema names as parameters, so the
real queries run unmodified against disposable schemas — which is exactly what RULE-01's
carve-out permits, with no widening of it and no reliance on the server being temporary
(OQ-52). The transaction is rolled back regardless.
"""
import datetime as dt
import json
import os
import uuid

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools import check_freshness

# Still local-server-only for speed: this builds a spine from real migration DDL, which is
# hundreds of statements and minutes of round trips against a remote instance.
pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds a spine from real migrations; disposable local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_fresh_pytest"
ANALYSIS = "analysis_fresh_pytest"
OPS = "ops_fresh_pytest"

# Deliberately WITHOUT the seed migrations (0016/0019/0022) and without 0051. These tests
# assert exact classification counts, so the registry must contain exactly what each test
# registers and nothing else. Including a seed migration would make every count assertion a
# statement about that migration's contents rather than about the checker.
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
         "0011_ops.sql")


def world(cur):
    cur.execute(f"CREATE SCHEMA {CORE}")
    cur.execute(f"CREATE SCHEMA {OPS}")
    cur.execute(f"CREATE SCHEMA {ANALYSIS}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"""CREATE TABLE {ANALYSIS}.panel (
        day DATE NOT NULL, metric TEXT NOT NULL, value NUMERIC NOT NULL,
        src TEXT NOT NULL, code_version TEXT NOT NULL, PRIMARY KEY (day, metric))""")


def register(cur, key, limit, unit="count", state="total"):
    cur.execute(f"""insert into {CORE}.metric_registry
                     (metric_key, display_name, family, unit, state_class, max_staleness_days)
                   values (%s, %s, 'test', %s, %s, %s)
                   on conflict (metric_key) do update set max_staleness_days = excluded.max_staleness_days""",
                (key, key, unit, state, limit))


def panel_row(cur, key, day, value=1):
    cur.execute(f"""insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
                    values (%s,%s,%s,'test','test') on conflict do nothing""", (day, key, value))


def atom_row(cur, key, day, value=1):
    cap = uuid.uuid4()
    cur.execute(f"""insert into {CORE}.raw_captures
                     (capture_id, captured_at, source, trust_level, payload, processing_status)
                   values (%s, now(), 'shortcut_text', 'trusted', '{{}}'::jsonb, 'enriched')""", (cap,))
    cur.execute(f"""insert into {CORE}.atoms
                     (raw_capture_id, kind, metric_key, occurred_at, time_precision, subject_day,
                      subject_day_rule_version, presence, value_low, value_point, value_high,
                      estimate_method, unit, state_class, trust_level, provenance, code_version)
                   values (%s,'activity_sample',%s,%s,'exact',%s,'v1-2026-08-23','observed',
                           %s,%s,%s,'measured','count','total','trusted','extracted','test')""",
                (cap, key, dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc), day,
                 value, value, value))


def today(cur):
    """The clock the checker itself uses: the current SUBJECT day (04:00 ET), not the
    server's calendar date.

    Building fixtures from `select current_date` was wrong and made three of these tests
    wall-clock dependent: between 00:00 and 08:00 UTC the server's date and the ET subject day
    differ by one, so on a UTC CI runner the fixtures were built a day away from where the
    checker looks. Two tests then reported the wrong elapsed count, and — worse —
    `test_REQ_NFR_005...` stopped distinguishing a working implementation from a broken one,
    because its 4-day-old metric classified as fresh against a 3-day limit.
    """
    from tools.importers.common import current_subject_day
    cur.execute("select now()")
    return current_subject_day(cur.fetchone()[0])


def test_REQ_NFR_005_the_staleness_limit_comes_from_the_registry_not_from_code(sql_connection):
    """The limit is stored configuration. Two metrics with different limits and the same
    elapsed days must classify differently — which is only possible if the limit is read."""
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    four_days_ago = now - dt.timedelta(days=4)
    register(cur, "tight_metric", 3)
    register(cur, "loose_metric", 30)
    panel_row(cur, "tight_metric", four_days_ago)
    panel_row(cur, "loose_metric", four_days_ago)

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert [r["metric"] for r in report["stale"]] == ["tight_metric"]
    assert [r["metric"] for r in report["fresh"]] == ["loose_metric"]
    assert not ok

    limits, _ = check_freshness.registered_limits(cur, CORE)
    assert limits["tight_metric"] == 3 and limits["loose_metric"] == 30
    sql_connection.rollback()


def test_REQ_NFR_006_never_seen_is_distinguished_from_stale(sql_connection):
    """A source that never reported and one that stopped reporting are different facts.

    Collapsing them is what makes a freshness check useless: unbuilt scope would keep the
    check permanently red, and a permanently red check is one nobody reads — which is how a
    real 43-day outage gets missed.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "went_quiet", 3)
    register(cur, "never_reported", 3)
    register(cur, "still_arriving", 3)
    panel_row(cur, "went_quiet", now - dt.timedelta(days=10))
    panel_row(cur, "still_arriving", now)

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert [r["metric"] for r in report["stale"]] == ["went_quiet"]
    assert [r["metric"] for r in report["never_seen"]] == ["never_reported"]
    assert [r["metric"] for r in report["fresh"]] == ["still_arriving"]
    assert report["counts"] == {"fresh": 1, "stale": 1, "misconfigured": 0,
                                "never_seen": 1, "unmonitored": 0, "source_quiet": 0}
    sql_connection.rollback()


def test_REQ_NFR_007_a_quiet_source_fails_the_run_and_reports_its_elapsed_days(sql_connection):
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "quiet", 3)
    last = now - dt.timedelta(days=43)      # the real 2026-07-28 gap length
    panel_row(cur, "quiet", last)

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert not ok, "a metric past its limit must fail the run"
    row = report["stale"][0]
    assert row["metric"] == "quiet"
    assert row["last_day"] == last.isoformat()
    assert row["elapsed_days"] == 43
    assert row["limit_days"] == 3

    # Exactly at the limit is still fresh; one day past it is stale. The boundary is stated
    # by the test so a later change cannot quietly move it (RULE-00).
    panel_row(cur, "edge", now - dt.timedelta(days=3))
    register(cur, "edge", 3)
    report2, _ = check_freshness.check(cur, CORE, ANALYSIS)
    assert "edge" in [r["metric"] for r in report2["fresh"]]
    sql_connection.rollback()


def test_REQ_NFR_008_one_runs_row_per_execution_carries_the_counts(sql_connection):
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "quiet", 3)
    register(cur, "ok_metric", 3)
    panel_row(cur, "quiet", now - dt.timedelta(days=9))
    panel_row(cur, "ok_metric", now)

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    check_freshness.log_run(cur, report, ok, OPS)

    cur.execute(f"select job_name, status, rows_written, detail from {OPS}.runs")
    rows = cur.fetchall()
    assert len(rows) == 1
    job, status, written, detail = rows[0]
    assert job == "check_freshness"
    assert status == "error"           # stale present -> the run is not ok
    assert written == 1                # fresh count
    d = detail if isinstance(detail, dict) else json.loads(detail)
    assert d["counts"] == {"fresh": 1, "stale": 1, "misconfigured": 0,
                           "never_seen": 0, "unmonitored": 0, "source_quiet": 0}
    assert d["stale_metrics"] == ["quiet"]
    sql_connection.rollback()


def test_REQ_NFR_010_a_metric_with_no_limit_is_reported_as_unmonitored(sql_connection):
    """A metric escaping monitoring must be visible, not absent."""
    cur = sql_connection.cursor()
    world(cur)
    cur.execute(f"""insert into {CORE}.metric_registry
                     (metric_key, display_name, family, unit, state_class, max_staleness_days)
                   values ('no_limit','No limit','test','count','total', null)""")
    register(cur, "has_limit", 3)
    panel_row(cur, "has_limit", today(cur))

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert ok
    assert report["unmonitored"] == ["no_limit"]
    assert report["counts"]["unmonitored"] == 1
    assert "no_limit" not in [r["metric"] for r in report["fresh"] + report["stale"]]
    sql_connection.rollback()


def test_REQ_NFR_011_the_report_never_carries_an_observed_value(sql_connection):
    """An operational alert must not become an egress path (RULE-29). The fixture uses a
    value that would be unmistakable if it leaked."""
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "sensitive", 3)
    panel_row(cur, "sensitive", now - dt.timedelta(days=10), value=987654321)

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    blob = json.dumps(report)
    assert "987654321" not in blob
    assert set(report["stale"][0]) == {"metric", "last_day", "elapsed_days", "limit_days", "source"}

    check_freshness.log_run(cur, report, ok, OPS)
    cur.execute(f"select detail::text from {OPS}.runs")
    assert "987654321" not in cur.fetchone()[0]
    sql_connection.rollback()


def test_REQ_NFR_012_a_successful_job_over_an_empty_input_is_not_freshness(sql_connection):
    """The exact 2026-07-28 failure: jobs green, data absent.

    `ops.runs` is filled with successful runs finishing today, and the metric has no
    observation for 43 days. The check must read the observation, not the job.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "starved", 3)
    panel_row(cur, "starved", now - dt.timedelta(days=43))
    for job in ("panel_build", "extract_checkins", "derive_visits", "keepalive_supabase"):
        cur.execute(f"""insert into {OPS}.runs (job_name, finished_at, status, rows_written, detail)
                        values (%s, now(), 'ok', 0, '{{}}'::jsonb)""", (job,))

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert not ok, "green jobs must not make a starved metric look fresh"
    assert report["stale"][0]["elapsed_days"] == 43
    sql_connection.rollback()


def test_REQ_NFR_012_the_later_of_atoms_and_panel_wins(sql_connection):
    """A metric arriving through either store is fresh. Consulting only one would report a
    live feed as quiet."""
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "steps", 3)
    panel_row(cur, "steps", now - dt.timedelta(days=30))    # stale in the panel
    atom_row(cur, "steps", now)                             # but arriving as atoms

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert ok
    fresh = report["fresh"][0]
    assert fresh["metric"] == "steps" and fresh["source"] == "atoms"

    seen = check_freshness.last_observed(cur, {"steps"}, CORE, ANALYSIS)
    assert seen["steps"] == (now, "atoms")
    sql_connection.rollback()


def test_REQ_NFR_009_an_unreachable_database_reports_nothing_as_fresh(monkeypatch):
    """REQ-NFR-009 had no test. An unreachable database must exit non-zero and must not
    report a single metric as fresh — reporting health from a connection that never opened is
    the worst possible failure for a monitoring tool."""
    def refuse():
        raise RuntimeError("connection refused")
    monkeypatch.setattr(check_freshness.db, "connect", refuse)
    assert check_freshness.main(["--no-log"]) == 2


def test_REQ_NFR_012_the_clock_is_the_subject_day_not_the_servers_calendar_date(sql_connection):
    """The comparison clock must turn at 04:00 ET, not at UTC midnight.

    `current_date` on the server is UTC; a stored `subject_day` turns at 04:00 ET. The
    freshness workflow runs at a fixed UTC time, so the two agree in EDT and differ by a full
    day in EST — which would inflate every metric's elapsed count by one all winter and turn
    any metric sitting exactly at its limit permanently red. ADR-0060's own stated design risk
    is that a permanently red check is one nobody reads.
    """
    import datetime as _dt
    from tools.importers.common import current_subject_day

    # 03:00 ET on 9 Jan is 08:00 UTC: the UTC calendar date is the 9th, the subject day is
    # still the 8th, because the subject day turns at 04:00 ET.
    winter = _dt.datetime(2027, 1, 9, 8, 0, tzinfo=_dt.timezone.utc)
    assert winter.date() == _dt.date(2027, 1, 9)
    assert current_subject_day(winter) == _dt.date(2027, 1, 8)

    # 05:00 ET on 9 July is 09:00 UTC: both agree.
    summer = _dt.datetime(2027, 7, 9, 9, 0, tzinfo=_dt.timezone.utc)
    assert current_subject_day(summer) == summer.date() == _dt.date(2027, 7, 9)

    # And the checker uses it: a metric observed on the current subject day is fresh.
    cur = sql_connection.cursor()
    world(cur)
    register(cur, "arriving", 1)
    panel_row(cur, "arriving", current_subject_day())
    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert ok and report["fresh"][0]["elapsed_days"] == 0


def test_REQ_NFR_006_a_missing_panel_is_a_schema_fact_not_an_outage(sql_connection):
    """On an installation without `analysis.panel`, the checker must still run.

    Hardcoding the table meant a fresh install raised, `main()` returned 2, and the workflow
    reported an unreachable-database-class failure for what is a schema-shape difference.
    """
    cur = sql_connection.cursor()
    cur.execute(f"CREATE SCHEMA {CORE}")
    cur.execute(f"CREATE SCHEMA {OPS}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    # No panel schema at all.
    cur.execute("select to_regclass(%s) is null", (f"{ANALYSIS}.panel",))
    assert cur.fetchone()[0]

    register(cur, "atoms_only", 3)
    atom_row(cur, "atoms_only", today(cur))
    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert ok
    assert report["fresh"][0]["source"] == "atoms"
    sql_connection.rollback()


def test_REQ_NFR_013_a_naming_mismatch_is_reported_and_fails_the_run(sql_connection):
    """A registered metric that nothing writes under, while a similar series exists, is a
    metric that is NOT being monitored — and that must fail.

    Filing it under `never_seen` (which does not fail) was the original behaviour and it hid
    the exact feeds this checker was built to watch: the registry says `hrv_sdnn_ms` and the
    panel says `hrv_sdnn`, so 133 rows of HRV that stopped on 2026-07-28 were reported as
    having never reported, in a non-failing category.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "hrv_sdnn_ms", 3)
    panel_row(cur, "hrv_sdnn", now - dt.timedelta(days=40))     # the series, under its own name
    register(cur, "genuinely_absent_metric", 3)                 # nothing resembles this

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert not ok, "a metric that is not being monitored must fail the run"
    assert [r["metric"] for r in report["misconfigured"]] == ["hrv_sdnn_ms"]
    assert report["misconfigured"][0]["candidate_key"] == "hrv_sdnn"
    assert [r["metric"] for r in report["never_seen"]] == ["genuinely_absent_metric"]
    assert report["counts"]["misconfigured"] == 1
    assert report["counts"]["never_seen"] == 1
    assert report["counts"]["stale"] == 0

    check_freshness.log_run(cur, report, ok, OPS)
    cur.execute(f"select status, detail from {OPS}.runs")
    status, detail = cur.fetchone()
    assert status == "error"
    d = detail if isinstance(detail, dict) else json.loads(detail)
    assert d["misconfigured_metrics"] == ["hrv_sdnn_ms"]
    sql_connection.rollback()


def test_REQ_NFR_014_a_similar_key_is_never_treated_as_an_alias(sql_connection):
    """The checker must not silently start reading the candidate series.

    If it did, `hrv_sdnn_ms` would report fresh from `hrv_sdnn`'s rows — asserting that two
    differently named series are the same measurement, which is a claim about data. The whole
    point of the `misconfigured` state is to surface that question, not answer it.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "hrv_sdnn_ms", 3)
    panel_row(cur, "hrv_sdnn", now)          # arriving TODAY under the other name

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert not ok
    # It must NOT be reported fresh by borrowing the other series' recency.
    assert report["fresh"] == []
    assert report["counts"]["fresh"] == 0
    assert [r["metric"] for r in report["misconfigured"]] == ["hrv_sdnn_ms"]
    # And no value from the candidate series leaks into the report (REQ-NFR-011).
    assert "last_day" not in report["misconfigured"][0]
    sql_connection.rollback()


def test_REQ_NFR_013_similar_key_detection_is_conservative():
    """The detector must not invent a relationship between unrelated metrics."""
    from tools.check_freshness import similar_key
    series = {"hrv_sdnn", "rhr", "resp_night", "steps", "away_min", "weather.temp_f"}
    # The mismatch shape this actually takes: a unit suffix on the registry side.
    assert similar_key("hrv_sdnn_ms", series) == "hrv_sdnn"
    # Unrelated names must not be paired up.
    assert similar_key("alcohol_standard_drinks", series) is None
    assert similar_key("checkin_night_mood", series) is None
    assert similar_key("flights_climbed", series) is None
    # And the honest limit: a genuine mismatch a string comparison cannot see stays unseen.
    assert similar_key("resting_hr", series) is None


# ------------------------------------------------- ADR-0140: a dead source behind a live metric

def atom_from_source(cur, key, day, source, value=1):
    """An atom whose capture row names a specific ingress channel."""
    cap = uuid.uuid4()
    cur.execute(f"""insert into {CORE}.raw_captures
                     (capture_id, captured_at, source, trust_level, payload, processing_status)
                   values (%s, now(), %s, 'trusted', '{{}}'::jsonb, 'enriched')""", (cap, source))
    cur.execute(f"""insert into {CORE}.atoms
                     (raw_capture_id, kind, metric_key, occurred_at, time_precision, subject_day,
                      subject_day_rule_version, presence, value_low, value_point, value_high,
                      estimate_method, unit, state_class, trust_level, provenance, code_version)
                   values (%s,'activity_sample',%s,%s,'exact',%s,'v1-2026-08-23','observed',
                           %s,%s,%s,'measured','count','total','trusted','extracted','test')""",
                (cap, key, dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc), day,
                 value, value, value))


def test_ADR_0140_REQ_NFR_012_a_fresh_metric_can_hide_a_dead_capture_source(sql_connection):
    """The metric is fresh, and the channel that used to supply half of it stopped weeks ago.

    This is the bank handover, in miniature and with the names changed. `bank_csv` captured 35
    to 46 charges a month through 2026-05-13 and stopped; `chase_email` took over with roughly
    a third of the transactions and a seventh of the value. `transaction_amount_usd` is FRESH
    throughout, and that statement is true and useless: freshness asks whether anything
    arrived, and the question here is whether the same thing kept arriving.

    Every count above it stays correct — this adds a fact, it does not reclassify the metric.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "spend", 7)
    atom_from_source(cur, "spend", now - dt.timedelta(days=40), "email_receipt")
    atom_from_source(cur, "spend", now - dt.timedelta(days=1), "shortcut_text")

    report, ok = check_freshness.check(cur, CORE, ANALYSIS)

    assert [r["metric"] for r in report["fresh"]] == ["spend"]
    assert report["stale"] == []
    quiet = report["source_quiet"]
    assert len(quiet) == 1, f"expected exactly one quiet channel, got {quiet}"
    assert quiet[0]["metric"] == "spend"
    assert quiet[0]["capture_source"] == "email_receipt"
    assert quiet[0]["elapsed_days"] >= 40
    assert quiet[0]["metric_last_day"] == (now - dt.timedelta(days=1)).isoformat()
    assert report["counts"]["source_quiet"] == 1
    # It reports; it does not fail. Which of two sources to believe is a measurement ruling
    # (RULE-12), and a check that is permanently red is a check nobody reads.
    assert ok is True
    sql_connection.rollback()


def test_ADR_0140_a_channel_still_reporting_is_not_called_quiet(sql_connection):
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "spend", 7)
    atom_from_source(cur, "spend", now - dt.timedelta(days=2), "email_receipt")
    atom_from_source(cur, "spend", now - dt.timedelta(days=1), "shortcut_text")
    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert report["source_quiet"] == []
    assert ok is True
    sql_connection.rollback()


def test_ADR_0140_a_stale_metric_does_not_have_its_channels_enumerated(sql_connection):
    """A metric that is already failing does not also list every channel under it.

    The `stale` row already names the last day and fails the run. Adding one `source_quiet`
    line per channel underneath would be noise on exactly the report that must stay readable.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "spend", 3)
    atom_from_source(cur, "spend", now - dt.timedelta(days=40), "email_receipt")
    atom_from_source(cur, "spend", now - dt.timedelta(days=30), "shortcut_text")
    report, ok = check_freshness.check(cur, CORE, ANALYSIS)
    assert [r["metric"] for r in report["stale"]] == ["spend"]
    assert report["source_quiet"] == []
    assert not ok
    sql_connection.rollback()


def test_ADR_0140_REQ_NFR_011_the_quiet_channel_report_carries_no_observed_value(sql_connection):
    """Metric key, channel name and day counts. Never a number Joe produced.

    The channel is `core.raw_captures.source`, an enum whose every possible value is named in
    migration 0004, so no free text from a capture can reach this report at all.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    register(cur, "spend", 7)
    atom_from_source(cur, "spend", now - dt.timedelta(days=40), "email_receipt", value=987654)
    atom_from_source(cur, "spend", now - dt.timedelta(days=1), "shortcut_text", value=123456)

    report, _ = check_freshness.check(cur, CORE, ANALYSIS)
    text = check_freshness.render(report) + json.dumps(report)
    assert "987654" not in text and "123456" not in text
    assert set(report["source_quiet"][0]) == {
        "metric", "capture_source", "last_day", "elapsed_days", "limit_days", "metric_last_day"}
    sql_connection.rollback()


# ------------------------------------------------- ADR-0140: the local schedule's own silence

def import_run(cur, job, finished):
    cur.execute(f"""insert into {OPS}.runs (job_name, started_at, finished_at, status,
                                            rows_written, detail)
                    values (%s, %s, %s, 'ok', 0, '{{}}'::jsonb)""", (job, finished, finished))


def test_ADR_0140_the_import_cadence_is_read_from_the_schedule_declaration():
    """Not a number written into the checker. `ops/capture_schedule.py` declares when the
    import runs, so that file is where the cadence is read from; a constant here would be a
    second statement of it, free to disagree with the first."""
    assert check_freshness.declared_import_cadence_days() == 1
    assert check_freshness.declared_import_cadence_days(
        {"StartCalendarInterval": {"Weekday": 1, "Hour": 2}}) == 7
    assert check_freshness.declared_import_cadence_days(
        {"StartCalendarInterval": {"Day": 1, "Hour": 2}}) == 31


def test_ADR_0140_a_local_import_schedule_that_never_ran_does_not_fail(sql_connection):
    """Never installed is unbuilt scope, exactly like `never_seen`.

    ADR-0094 keeps activation a separate human act, so between shipping this check and Joe
    bootstrapping the agent there is a window in which no row can exist. Failing on it would
    leave the freshness workflow red for that whole window, which is how a red check becomes
    an ignored one.
    """
    cur = sql_connection.cursor()
    world(cur)
    report, ok = check_freshness.check(cur, CORE, ANALYSIS, OPS)
    assert report["import_schedule"]["state"] == "not_installed"
    assert ok is True
    assert "NOT INSTALLED" in check_freshness.render(report)
    sql_connection.rollback()


def test_ADR_0140_REQ_NFR_012_a_local_import_schedule_that_went_silent_fails(sql_connection):
    """The drop folder is on the Mac. A GitHub runner cannot see the laptop being shut.

    Without this, a week of a closed laptop looks like a dozen metrics ageing for a dozen
    unrelated reasons, and the one sentence that explains all of them is absent from the only
    report that runs every day.
    """
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    import_run(cur, "capture_schedule",
               dt.datetime.combine(now - dt.timedelta(days=9), dt.time(6),
                                   tzinfo=dt.timezone.utc))
    report, ok = check_freshness.check(cur, CORE, ANALYSIS, OPS)
    assert report["import_schedule"]["state"] == "stale"
    assert report["import_schedule"]["elapsed_days"] >= 9
    assert ok is False, "a silent local import schedule must fail the run"
    assert "LOCAL IMPORT SCHEDULE STALE" in check_freshness.render(report)
    sql_connection.rollback()


def test_ADR_0140_the_importers_own_row_also_proves_the_schedule_fired(sql_connection):
    """`import_drop` writes the row when its transaction commits and `capture_schedule` writes
    one when it does not. Either is evidence the schedule fired — and neither is evidence that
    anything arrived, which every other line of this report is for."""
    cur = sql_connection.cursor()
    world(cur)
    now = today(cur)
    import_run(cur, "import_drop",
               dt.datetime.combine(now, dt.time(6), tzinfo=dt.timezone.utc))
    report, ok = check_freshness.check(cur, CORE, ANALYSIS, OPS)
    assert report["import_schedule"]["state"] == "fresh"
    assert ok is True
    sql_connection.rollback()


def test_ADR_0140_a_missing_ops_schema_is_reported_as_unknown_not_as_healthy(sql_connection):
    """No runs table means the question cannot be answered, and `unknown` says so."""
    cur = sql_connection.cursor()
    world(cur)
    report, ok = check_freshness.check(cur, CORE, ANALYSIS, "ops_absent_pytest")
    assert report["import_schedule"]["state"] == "unknown"
    assert ok is True
    sql_connection.rollback()
