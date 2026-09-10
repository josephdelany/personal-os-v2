"""The analysis layer reads core.atoms (REQ-INF-108, REQ-ASK-021, RULE-06/08/10/12/13).

Three acceptance areas Joe named: device reconciliation, sleep aggregation, and
historical-cutoff behaviour. Every fixture row lives in a disposable schema (ADR-0022).
"""
import datetime as dt
import os
import re
import uuid

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements

S = "pan_core_pytest"
AS_OF = dt.date(2026, 9, 8)


def rebind(sql):
    return re.sub(r"\b(config|analysis)\.", r"\1_pytest.", sql.replace("__CORE__", S))


@pytest.fixture
def cur(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (S, "config_pytest", "analysis_pytest", "public_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    # 0056 replaces _ask_resolve_metric, which reads the domain tables and pg_trgm.
    c.execute("SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname='pg_trgm'")
    found = c.fetchone()
    if found:
        ext = found[0]
    else:
        c.execute("CREATE SCHEMA IF NOT EXISTS extensions_pytest")
        c.execute("CREATE EXTENSION pg_trgm WITH SCHEMA extensions_pytest")
        ext = "extensions_pytest"
    for filename in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
                     "0051_file_import.sql", "0034_domain_config.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            c.execute(rebind(statement).replace("extensions.", f'"{ext}".'))
    c._ext = ext
    # The legacy panel, to the live shape.
    c.execute("""CREATE TABLE analysis_pytest.panel (
        day DATE NOT NULL, metric TEXT NOT NULL, value NUMERIC, src TEXT,
        code_version TEXT, computed_at TIMESTAMPTZ DEFAULT now())""")
    for key, unit, state in (("steps", "count", "total"),
                             ("heart_rate_bpm", "bpm", "measurement"),
                             ("sleep_core_min", "min", "total"),
                             ("sleep_deep_min", "min", "total"),
                             ("sleep_rem_min", "min", "total"),
                             ("sleep_asleep_min", "min", "total"),
                             ("sleep_awake_min", "min", "total"),
                             ("sleep_minutes", "min", "total")):
        c.execute(f"""INSERT INTO {S}.metric_registry
            (metric_key, display_name, family, unit, state_class)
            VALUES (%s, %s, 'health', %s, %s)
            ON CONFLICT (metric_key) DO NOTHING""", (key, key, unit, state))
    return c


def _apply_0056(c):
    for statement in split_statements((ROOT / "migrations" / "0056_atom_panel.sql").read_text()):
        c.execute(rebind(statement)
                  .replace("extensions.", f'"{c._ext}".')
                  .replace("public._ask_resolve_metric", "public_pytest._ask_resolve_metric"))


def atom(c, metric, day, value, *, device="Apple Watch", recorded=None,
         interval=None, supersedes=None, presence="observed"):
    cid = uuid.uuid4()
    c.execute(f"""INSERT INTO {S}.raw_captures (capture_id, source, captured_at, payload, trust_level)
                  VALUES (%s,'file_import', %s, '{{}}'::jsonb, 'trusted')""",
              (cid, dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)))
    aid = uuid.uuid4()
    c.execute(f"""INSERT INTO {S}.atoms
        (id, raw_capture_id, kind, metric_key, occurred_at, valid_interval, subject_day,
         subject_day_rule_version, recorded_at, presence, value_low, value_point, value_high,
         estimate_method, unit, state_class, value_type, trust_level, provenance,
         evidence_span, code_version, supersedes)
        VALUES (%s,%s,'measurement',%s,%s,%s,%s,'v1',%s,%s,%s,%s,%s,'measured','count',
                'total','numeric','trusted','extracted',%s,'test',%s)""",
        (aid, cid, metric, dt.datetime.combine(day, dt.time(12), dt.timezone.utc), interval,
         day, recorded or dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc), presence,
         value, value, value, f"apple_health:X;source=Joseph's {device}", supersedes))
    return aid


def panel(c, as_of=AS_OF, known_at=None):
    """`as_of` is the subject-day cutoff; `known_at` is the knowledge-time cutoff. Two clocks,
    two parameters — the one-argument form means "everything known now"."""
    if known_at is None:
        c.execute("SELECT day, metric, value FROM analysis_pytest.f_daily_panel(%s) ORDER BY 1,2",
                  (as_of,))
    else:
        c.execute("SELECT day, metric, value FROM analysis_pytest.f_daily_panel(%s,%s) ORDER BY 1,2",
                  (as_of, known_at))
    return {(r[0], r[1]): float(r[2]) for r in c.fetchall()}


# ---------------------------------------------------------------- device reconciliation

def test_RULE_12_the_two_devices_are_never_summed(cur):
    """Measured on real data: each device records the WHOLE day, so summing doubles it.
    Watch alone was 1.01x a one-device day, iPhone 0.97x, their sum 1.98x."""
    day = dt.date(2026, 9, 1)
    for v in (1000, 1200):
        atom(cur, "steps", day, v, device="Apple Watch")
    for v in (900, 1100, 1000):
        atom(cur, "steps", day, v, device="iPhone (8473)")
    _apply_0056(cur)
    assert panel(cur)[(day, "steps")] == 2200, "the Watch's own total, not 5200"


def test_RULE_12_the_iphone_is_used_when_the_watch_has_no_record_that_day(cur):
    """Precedence is per DAY, not per metric: after the Watch went quiet on 2026-08-21 the
    phone is the only instrument, and dropping it would erase real days."""
    watch_day, phone_day = dt.date(2026, 9, 1), dt.date(2026, 9, 2)
    atom(cur, "steps", watch_day, 1000, device="Apple Watch")
    atom(cur, "steps", phone_day, 800, device="iPhone (8473)")
    _apply_0056(cur)
    p = panel(cur)
    assert p[(watch_day, "steps")] == 1000
    assert p[(phone_day, "steps")] == 800, "a phone-only day must not vanish"


def test_REQ_ASK_021_the_provenance_names_the_device_and_that_a_second_was_dropped(cur):
    day = dt.date(2026, 9, 1)
    atom(cur, "steps", day, 1000, device="Apple Watch")
    atom(cur, "steps", day, 900, device="iPhone (8473)")
    _apply_0056(cur)
    cur.execute("""SELECT lane, device, n_atoms, n_devices, method, value
                     FROM analysis_pytest.f_panel_provenance('steps', %s, %s, %s)""",
                (day, day, AS_OF))
    lane, device, n_atoms, n_devices, method, value = cur.fetchone()
    assert (lane, device, n_atoms, n_devices, method) == ("atoms", "Watch", 1, 2, "sum")
    assert float(value) == 1000


def test_RULE_13_a_measurement_takes_the_median_and_a_total_takes_the_sum(cur):
    """The method comes from config.panel_aggregation, seeded from the registry's state_class,
    so the panel and `describe`'s sentence cannot mean different things."""
    day = dt.date(2026, 9, 1)
    for v in (50, 60, 200):
        atom(cur, "heart_rate_bpm", day, v)
    for v in (100, 200):
        atom(cur, "steps", day, v)
    _apply_0056(cur)
    p = panel(cur)
    assert p[(day, "heart_rate_bpm")] == 60, "a reading has no daily total"
    assert p[(day, "steps")] == 300


# ---------------------------------------------------------------- sleep aggregation

def _seg(day, h0, m0, h1, m1):
    base = dt.datetime.combine(day, dt.time(0), dt.timezone.utc)
    return (f"[{base + dt.timedelta(hours=h0, minutes=m0)},"
            f"{base + dt.timedelta(hours=h1, minutes=m1)})")


def test_REQ_INF_108_sleep_is_core_deep_rem_and_unspecified_excluding_awake(cur):
    """Joe's ruling. 60 core + 30 deep + 30 rem + 20 unspecified = 140; the 45 awake minutes
    are time in bed, not sleep."""
    day = dt.date(2026, 9, 1)
    atom(cur, "sleep_core_min",   day, 60, interval=_seg(day, 1, 0, 2, 0))
    atom(cur, "sleep_deep_min",   day, 30, interval=_seg(day, 2, 0, 2, 30))
    atom(cur, "sleep_rem_min",    day, 30, interval=_seg(day, 2, 30, 3, 0))
    atom(cur, "sleep_asleep_min", day, 20, interval=_seg(day, 3, 0, 3, 20))
    atom(cur, "sleep_awake_min",  day, 45, interval=_seg(day, 3, 20, 4, 5))
    _apply_0056(cur)
    assert panel(cur)[(day, "sleep_minutes")] == 140


def test_RULE_08_overlapping_sleep_segments_are_counted_once(cur):
    """The stored data happens not to overlap — 0 overlapping pairs, checked. "Happens not to"
    is not a guarantee, and a duplicated segment from a future import must not inflate a night
    by its own length. The union of ranges is measured, not the sum of durations."""
    day = dt.date(2026, 9, 1)
    atom(cur, "sleep_core_min", day, 60, interval=_seg(day, 1, 0, 2, 0))
    atom(cur, "sleep_deep_min", day, 60, interval=_seg(day, 1, 30, 2, 30))   # overlaps by 30
    _apply_0056(cur)
    assert panel(cur)[(day, "sleep_minutes")] == 90, "naive summing would give 120"


def test_RULE_12_both_the_whole_and_its_parts_are_answerable(cur):
    """A component is served in its own right — "how much deep sleep did I get" must have
    something to answer from. Withholding components to prevent a double-count nothing
    performs would trade a concrete capability for a hypothetical risk."""
    day = dt.date(2026, 9, 1)
    atom(cur, "sleep_core_min", day, 60, interval=_seg(day, 1, 0, 2, 0))
    atom(cur, "sleep_deep_min", day, 30, interval=_seg(day, 2, 0, 2, 30))
    _apply_0056(cur)
    p = panel(cur)
    assert p[(day, "sleep_minutes")] == 90, "the whole"
    assert p[(day, "sleep_core_min")] == 60, "the part, answerable on its own"
    assert p[(day, "sleep_deep_min")] == 30


def test_RULE_12_a_question_about_the_whole_resolves_to_the_whole(cur):
    """The guard is at NAMING, and this exercises the real production resolver.

    "sleep" is a substring of "Asleep (unspecified)" and trigram-scores a perfect 1.0 against
    it, so before this "how is my sleep" answered from the 3-day unstaged fragment instead of
    sleep duration. "deep sleep" carries a word that distinguishes the part, so it must still
    reach the part — demoting parts on similarity alone sent it to the whole."""
    _apply_0056(cur)
    for text, expected in (("sleep", "sleep_minutes"),
                           ("deep sleep", "sleep_deep_min"),
                           ("rem sleep", "sleep_rem_min"),
                           ("core sleep", "sleep_core_min"),
                           ("time in bed", "sleep_inbed_min")):
        cur.execute("SELECT metric FROM public_pytest._ask_resolve_metric(%s)", (text,))
        got = cur.fetchone()[0]
        assert got == expected, f"{text!r} resolved to {got}, expected {expected}"


# ---------------------------------------------------------------- historical cutoff

def test_INV_4_a_replay_uses_only_what_was_known_at_the_time(cur):
    """core.atoms has a real recorded_at, so unlike analysis.panel this lane is genuinely
    bitemporal: importing history next month does not change the answer to a question asked
    today. This is the half of OQ-45 the atom lane can close."""
    day = dt.date(2026, 9, 1)
    atom(cur, "steps", day, 1000, recorded=dt.datetime(2026, 9, 2, tzinfo=dt.timezone.utc))
    atom(cur, "steps", day, 5000, recorded=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc))
    _apply_0056(cur)
    replay = panel(cur, dt.date(2026, 9, 5), dt.datetime(2026, 9, 5, tzinfo=dt.timezone.utc))
    assert replay[(day, "steps")] == 1000, "the replay used knowledge it did not have"
    later = panel(cur, dt.date(2026, 10, 5), dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc))
    assert later[(day, "steps")] == 6000


def test_REQ_INF_108_the_two_cutoffs_are_separate_clocks(cur):
    """The error this test exists to prevent: passing as_of to BOTH cutoffs. Ask defaults
    as_of to YESTERDAY because today is incomplete, so a single conflated cutoff made every
    atom imported TODAY invisible to every question — bitemporally correct and useless. A live
    question wants days up to yesterday using everything known now."""
    day = dt.date(2026, 9, 1)
    atom(cur, "steps", day, 1000,
         recorded=dt.datetime(2026, 9, 8, 20, tzinfo=dt.timezone.utc))   # imported "today"
    _apply_0056(cur)
    assert panel(cur, dt.date(2026, 9, 7))[(day, "steps")] == 1000, (
        "an atom imported after the subject-day cutoff must still be USED; only a replay "
        "pinned to an earlier knowledge time may exclude it")
    pinned = panel(cur, dt.date(2026, 9, 7), dt.datetime(2026, 9, 7, tzinfo=dt.timezone.utc))
    assert (day, "steps") not in pinned, "the replay clock had no effect"


def test_RULE_04_a_subject_day_after_the_as_of_is_excluded(cur):
    atom(cur, "steps", dt.date(2026, 9, 1), 1000)
    atom(cur, "steps", dt.date(2026, 9, 7), 2000)
    _apply_0056(cur)
    p = panel(cur, dt.date(2026, 9, 3))
    assert (dt.date(2026, 9, 1), "steps") in p
    assert (dt.date(2026, 9, 7), "steps") not in p


def test_RULE_10_a_correction_supersedes_and_the_replay_still_shows_the_old_value(cur):
    """Append-only. The correction wins today; a question asked before it was made still
    replays to the value that was current then."""
    day = dt.date(2026, 9, 1)
    first = atom(cur, "steps", day, 1000,
                 recorded=dt.datetime(2026, 9, 2, tzinfo=dt.timezone.utc))
    atom(cur, "steps", day, 1500, supersedes=first,
         recorded=dt.datetime(2026, 9, 6, tzinfo=dt.timezone.utc))
    _apply_0056(cur)
    assert panel(cur, dt.date(2026, 9, 8))[(day, "steps")] == 1500, "correction not applied"
    before = panel(cur, dt.date(2026, 9, 4), dt.datetime(2026, 9, 4, tzinfo=dt.timezone.utc))
    assert before[(day, "steps")] == 1000, "history was rewritten"


# ---------------------------------------------------------------- lane separation

def test_RULE_12_a_legacy_row_never_backfills_a_metric_the_atom_lane_owns(cur):
    """Measured before this was built: legacy sleep_deep_min is in HOURS despite the _min
    suffix (1.3 vs 78.2) and legacy sleep_asleep_min means TOTAL sleep (411 vs 122). Blending
    them would be wrong by a factor of sixty, silently, under a name asserting the unit."""
    day, older = dt.date(2026, 9, 1), dt.date(2025, 1, 1)
    atom(cur, "steps", day, 1000)
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES (%s,'steps',9999,'signals:health_history')", (older,))
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES (%s,'weight_lb',180,'legacy_daily')", (older,))
    _apply_0056(cur)
    p = panel(cur)
    assert (older, "steps") not in p, "a legacy row backfilled an atom-owned metric"
    assert p[(older, "weight_lb")] == 180, "a metric the atom lane does not own must survive"


def test_RULE_06_partial_coverage_is_disclosed_and_never_imputed(cur):
    day = dt.date(2026, 9, 1)
    atom(cur, "steps", day, 1000)
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES ('2025-01-01','steps',9999,'legacy')")
    _apply_0056(cur)
    cur.execute("""SELECT first_day, days_with_data, legacy_rows_exist_and_are_excluded
                     FROM analysis_pytest.v_atom_lane_coverage WHERE metric = 'steps'""")
    first_day, days, excluded = cur.fetchone()
    assert first_day == day and days == 1
    assert excluded is True, "the excluded legacy history must be visible, not hidden"
