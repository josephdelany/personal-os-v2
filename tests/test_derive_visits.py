"""B5.2 — in-database visit derivation, the public view, the lint (migration 0039, ADR-0045).

Runs on the disposable twins from tests/_location_fixture.py inside ONE rolled-back transaction.
Synthetic fixes are ocean points (0.0 / 0.01 / 0.5), ≤ 3 decimals. Names carry the IDs (DoD 1/3).

Run: python3 -m pytest tests/test_derive_visits.py -v   (needs SUPABASE_DB_URL)
"""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

import pytest

from lib import db
from tests import _location_fixture as lf

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these need the live PG 17 engine",
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOC = lf.LOC_SCHEMA
T0 = dt.datetime(2026, 1, 5, 15, 0, tzinfo=dt.timezone.utc)      # 10:00 ET, subject day 2026-01-05


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


@pytest.fixture()
def cur():
    """Function-scoped: every test starts from empty twins."""
    conn = db.connect()
    c = conn.cursor()
    try:
        lf.apply_chain(c)
        lf.as_owner(c)
        yield c
    finally:
        conn.rollback()
        conn.close()


def _fix(cur, minutes, lat, lon, acc=5):
    at = T0 + dt.timedelta(minutes=minutes)
    cur.execute("select public.ingest_location(NULL, %s, %s, %s, %s, NULL, NULL, NULL, 'shortcut')",
                (at, lat, lon, acc))


def _stay(cur, start_min, dwell_min, lat, lon, every=5):
    for m in range(start_min, start_min + dwell_min + 1, every):
        _fix(cur, m, lat, lon)


def _derive(cur):
    cur.execute(f"select {LOC}.derive_visits(%s::date)", ("2026-01-01",))
    return cur.fetchone()[0]


def _visits(cur):
    cur.execute(f"""select place_id::text, label, is_home, arrive_at, depart_at, dwell_min, n_fixes
                     from {lf.ANALYSIS_TWIN}.visits_public order by arrive_at""")
    return list(cur.fetchall())          # place_id as text: the RPCs return ids as JSON strings


def test_REQ_LOC_009_stay_far_from_every_place_yields_visit_with_null_place_id(cur):
    cur.execute("select public.register_place('Far Place', 'other', 0.5, 0.5, 75, false)")   # ~78 km away
    _stay(cur, 0, 30, 0.0, 0.0)
    assert _derive(cur) == 1
    v = _visits(cur)
    assert len(v) == 1
    assert v[0][0] is None and v[0][1] is None            # unknown, never the nearest guess
    assert v[0][6] == 7 and 29 <= float(v[0][5]) <= 31


def test_REQ_LOC_015_gap_longer_than_max_gap_splits_into_two_visits_and_imputes_nothing(cur):
    _stay(cur, 0, 30, 0.0, 0.0)             # 10:00–10:30
    _stay(cur, 150, 30, 0.0, 0.0)           # 12:30–13:00, same spot, 2 h gap (> max_gap_min 45)
    assert _derive(cur) == 2
    v = _visits(cur)
    assert len(v) == 2
    assert v[0][4] < v[1][3]                                 # first departs before second arrives
    assert float(v[0][5]) + float(v[1][5]) <= 61             # the gap is not counted as dwell anywhere
    cur.execute(f"select count(*) from {lf.ANALYSIS_TWIN}.visits_public where arrive_at < %s and depart_at > %s",
                (T0 + dt.timedelta(minutes=60), T0 + dt.timedelta(minutes=60)))
    assert cur.fetchone()[0] == 0                            # nothing covers 11:00


def test_ADR_0045_stay_shorter_than_min_dwell_is_not_a_visit(cur):
    _stay(cur, 0, 5, 0.0, 0.0)              # 5 min < min_dwell_min 10
    assert _derive(cur) == 0
    assert _visits(cur) == []


def test_REQ_LOC_006_registered_place_within_radius_resolves_and_human_assignment_survives_rebuild(cur):
    cur.execute("select public.register_place('Test Gym', 'gym', 0.0, 0.0, 75, false)")
    gym = _json(cur.fetchone()[0])["place_id"]
    _stay(cur, 0, 30, 0.0, 0.0)             # inside the 75 m radius
    _stay(cur, 120, 30, 0.01, 0.01)         # ~1.6 km away: unknown
    assert _derive(cur) == 2
    v = _visits(cur)
    assert v[0][0] == gym and v[0][1] == "Test Gym"
    assert v[1][0] is None
    # human names the unknown visit; the place is created from the centroid server-side
    cur.execute(f"select visit_id from {LOC}.visits where place_id is null")
    vid = cur.fetchone()[0]
    cur.execute("select public.assign_place(%s, 'Test Cafe', 'restaurant')", (vid,))
    out = _json(cur.fetchone()[0])
    assert out["label"] == "Test Cafe"
    # rebuild: the derived rows are recreated, the human assignment survives (RULE-10)
    assert _derive(cur) == 2
    v = _visits(cur)
    assert v[1][1] == "Test Cafe" and v[1][0] == out["place_id"]


def test_REQ_LOC_012_visits_public_view_exposes_no_coordinate_column(cur):
    cur.execute("select column_name from information_schema.columns where table_schema=%s and table_name='visits_public'",
                (lf.ANALYSIS_TWIN,))
    cols = {r[0] for r in cur.fetchall()}
    assert cols and not cols & {"lat", "lon", "c_lat", "c_lon", "latitude", "longitude"}
    # and the live view has the same shape
    cur.execute("select column_name from information_schema.columns where table_schema='analysis' and table_name='visits_public'")
    live = {r[0] for r in cur.fetchall()}
    assert live == cols


def test_REQ_LOC_005_lint_fails_on_a_restricted_reference_outside_migrations():
    """Writes a throwaway probe file naming a location table, runs the layout gate, expects a FAIL,
    removes the probe. The forbidden token is assembled at runtime so this test file itself passes."""
    token = "restricted" + "." + "location_fixes"
    probe = ROOT / "tools" / "_lint_probe_tmp.py"
    try:
        probe.write_text(f"# probe\nQ = 'select lat from {token}'\n")
        r = subprocess.run([sys.executable, "tools/validate_layout.py"], cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 1
        assert "_lint_probe_tmp.py" in r.stdout and "REQ-LOC-005" in r.stdout
    finally:
        if probe.exists():
            probe.unlink()
    r = subprocess.run([sys.executable, "tools/validate_layout.py"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-800:]
