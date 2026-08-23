"""Behavioural INSERT-path tests for the Phase-2 spine (OQ-21, ADR-0022).

These prove the *acceptance and coercion* paths that a rejection on an empty table
cannot reach: the atoms value/presence/lane CHECKs (RULE-05/07/08, ADR-0002), the
`force_recorded_at` override (ADR-0002/ADR-0019), the `predictions` binary/continuous
XOR (ADR-0021), the `hypothesis_register` freeze happy path (REQ-INF-103), and the
REQ-ONT taxonomy CHECKs (ADR-0023).

RULE-01 / ADR-0022: every row here lives in a DISPOSABLE schema pair
(`core_pytest`/`ops_pytest`, never `core`, never `public`), inside a transaction that
is ROLLED BACK. Nothing is committed, and no row is ever read as data. The migration
is applied ONCE per module; each test runs inside its own SAVEPOINT that is rolled
back afterwards, so tests are isolated and nothing survives.

Run: python3 -m pytest tests/test_spine_insert_paths.py -v
(Requires SUPABASE_DB_URL, same as every ETL path and the invariant suite.)
"""
import os
import pytest

from lib import db
from tools import run_migration

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — spine tests need the live PG 17.6 engine",
)

CORE = "core_pytest"
OPS = "ops_pytest"

CHECK_VIOLATION = "23514"   # Postgres SQLSTATE for a CHECK constraint violation


@pytest.fixture(scope="module")
def spine():
    """Apply the full forward-only migration to a throwaway schema pair ONCE, in a
    transaction that is rolled back at teardown (ADR-0022: nothing persists)."""
    conn = db.connect()
    cur = conn.cursor()
    try:
        run_migration.apply(cur, CORE, OPS)
        yield conn, cur
    finally:
        conn.rollback()   # disposable schema + every fixture row vanish here
        conn.close()


@pytest.fixture()
def cur(spine):
    """Isolate each test inside its own savepoint; roll it back afterwards."""
    conn, cursor = spine
    cursor.execute("SAVEPOINT test_sp")
    yield cursor
    cursor.execute("ROLLBACK TO SAVEPOINT test_sp")


def _capture(cur):
    """Insert a raw_captures row (INV-1 FK target) and return its capture_id."""
    cur.execute(
        f"""INSERT INTO {CORE}.raw_captures
              (capture_id, captured_at, source, trust_level, payload)
            VALUES (gen_random_uuid(), now(), 'pwa_text', 'trusted', '{{}}'::jsonb)
            RETURNING capture_id""")
    return cur.fetchone()[0]


def _rejects(cur, sql, params=None):
    """Assert an INSERT/UPDATE is rejected; return the error string. Savepoint-guarded
    so the surrounding test savepoint is not left aborted."""
    cur.execute("SAVEPOINT p")
    with pytest.raises(Exception) as exc:
        cur.execute(sql, params or ())
    cur.execute("ROLLBACK TO SAVEPOINT p")
    return str(exc.value)


# ---- RULE-07 / RULE-08: the two rows Joe explicitly wanted to SEE insert ---------

def test_RULE_07_observed_absent_row_inserts(cur):
    """A legitimate observed_absent atom ('I logged that I did NOT drink') inserts."""
    cap = _capture(cur)
    cur.execute(
        f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, occurred_at, subject_day, subject_day_rule_version,
               presence, trust_level, provenance, code_version)
            VALUES (%s, 'consume', now(), current_date, 'v1',
                    'observed_absent', 'trusted', 'extracted', 'test')""",
        (cap,))
    assert cur.rowcount == 1


def test_RULE_08_interval_only_nutrition_estimate_inserts(cur):
    """A valid-interval-only nutrition estimate (400/500/600 kcal, labelled) inserts."""
    cap = _capture(cur)
    cur.execute(
        f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, valid_interval, subject_day, subject_day_rule_version,
               presence, value_low, value_point, value_high, estimate_method,
               state_class, unit, trust_level, provenance, code_version)
            VALUES (%s, 'consume', tstzrange(now(), now() + interval '30 minutes'),
                    current_date, 'v1', 'observed', 400, 500, 600, 'labelled',
                    'total', 'kcal', 'trusted', 'extracted', 'test')""",
        (cap,))
    assert cur.rowcount == 1


# ---- RULE-05 / RULE-07 / RULE-08 / ADR-0002: the CHECK constraints reject ---------

def test_RULE_05_atoms_value_requires_lane(cur):
    """INV-5/RULE-05: a stored value with no lane (estimate_method) is rejected."""
    cap = _capture(cur)
    err = _rejects(
        cur,
        f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, occurred_at, subject_day, subject_day_rule_version,
               presence, value_point, state_class, trust_level, provenance, code_version)
            VALUES (%s, 'consume', now(), current_date, 'v1', 'observed', 500,
                    'total', 'trusted', 'extracted', 'test')""",
        (cap,))
    assert "atoms_value_has_lane" in err


def test_RULE_07_unknown_presence_rejects_value(cur):
    """RULE-07: an 'unknown' presence carrying a value is rejected (no collapse to 0)."""
    cap = _capture(cur)
    err = _rejects(
        cur,
        f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, occurred_at, subject_day, subject_day_rule_version,
               presence, value_low, value_point, value_high, estimate_method,
               state_class, trust_level, provenance, code_version)
            VALUES (%s, 'consume', now(), current_date, 'v1', 'unknown', 500, 500, 500,
                    'labelled', 'total', 'trusted', 'extracted', 'test')""",
        (cap,))
    assert "atoms_unknown_has_no_value" in err


def test_ADR_0002_measured_value_must_be_point(cur):
    """ADR-0002: estimate_method='measured' with a non-collapsed interval is rejected."""
    cap = _capture(cur)
    err = _rejects(
        cur,
        f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, occurred_at, subject_day, subject_day_rule_version,
               presence, value_low, value_point, value_high, estimate_method,
               state_class, trust_level, provenance, code_version)
            VALUES (%s, 'body_measurement', now(), current_date, 'v1', 'observed',
                    1, 2, 3, 'measured', 'measurement', 'trusted', 'extracted', 'test')""",
        (cap,))
    assert "atoms_measured_is_point" in err


def test_RULE_08_atoms_value_must_be_ordered(cur):
    """RULE-08: value_low > value_point is rejected (interval must be ordered)."""
    cap = _capture(cur)
    err = _rejects(
        cur,
        f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, occurred_at, subject_day, subject_day_rule_version,
               presence, value_low, value_point, value_high, estimate_method,
               state_class, trust_level, provenance, code_version)
            VALUES (%s, 'consume', now(), current_date, 'v1', 'observed',
                    600, 500, 700, 'labelled', 'total', 'trusted', 'extracted', 'test')""",
        (cap,))
    assert "atoms_value_ordered" in err


# ---- ADR-0002 / ADR-0019: recorded_at is system-set, never client-set ------------

def test_ADR_0002_force_recorded_at_overrides_client_value(cur):
    """A client-supplied backdated recorded_at is overwritten by the trigger to now()."""
    cap = _capture(cur)
    cur.execute(
        f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, occurred_at, recorded_at, subject_day,
               subject_day_rule_version, presence, trust_level, provenance, code_version)
            VALUES (%s, 'consume', now(), '2000-01-01T00:00:00Z', current_date, 'v1',
                    'observed', 'trusted', 'extracted', 'test')
            RETURNING recorded_at""",
        (cap,))
    stored = cur.fetchone()[0]
    # the backdated 2000 value must have been replaced with ~now()
    assert stored.year >= 2026


# ---- ADR-0021: a prediction is exactly one shape --------------------------------

def test_ADR_0021_predictions_shape_is_binary_xor_continuous(cur):
    base = (f"INSERT INTO {CORE}.predictions "
            "(claim_text, resolution_rule, resolves_at, evidence_tier, %s) "
            "VALUES ('c', 'r', now() + interval '1 day', 'DESCRIPTIVE', %s)")
    # binary only — accepted
    cur.execute(base % ("p_forecast", "0.7"))
    assert cur.rowcount == 1
    # continuous only — accepted
    cur.execute(base % ("forecast_distribution", "'{\"q\": [0.1, 0.5, 0.9]}'::jsonb"))
    assert cur.rowcount == 1
    # both — rejected (no defined score)
    err_both = _rejects(
        cur,
        f"""INSERT INTO {CORE}.predictions
              (claim_text, resolution_rule, resolves_at, evidence_tier,
               p_forecast, forecast_distribution)
            VALUES ('c', 'r', now() + interval '1 day', 'DESCRIPTIVE',
                    0.7, '{{\"q\": [0.1]}}'::jsonb)""")
    assert CHECK_VIOLATION in err_both
    # neither — rejected
    err_neither = _rejects(
        cur,
        f"""INSERT INTO {CORE}.predictions
              (claim_text, resolution_rule, resolves_at, evidence_tier)
            VALUES ('c', 'r', now() + interval '1 day', 'DESCRIPTIVE')""")
    assert CHECK_VIOLATION in err_neither


# ---- REQ-INF-103: pre-registration columns frozen, status mutable ----------------

def test_REQ_INF_103_prereg_columns_frozen_status_mutable(cur):
    cur.execute(
        f"""INSERT INTO {CORE}.hypothesis_register
              (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction,
               transformation, adjustment_set, test_statistic, preregistered_at,
               confirmation_data_from, resolution_rule)
            VALUES ('H1', 'sleep_hours', 'rhr', 1, 'negative', 'none',
                    '[]'::jsonb, 'pearson_r', now(), now(), 'r < 0 at q<0.1')""")
    assert cur.rowcount == 1
    # status may change (the legitimate UPDATE path)
    cur.execute(f"UPDATE {CORE}.hypothesis_register SET status = 'REFUTED' WHERE hypothesis_id = 'H1'")
    assert cur.rowcount == 1
    # a pre-registration column may not (the freeze trigger)
    err = _rejects(
        cur,
        f"UPDATE {CORE}.hypothesis_register SET exposure_metric = 'x' WHERE hypothesis_id = 'H1'")
    assert "REQ-INF-103" in err


# ---- REQ-ONT-001 / REQ-ONT-002: the closed taxonomies (ADR-0023) -----------------

def test_REQ_ONT_001_kind_taxonomy_enforced(cur):
    cap = _capture(cur)
    good = (f"""INSERT INTO {CORE}.atoms
              (raw_capture_id, kind, occurred_at, subject_day, subject_day_rule_version,
               presence, trust_level, provenance, code_version)
            VALUES (%s, %s, now(), current_date, 'v1', 'observed',
                    'trusted', 'extracted', 'test')""")
    cur.execute(good, (cap, "workout"))            # a member — accepted
    assert cur.rowcount == 1
    err = _rejects(cur, good, (cap, "banana"))      # not a member — rejected
    assert "atoms_kind_taxonomy" in err


def test_REQ_ONT_002_entity_type_taxonomy_enforced(cur):
    good = (f"INSERT INTO {CORE}.entities (entity_type, canonical_name, provenance) "
            "VALUES (%s, 'X', 'extracted')")
    cur.execute(good, ("merchant",))                # a member — accepted
    assert cur.rowcount == 1
    err = _rejects(cur, good, ("spaceship",))       # not a member — rejected
    assert "entities_type_taxonomy" in err
