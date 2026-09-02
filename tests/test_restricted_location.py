"""B5.1 — the restricted coordinate store, ingress, place registration (migration 0038, ADR-0044).

Every test runs against the disposable twins built by tests/_location_fixture.py inside ONE
transaction that is ROLLED BACK. Coordinates are ocean points (0.0 / 0.01), ≤ 3 decimals.
Names carry the REQ/INV/ADR IDs they cover (DoD 1/3).

Run: python3 -m pytest tests/test_restricted_location.py -v   (needs SUPABASE_DB_URL)
"""
import json
import os
import pathlib
import re

import pytest

from lib import db
from tests import _location_fixture as lf

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these need the live PG 17 engine",
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOC = lf.LOC_SCHEMA


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


@pytest.fixture(scope="module")
def cur():
    conn = db.connect()
    c = conn.cursor()
    try:
        lf.apply_chain(c)
        yield c
    finally:
        conn.rollback()      # twins, rows, replaced RPCs — all gone
        conn.close()


def _ingest(cur, lat, lon, at="2026-01-01T12:00:00+00:00", cid=None, src="shortcut"):
    cur.execute("select public.ingest_location(%s, %s::timestamptz, %s, %s, 5, NULL, 80, NULL, %s)",
                (cid, at, lat, lon, src))
    return _json(cur.fetchone()[0])


def _scalars(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _scalars(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _scalars(v)
    else:
        yield obj


def test_REQ_LOC_001_restricted_schema_has_no_grants_for_anon_authenticated_service_role(cur):
    for role in ("anon", "authenticated", "service_role"):
        cur.execute("select has_schema_privilege(%s, %s, 'USAGE')", (role, LOC))
        assert cur.fetchone()[0] is False, role
    # scoped to the app roles, as the RULE-02 CI check is (ADR-0010): the owner's implicit grants are unrevocable
    cur.execute("""select grantee, privilege_type from information_schema.role_table_grants
                    where table_schema = %s and grantee in ('anon','authenticated','service_role')""", (LOC,))
    assert list(cur.fetchall()) == []


def test_REQ_LOC_004_ingest_location_raw_capture_payload_has_no_coordinate_and_is_trusted(cur):
    cur.execute("select gen_random_uuid()"); cid = cur.fetchone()[0]
    out = _ingest(cur, 0.0, 0.01, cid=cid)
    assert out == {"ok": True}
    cur.execute(f"select payload, trust_level::text, processing_status, source::text from {lf.CORE}.raw_captures where capture_id = %s", (cid,))
    payload, trust, status, source = cur.fetchone()
    payload = _json(payload)
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in _scalars(payload)), payload
    assert payload["redacted"] is True and payload["kind"] == "location"
    assert trust == "trusted" and status == "enriched" and source == "location"
    # a re-post of the same capture id is a duplicate, not a second fix
    assert _ingest(cur, 0.0, 0.01, cid=cid) == {"ok": True, "duplicate": True}
    cur.execute(f"select count(*) from {LOC}.location_fixes where raw_capture_id = %s", (cid,))
    assert cur.fetchone()[0] == 1


def test_INV_1_every_fix_references_a_raw_capture(cur):
    _ingest(cur, 0.0, 0.02)
    cur.execute(f"""select count(*) from {LOC}.location_fixes f
                     left join {lf.CORE}.raw_captures rc on rc.capture_id = f.raw_capture_id
                    where rc.capture_id is null""")
    assert cur.fetchone()[0] == 0
    cur.execute(f"select subject_day, subject_day_rule_version from {LOC}.location_fixes order by recorded_at desc limit 1")
    day, rule = cur.fetchone()
    assert rule == "v1-2026-08-23" and str(day) == "2026-01-01"      # 12:00 UTC = 07:00 ET, same day


def test_INV_2_location_fixes_rejects_update_and_delete(cur):
    _ingest(cur, 0.0, 0.03)
    for stmt in (f"update {LOC}.location_fixes set battery = 1", f"delete from {LOC}.location_fixes"):
        cur.execute("SAVEPOINT sp")
        with pytest.raises(Exception) as exc:
            cur.execute(stmt)
        cur.execute("ROLLBACK TO SAVEPOINT sp")
        assert "RULE-02" in str(exc.value), stmt


def test_REQ_LOC_008_register_place_home_flag_persists_and_is_owner_only(cur):
    cur.execute("SAVEPOINT sp")
    with pytest.raises(Exception) as exc:
        cur.execute("select public.register_place('Test Home', 'home', 0.0, 0.0, 75, true)")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert "owner only" in str(exc.value)
    lf.as_owner(cur)
    cur.execute("select public.register_place('Test Home', 'home', 0.0, 0.0, 75, true)")
    out = _json(cur.fetchone()[0])
    assert out["is_home"] is True and out["kind"] == "home"
    cur.execute(f"select is_home, provenance, corrected_by_human from {LOC}.places_current where place_id = %s", (out["place_id"],))
    assert list(cur.fetchone()) == [True, "human", True]


def test_ADR_0044_ingest_location_batch_parses_overland_geojson_and_returns_result_ok(cur):
    batch = {"locations": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
         "properties": {"timestamp": "2026-01-02T10:00:00Z", "horizontal_accuracy": 10, "speed": 0,
                        "battery_level": 0.5, "motion": ["stationary"]}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0.01, 0.0]},
         "properties": {"timestamp": "2026-01-02T10:05:00Z", "horizontal_accuracy": 12}},
    ]}
    cur.execute("select public.ingest_location_batch(%s::jsonb)", (json.dumps(batch),))
    out = _json(cur.fetchone()[0])
    assert out["result"] == "ok" and out["n"] == 2
    cur.execute(f"select lat, lon, source, motion from {LOC}.location_fixes where source='overland' order by captured_at")
    rows = list(cur.fetchall())
    assert [(r[0], r[1]) for r in rows] == [(0.0, 0.0), (0.0, 0.01)]      # coordinates arrive [lon, lat]
    assert rows[0][3] == ["stationary"] and rows[1][3] is None


def test_REQ_LOC_005_migration_0038_has_no_coordinate_literal():
    sql = (ROOT / "migrations" / "0038_restricted_location.sql").read_text()
    assert re.search(r"-?\d{1,3}\.\d{4,}", sql) is None
