"""B13 — the panel's attention precedence flip (ADR-0058).

`panel.build` now takes its schema names as parameters, so these run against **throwaway
names** — never `core`, `analysis` or `public`. That is exactly what RULE-01's disposable-schema
carve-out permits, with no widening of it (OQ-52); the previous version created schemas with the
production names and leaned on the server being temporary, which is a weaker guarantee resting
on a docstring rather than on the rule.

Still local-server-only for speed: this builds a spine from real migration DDL.
"""
import datetime as dt
import os

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools.engines import panel

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds a spine from real migrations; disposable local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_panel_pytest"
ANALYSIS = "analysis_panel_pytest"
PUBLIC = "public_panel_pytest"
CONFIG = "config_panel_pytest"
OPS = "ops_panel_pytest"
SCHEMAS = {"core": CORE, "analysis": ANALYSIS, "public": PUBLIC, "config": CONFIG, "ops": OPS}

SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
         "0011_ops.sql", "0016_alcohol_metric_seed.sql", "0019_checkin_metric_seed.sql",
         "0022_workout_health_seed.sql", "0051_file_import.sql")


def build_panel_world(cur):
    """The narrowest world `panel.build` can run in, with the real spine DDL for atoms."""
    for schema in (CORE, OPS, ANALYSIS, CONFIG, PUBLIC):
        cur.execute(f"CREATE SCHEMA {schema}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"""CREATE TABLE {ANALYSIS}.panel (
        day DATE NOT NULL, metric TEXT NOT NULL, value NUMERIC NOT NULL,
        src TEXT NOT NULL, code_version TEXT NOT NULL,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (day, metric))""")
    cur.execute(f"""CREATE TABLE {PUBLIC}.signals (
        ts TIMESTAMPTZ NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value NUMERIC)""")
    cur.execute(f"""CREATE TABLE {ANALYSIS}.legacy_daily (
        day DATE PRIMARY KEY, hrv NUMERIC, rhr NUMERIC, resp NUMERIC, kcal NUMERIC,
        exmin NUMERIC, steps NUMERIC, asleep NUMERIC, inbed NUMERIC, deep NUMERIC,
        rem NUMERIC, onset NUMERIC, wake_min NUMERIC, core_min NUMERIC)""")
    cur.execute(f"""CREATE TABLE {ANALYSIS}.visits_public (
        subject_day DATE, dwell_min NUMERIC, is_home BOOLEAN, place_id TEXT)""")
    cur.execute(f"CREATE FUNCTION {CONFIG}.ensure_places_metrics() RETURNS void "
                "LANGUAGE sql AS $$ SELECT $$")


def _capture(cur, cap_id):
    cur.execute(f"""insert into {CORE}.raw_captures
                     (capture_id, captured_at, source, trust_level, payload, processing_status)
                    values (%s, now(), 'file_import', 'trusted', '{{}}'::jsonb, 'enriched')""",
                (cap_id,))


def _event_atom(cur, cap_id, kind, day, when):
    cur.execute(f"""insert into {CORE}.atoms
                     (raw_capture_id, kind, occurred_at, time_precision, subject_day,
                      subject_day_rule_version, presence, trust_level, provenance, code_version)
                   values (%s, %s, %s, 'exact', %s, 'v1-2026-08-23', 'observed',
                           'trusted', 'extracted', 'test')""",
                (cap_id, kind, when, day))


def test_ADR_0058_panel_prefers_atoms_over_signals_for_attention_metrics(sql_connection):
    """Atoms FILL `chrome_events` / `yt_events` where signals never covered the day, and
    never overwrite a day signals already has.

    The build order asked for atoms to win these two metrics outright. Review showed that is
    unsafe and it was not done. Two reasons, both of which only bite on the overlap:

    * The two sources use different day boundaries — atoms carry `subject_day` (04:00 ET),
      the signals passes group by `ts::date` (the server's UTC date). A visit at 22:00 ET is
      one day under one rule and the previous day under the other, so overwriting would move
      every late-evening visit a day earlier across the overlap: a silent step in the middle
      of a series, which is exactly what ADR-0058 refuses to accept for the `screen_*` metrics.
    * Chrome expires local history at ~90 days, so a Takeout archive would replace complete
      historical values with partial ones.

    Filling gets the live data in without rewriting history, which is what this asserts.
    """
    import uuid
    cur = sql_connection.cursor()
    build_panel_world(cur)

    covered = dt.date(2026, 7, 20)      # signals has this day
    uncovered = dt.date(2026, 9, 8)     # signals stopped before this day

    for source, metric, value in (("attention", "chrome_events", 111),
                                  ("attention", "yt_events", 222),
                                  ("apple_sleep", "asleep_min", 400)):
        cur.execute(f"insert into {PUBLIC}.signals (ts, source, metric, value) values (%s,%s,%s,%s)",
                    (dt.datetime.combine(covered, dt.time(12, 0), tzinfo=dt.timezone.utc),
                     source, metric, value))

    # Atoms exist for BOTH days: three visits and two plays on each.
    cap = uuid.uuid4()
    _capture(cur, cap)
    for day in (covered, uncovered):
        for i in range(3):
            _event_atom(cur, cap, "web_visit", day,
                        dt.datetime.combine(day, dt.time(10, i), tzinfo=dt.timezone.utc))
        for i in range(2):
            _event_atom(cur, cap, "media_play", day,
                        dt.datetime.combine(day, dt.time(11, i), tzinfo=dt.timezone.utc))

    panel.build(cur, SCHEMAS)

    def cell(d, metric):
        cur.execute(f"select value, src from {ANALYSIS}.panel where day=%s and metric=%s", (d, metric))
        return cur.fetchone()

    # The day signals covers keeps the signals value, even though atoms exist for it.
    assert cell(covered, "chrome_events") == [111, "signals:attention"]
    assert cell(covered, "yt_events") == [222, "signals:attention"]
    # The day signals never covered is filled from atoms — this is the new data arriving.
    assert cell(uncovered, "chrome_events") == [3, "atoms:takeout"]
    assert cell(uncovered, "yt_events") == [2, "atoms:takeout"]
    # Every other metric is untouched by any of this.
    assert cell(covered, "sleep_asleep_min") == [400, "signals:apple_sleep"]
    assert cell(uncovered, "sleep_asleep_min") is None, "absent means absent (REQ-INF-505)"
    sql_connection.rollback()


def test_ADR_0058_session_level_screen_metrics_are_not_re_derived_from_atoms(sql_connection):
    """The four `screen_*` metrics must keep coming from signals.

    Their definitions — the gap that ends a session, the length that makes a binge — live in
    the old stack and are not in this repository. Re-deriving them here with invented
    thresholds would produce a series that steps silently at the changeover, so they are
    deliberately left alone and allowed to go visibly stale (OQ-48). This test is what stops
    a later change from quietly adding them.
    """
    import uuid
    cur = sql_connection.cursor()
    build_panel_world(cur)
    day = dt.date(2026, 9, 8)
    for metric in ("active_hours", "binge_minutes", "max_binge_len", "session_count"):
        cur.execute(f"insert into {PUBLIC}.signals (ts, source, metric, value) values (%s,'attention',%s,%s)",
                    (dt.datetime.combine(day, dt.time(12, 0), tzinfo=dt.timezone.utc), metric, 7))
    cap = uuid.uuid4()
    _capture(cur, cap)
    for i in range(50):
        _event_atom(cur, cap, "web_visit", day,
                    dt.datetime.combine(day, dt.time(10, i % 60), tzinfo=dt.timezone.utc))

    panel.build(cur, SCHEMAS)

    for canon in ("screen_active_hours", "screen_binge_min", "screen_max_binge", "screen_sessions"):
        cur.execute(f"select value, src from {ANALYSIS}.panel where day=%s and metric=%s", (day, canon))
        row = cur.fetchone()
        assert row == [7, "signals:attention"], f"{canon} must still come from signals"
    assert set(panel.ATOM_EVENT_COUNTS) == {"chrome_events", "yt_events"}
    sql_connection.rollback()
