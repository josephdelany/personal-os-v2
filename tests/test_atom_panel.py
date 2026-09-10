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


def panel_rows(c, as_of=AS_OF, known_at=None):
    """Every row, as a list. `panel()` collapses to a dict for convenience and a dict SILENTLY
    DISCARDS A DUPLICATE KEY — which is why two `sleep_minutes` rows for one day could not
    fail any test in this file. Assertions about duplication must use this."""
    if known_at is None:
        c.execute("SELECT day, metric, value FROM analysis_pytest.f_daily_panel(%s) ORDER BY 1,2",
                  (as_of,))
    else:
        c.execute("SELECT day, metric, value FROM analysis_pytest.f_daily_panel(%s,%s) ORDER BY 1,2",
                  (as_of, known_at))
    return [(r[0], r[1], None if r[2] is None else float(r[2])) for r in c.fetchall()]


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


# ---------------------------------------------------------------- domain readiness (0060)

def _apply_0060(c):
    for statement in split_statements((ROOT / "migrations" / "0060_domain_status.sql").read_text()):
        c.execute(rebind(statement))


def _domain(c, key, hero, display=None):
    c.execute("""INSERT INTO config_pytest.domains
        (domain_key, pillar, display_name, hero_metric, sort_order, enabled, capture_action)
        VALUES (%s,'body',%s,%s,1,true,'do the thing')
        ON CONFLICT (domain_key) DO UPDATE SET hero_metric = EXCLUDED.hero_metric""",
        (key, display or key, hero))


def _status(c, as_of=AS_OF):
    c.execute("SELECT domain_key, hero_metric, resolution, days_with_data, band_position "
              "FROM analysis_pytest.f_domain_status(%s)", (as_of,))
    return {r[0]: (r[1], r[2], r[3], r[4]) for r in c.fetchall()}


@pytest.fixture
def domains(cur):
    # config.domains comes from 0034, already applied by the base fixture. Its seeded rows
    # would drown these cases, so the table is emptied rather than recreated.
    cur.execute("DELETE FROM config_pytest.domain_metrics")
    cur.execute("DELETE FROM config_pytest.domains")
    # `computed_at` matters: it is the baseline's knowledge time, and the stub omitted it, so
    # no test in this file could exercise the bound f_domain_status is supposed to apply.
    # The reviewer found that gap by reading the fixture, not by running it.
    cur.execute("""CREATE TABLE IF NOT EXISTS analysis_pytest.baselines (
        day DATE, metric TEXT, value NUMERIC, band_lo NUMERIC, band_hi NUMERIC,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    return cur


def test_RULE_18_a_rename_is_not_reported_as_an_absence_of_data(domains):
    """The OQ-60 case, and the reason this function exists. `hrv_sdnn` has rows; the registry
    knows `hrv_sdnn_ms`. "No data" and "no data UNDER THIS NAME" are different statements and
    only one is true — printing the first would say Joe has no recovery data while 1,333
    observations sit in core.atoms under the other spelling."""
    cur = domains
    _domain(cur, "recovery", "hrv_sdnn")
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES (%s,'hrv_sdnn',42,'legacy')", (AS_OF - dt.timedelta(days=1),))
    _apply_0056(cur); _apply_0060(cur)
    hero, resolution, days, _ = _status(cur)["recovery"]
    assert resolution == "unregistered_but_has_data", resolution
    assert days == 1, "the rows must still be counted; they exist"


def test_RULE_06_an_unbuilt_measure_is_distinguished_from_a_renamed_one(domains):
    """`meals_logged` has no rows anywhere and no registry entry: unbuilt scope, not a rename.
    Collapsing the two would send someone hunting for data that was never captured."""
    cur = domains
    _domain(cur, "food", "meals_logged")
    _apply_0056(cur); _apply_0060(cur)
    assert _status(cur)["food"][1] == "unregistered_and_unbuilt"


def test_RULE_07_a_registered_metric_with_no_observation_is_its_own_state(domains):
    """Registered and never captured is neither a rename nor unbuilt scope: the definition
    exists and the capture does not, which points at a different fix."""
    cur = domains
    _domain(cur, "body", "weight_lb")
    cur.execute("""INSERT INTO pan_core_pytest.metric_registry
        (metric_key, display_name, family, unit, state_class)
        VALUES ('weight_lb','Weight','body','lb','measurement')
        ON CONFLICT (metric_key) DO NOTHING""")
    _apply_0056(cur); _apply_0060(cur)
    assert _status(cur)["body"][1] == "registered_no_observations"


def test_RULE_07_a_domain_with_no_hero_metric_says_so_rather_than_looking_empty(domains):
    cur = domains
    _domain(cur, "calendar", None)
    _apply_0056(cur); _apply_0060(cur)
    assert _status(cur)["calendar"][1] == "no_hero_metric"


def test_RULE_07_no_band_is_not_reported_as_inside_one(domains):
    """A missing band is unknown position, not `in_band`. Defaulting to inside would make an
    unmonitored metric look reassuring."""
    cur = domains
    _domain(cur, "activity", "steps")
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES (%s,'steps',5000,'legacy')", (AS_OF - dt.timedelta(days=1),))
    _apply_0056(cur); _apply_0060(cur)
    assert _status(cur)["activity"][3] is None, "a missing band must not read as in_band"


def test_RULE_12_the_function_never_maps_a_hero_metric_onto_a_similar_name(domains):
    """A string-similarity search proposes `sleep_awake_min` for `away_min` — time AWAKE IN BED
    offered as time AWAY FROM HOME. The tooling cannot tell a rename from a coincidence, so
    this function resolves by EXACT name only."""
    cur = domains
    _domain(cur, "places", "away_min")
    cur.execute("""INSERT INTO pan_core_pytest.metric_registry
        (metric_key, display_name, family, unit, state_class)
        VALUES ('sleep_awake_min','Awake','sleep','min','total')
        ON CONFLICT (metric_key) DO NOTHING""")
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES (%s,'sleep_awake_min',45,'legacy')", (AS_OF - dt.timedelta(days=1),))
    _apply_0056(cur); _apply_0060(cur)
    hero, resolution, days, _ = _status(cur)["places"]
    assert resolution == "unregistered_and_unbuilt", resolution
    assert days == 0, "a similarly-named metric's rows must not be borrowed"


# ---------------------------------------------------------------- review findings 1, 2, 9

def test_RULE_12_a_composed_metric_is_served_by_exactly_one_lane(cur):
    """Review finding 1. `sleep_minutes` is composed here AND written directly by
    extract_checkins.py from Joe's self-reported sleep, so both arms of f_daily_panel emitted
    it — two rows for one metric on one day. Coverage then counts two, can exceed 1.0, and
    sails past the 0.60 INSUFFICIENT floor on a doubled denominator. The median also mixed a
    self-report with a device interval union in one distribution, which is INV-5.

    Asserted on the ROW LIST: a dict comprehension discards the duplicate key, which is exactly
    why this defect could not fail a test in this file before."""
    day = dt.date(2026, 9, 1)
    atom(cur, "sleep_core_min", day, 90, interval=_seg(day, 1, 0, 2, 30))
    atom(cur, "sleep_minutes", day, 420)          # a self-reported night, no interval
    _apply_0056(cur)
    rows = [r for r in panel_rows(cur) if r[1] == "sleep_minutes"]
    assert len(rows) == 1, f"one metric, one lane, one row per day: {rows}"
    assert rows[0][2] == 90.0, "the composed lane owns it; the self-report is not merged in"


def test_RULE_06_an_unbounded_sleep_interval_does_not_become_a_night_with_no_duration(cur):
    """Review finding 2. `valid_interval IS NOT NULL` passes a range with an open end; upper()
    is then NULL and the whole night's sum is NULL — and the row was still EMITTED, counted
    toward coverage and toward n. A night with no computable duration reported as a night WITH
    data is worse than a missing night. HealthKit emits an open end when an export truncates
    mid-session."""
    day = dt.date(2026, 9, 1)
    cur.execute(f"""INSERT INTO {S}.raw_captures (capture_id, source, captured_at, payload,
                    trust_level) VALUES (gen_random_uuid(),'file_import', now(), '{{}}','trusted')
                    RETURNING capture_id""")
    cap = cur.fetchone()[0]
    cur.execute(f"""INSERT INTO {S}.atoms (raw_capture_id, kind, metric_key, valid_interval,
        subject_day, subject_day_rule_version, presence, value_low, value_point, value_high,
        estimate_method, unit, state_class, value_type, trust_level, provenance, evidence_span,
        code_version)
        VALUES (%s,'sleep','sleep_core_min', tstzrange(%s, NULL, '[)'), %s,'v1','observed',
                1,1,1,'measured','min','total','numeric','trusted','extracted',
                'apple_health:X;source=Joseph''s Apple Watch','t')""",
        (cap, dt.datetime.combine(day, dt.time(3), dt.timezone.utc), day))
    _apply_0056(cur)
    rows = [r for r in panel_rows(cur) if r[1] == "sleep_minutes"]
    assert rows == [], f"an incomputable night must be absent, not present-and-NULL: {rows}"


def test_RULE_12_the_composed_metric_obeys_device_precedence_too(cur):
    """Review finding 9. Precedence was applied to the components and skipped for the
    composition, so range_agg unioned a Watch segment and a phone segment into one night and
    labelled the total with min(device) — 150 minutes credited to the Watch of which 90 came
    from the phone. Two devices' segments generally do NOT overlap, so the union ADDS them:
    the "0 overlapping pairs" check that justifies the union gives no protection here."""
    day = dt.date(2026, 9, 1)
    atom(cur, "sleep_core_min", day, 60, interval=_seg(day, 1, 0, 2, 0), device="Apple Watch")
    atom(cur, "sleep_core_min", day, 90, interval=_seg(day, 4, 0, 5, 30),
         device="iPhone (8473)")
    _apply_0056(cur)
    rows = [r for r in panel_rows(cur) if r[1] == "sleep_minutes"]
    assert rows == [(day, "sleep_minutes", 60.0)], (
        f"the Watch's night only, never the union of two devices: {rows}")


def test_INV_4_a_band_recomputed_after_the_knowledge_time_is_not_used(domains):
    """Review finding 12. `f_domain_status` accepted `p_known_at` and applied it to the atoms
    and not to the baselines, although `analysis.baselines.computed_at` exists. A replay's
    `band_position` was therefore computed against a band that did not exist when the question
    was asked — reporting where a value sat inside a band built afterwards."""
    cur = domains
    day = AS_OF - dt.timedelta(days=1)
    _domain(cur, "activity", "steps")
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES (%s,'steps',5000,'legacy')", (day,))
    # A band computed LATER that would place the value inside it.
    cur.execute("""INSERT INTO analysis_pytest.baselines
        (day, metric, value, band_lo, band_hi, computed_at)
        VALUES (%s,'steps',5000,4000,6000,%s)""",
        # After the replay's knowledge time, and before real `now()` — so the default
        # one-argument call sees it and the pinned replay does not. Putting it beyond now()
        # would have made both exclude it and proved nothing.
        (day, dt.datetime.combine(AS_OF + dt.timedelta(days=1), dt.time(12),
                                  tzinfo=dt.timezone.utc)))
    _apply_0056(cur); _apply_0060(cur)

    cur.execute("SELECT band_position FROM analysis_pytest.f_domain_status(%s, %s)",
                (AS_OF, dt.datetime.combine(AS_OF, dt.time(12), tzinfo=dt.timezone.utc)))
    assert cur.fetchone()[0] is None, "a band from the future must not place a past value"

    cur.execute("SELECT band_position FROM analysis_pytest.f_domain_status(%s)", (AS_OF,))
    assert cur.fetchone()[0] == "in_band", "and it must be used once it is known"


def test_REQ_NFR_005_a_stale_latest_value_is_marked_stale(domains):
    """Review finding 12c. `latest_value` was rendered beside a band as "latest" with nothing
    saying it was two years old — `last_day` was returned and nothing said the two disagreed."""
    cur = domains
    _domain(cur, "activity", "steps")
    cur.execute("""INSERT INTO pan_core_pytest.metric_registry
        (metric_key, display_name, family, unit, state_class, max_staleness_days)
        VALUES ('steps','Steps','activity','count','total',3)
        ON CONFLICT (metric_key) DO UPDATE SET max_staleness_days = 3""")
    cur.execute("INSERT INTO analysis_pytest.panel (day, metric, value, src) "
                "VALUES (%s,'steps',5000,'legacy')", (AS_OF - dt.timedelta(days=400),))
    _apply_0056(cur); _apply_0060(cur)
    cur.execute("SELECT value_is_stale FROM analysis_pytest.f_domain_status(%s)", (AS_OF,))
    assert cur.fetchone()[0] is True
