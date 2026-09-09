"""B18 capture: a tapped set becomes strength atoms (REQ-WKT-003/004/005/007).

The shortcut and the registry rows already existed; nothing joined them. These tests are
about the lanes and the refusals, because a strength log that quietly stores a feeling as a
measurement or a bodyweight rep as a load of zero is worse than no strength log.
"""
import datetime as dt
import json
import os
import re
import uuid

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.extract_workouts import extract, rpe_interval, subject_day
from tools.run_migration import split_statements

S = "wkt_core_pytest"
CAPTURED = dt.datetime(2026, 9, 8, 18, 30, tzinfo=dt.timezone.utc)


@pytest.fixture
def cur(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (S, "wkt_ops_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    for filename in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
                     "0022_workout_health_seed.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            c.execute(re.sub(r"\bconfig\.", "config_pytest.", statement.replace("__CORE__", S)))
    return c


def capture(cur, **payload):
    cid = uuid.uuid4()
    payload.setdefault("kind", "workout")
    cur.execute(f"""INSERT INTO {S}.raw_captures
        (capture_id, source, captured_at, payload, trust_level)
        VALUES (%s, 'shortcut_text', %s, %s, 'trusted')""",
        (cid, CAPTURED, json.dumps(payload)))
    return cid


def atoms(cur, metric_key=None):
    q = f"""SELECT metric_key, value_low, value_point, value_high, estimate_method, unit,
                   kind, evidence_span, supersedes
              FROM {S}.atoms WHERE metric_key IS NOT NULL"""
    if metric_key:
        q += f" AND metric_key = '{metric_key}'"
    cur.execute(q + " ORDER BY metric_key, recorded_at")
    return list(cur.fetchall())


def run(cur):
    return extract(cur, S, "wkt_ops_pytest")


def test_REQ_WKT_005_one_set_becomes_three_atoms_sharing_a_set_key(cur):
    """Per-attribute atoms (OQ-33 (a)) — the only shape an atoms row expresses, since it
    carries a single value_point. Every attribute stays individually addressable."""
    cid = capture(cur, exercise="Bench Press", weight_lb="185", reps="5", rpe="8")
    written, counters, seen = run(cur)
    assert (written, seen) == (3, 1), counters
    rows = atoms(cur)
    assert {r[0] for r in rows} == {"strength_load_lb", "strength_reps", "strength_rpe"}
    keys = {re.search(r"set=([^;]+)", r[7]).group(1) for r in rows}
    assert keys == {str(cid)}, "the three attributes must share one set key"
    assert all("exercise=Bench Press" in r[7] for r in rows)
    assert all(r[6] == "workout" for r in rows)


def test_REQ_WKT_007_rpe_is_a_coarsened_self_report_and_load_is_measured(cur):
    """RULE-05. A feeling and a plate do not share a lane. The registry declares RPE on a
    21-point [0,10] scale, so a stated 8 means [7.75, 8.25] — half a step either side."""
    capture(cur, exercise="Squat", weight_lb="225", reps="3", rpe="8")
    run(cur)
    (load,) = atoms(cur, "strength_load_lb")
    assert (load[1], load[2], load[3]) == (225, 225, 225), "a measured value is a point"
    assert load[4] == "measured"
    (rpe,) = atoms(cur, "strength_rpe")
    assert rpe[4] == "self_report", "an RPE stored as measured is a feeling in the plate lane"
    assert (float(rpe[1]), float(rpe[3])) == (7.75, 8.25), rpe


def test_REQ_WKT_007_the_coarsening_step_comes_from_the_registry_scale():
    """RULE-12: the scale has one owner. Reading it at run time means a registry change
    cannot silently disagree with the coarsening applied to the data."""
    assert rpe_interval(8, 0, 10, 21) == (7.75, 8.25)     # 21 points over [0,10] = 0.5 step
    assert rpe_interval(8, 0, 10, 11) == (7.5, 8.5)       # 11 points = 1.0 step
    assert rpe_interval(10, 0, 10, 21) == (9.75, 10)      # clamped to the instrument
    assert rpe_interval(0, 0, 10, 21) == (0, 0.25)


def test_REQ_WKT_004_a_zero_load_is_not_written_as_a_load_of_zero(cur):
    """A bodyweight or assisted movement must be MARKED. The shortcut has no field to mark
    one, so a 0 lb entry is a capture gap that gets counted, not a real load of nothing."""
    capture(cur, exercise="Pull-up", weight_lb="0", reps="8", rpe="7")
    written, counters, _ = run(cur)
    assert counters.get("zero_load_unmarkable_see_REQ_WKT_004") == 1
    assert atoms(cur, "strength_load_lb") == [], "zero was stored as a load"
    assert written == 2, "reps and RPE still land; only the load is withheld"


def test_RULE_06_a_non_numeric_entry_is_a_gap_never_a_guess(cur):
    capture(cur, exercise="Deadlift", weight_lb="a lot", reps="5", rpe="9")
    written, counters, _ = run(cur)
    assert counters.get("absent:strength_load_lb") == 1
    assert atoms(cur, "strength_load_lb") == []
    assert written == 2


def test_REQ_WKT_003_an_out_of_range_value_is_skipped_not_clamped(cur):
    """INV-6 in miniature: the registry's plausible range is a gate, and squeezing a value
    into it would manufacture a plausible number where the truth is a typo."""
    capture(cur, exercise="Curl", weight_lb="9999", reps="5", rpe="6")
    written, counters, _ = run(cur)
    assert counters.get("out_of_range:strength_load_lb") == 1
    assert atoms(cur, "strength_load_lb") == []


def test_RULE_09_the_capture_path_computes_no_derived_training_measure(cur):
    """No e1RM, no volume. Those have their own owner and code_version (REQ-WKT-008/011);
    a capture path that computes them makes the number untraceable."""
    capture(cur, exercise="Bench Press", weight_lb="185", reps="5", rpe="8")
    run(cur)
    assert {r[0] for r in atoms(cur)} == {"strength_load_lb", "strength_reps", "strength_rpe"}
    import inspect
    import tools.extract_workouts as m
    src = inspect.getsource(m)
    assert "e1rm" not in src.lower() or "No e1RM" in src
    assert "* reps" not in src and "volume =" not in src


def test_REQ_WKT_005_extraction_is_idempotent(cur):
    capture(cur, exercise="Row", weight_lb="135", reps="10", rpe="7")
    assert run(cur)[0] == 3
    assert run(cur)[0] == 0, "a second run rewrote atoms for a done capture"
    assert len(atoms(cur)) == 3


def test_RULE_10_a_relogged_set_supersedes_rather_than_sits_beside(cur):
    """Append-only correction. Two loads for one set with nothing superseded would make
    `atoms_current` return both, and a later reader cannot tell which Joe meant."""
    cid = capture(cur, exercise="Bench Press", weight_lb="185", reps="5", rpe="8")
    run(cur)
    # The same SET logged again — same set key, corrected load.
    cur.execute(f"""INSERT INTO {S}.raw_captures
        (capture_id, source, captured_at, payload, trust_level)
        VALUES (%s, 'shortcut_text', %s, %s, 'trusted')""",
        (uuid.uuid4(), CAPTURED, json.dumps(
            {"kind": "workout", "exercise": "Bench Press", "weight_lb": "195",
             "reps": "5", "rpe": "8", "set_key": str(cid)})))
    run(cur)
    loads = atoms(cur, "strength_load_lb")
    assert len(loads) == 2, "the earlier value must remain readable (INV-2)"
    cur.execute(f"""SELECT a.value_point FROM {S}.atoms a
                     WHERE a.metric_key = 'strength_load_lb'
                       AND NOT EXISTS (SELECT 1 FROM {S}.atoms b WHERE b.supersedes = a.id)""")
    current = [r[0] for r in cur.fetchall()]
    assert current == [195], f"exactly one current load, the corrected one; got {current}"


def test_ADR_0019_the_subject_day_uses_the_four_am_boundary():
    """A set logged at 01:00 belongs to the previous training day, not to a new one."""
    late = dt.datetime(2026, 9, 9, 5, 30, tzinfo=dt.timezone.utc)      # 01:30 ET
    assert subject_day(late) == dt.date(2026, 9, 8)
    early = dt.datetime(2026, 9, 9, 13, 0, tzinfo=dt.timezone.utc)     # 09:00 ET
    assert subject_day(early) == dt.date(2026, 9, 9)
