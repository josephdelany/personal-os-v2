"""B5.3 — the MOVEMENTS read API and the Overland receiver (migration 0040, ADR-0046).

Runs on the disposable twins from tests/_location_fixture.py inside ONE rolled-back transaction with
synthetic ocean fixes (0.0 / 0.01), then walks every RPC output for anything coordinate-shaped.
Names carry the IDs (DoD 1/3).

Run: python3 -m pytest tests/test_movements_api.py -v   (needs SUPABASE_DB_URL)
"""
import datetime as dt
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
COORD_KEYS = {"lat", "lon", "latitude", "longitude", "coordinates", "c_lat", "c_lon", "geometry", "lng"}
SYNTH_DAY = dt.date(2026, 1, 5)
T0 = dt.datetime(2026, 1, 5, 15, 0, tzinfo=dt.timezone.utc)      # 10:00 ET
EMPTY_DAY = dt.date(2026, 1, 9)


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


@pytest.fixture(scope="module")
def world():
    """Twins + a home, a gym, a synthetic day of fixes, derived visits. Returns (cursor, ids)."""
    conn = db.connect()
    cur = conn.cursor()
    try:
        lf.apply_chain(cur)
        lf.as_owner(cur)
        cur.execute("select public.register_place('Test Home', 'home', 0.0, 0.0, 75, true)")
        home = _json(cur.fetchone()[0])["place_id"]
        cur.execute("select public.register_place('Test Gym', 'gym', 0.01, 0.0, 75, false)")
        gym = _json(cur.fetchone()[0])["place_id"]
        def fix(minutes, lat, lon):
            cur.execute("select public.ingest_location(NULL, %s, %s, %s, 5, NULL, NULL, NULL, 'shortcut')",
                        (T0 + dt.timedelta(minutes=minutes), lat, lon))
        for m in range(0, 61, 5):      fix(m, 0.0, 0.0)          # home 10:00–11:00
        for m in range(90, 151, 5):    fix(m, 0.01, 0.0)         # gym  11:30–12:30
        for m in range(180, 211, 5):   fix(m, 0.5, 0.5)          # unknown place 13:00–13:30
        for m in range(240, 301, 5):   fix(m, 0.0, 0.0)          # home 14:00–15:00
        cur.execute(f"select {LOC}.derive_visits(%s::date)", ("2026-01-01",))
        n = cur.fetchone()[0]
        assert n == 4, n
        yield cur, {"home": home, "gym": gym}
    finally:
        conn.rollback()
        conn.close()


def _mov(cur, day):
    cur.execute("select public.get_movements(%s::date)", (day,))
    return _json(cur.fetchone()[0])


def _all_outputs(world):
    cur, ids = world
    outs = {"movements_synth": _mov(cur, SYNTH_DAY), "movements_empty": _mov(cur, EMPTY_DAY)}
    cur.execute("select public.get_movements(NULL)"); outs["movements_today"] = _json(cur.fetchone()[0])
    cur.execute("select public.get_place(%s::uuid)", (ids["gym"],)); outs["place_gym"] = _json(cur.fetchone()[0])
    cur.execute("select public.get_place(%s::uuid)", (ids["home"],)); outs["place_home"] = _json(cur.fetchone()[0])
    cur.execute("select public.get_places()"); outs["places"] = _json(cur.fetchone()[0])
    cur.execute("select public.get_entity('place', %s)", (ids["gym"],)); outs["entity_place"] = _json(cur.fetchone()[0])
    return outs


def test_ADR_0036_get_movements_and_get_place_refuse_without_owner_jwt():
    conn = db.connect(); k = conn.cursor()
    try:
        for stmt in ("select public.get_movements(NULL)", "select public.get_place(gen_random_uuid())", "select public.get_places()"):
            k.execute("SAVEPOINT sp")
            with pytest.raises(Exception) as exc:
                k.execute(stmt)
            k.execute("ROLLBACK TO SAVEPOINT sp")
            assert "owner only" in str(exc.value), stmt
    finally:
        conn.rollback(); conn.close()


def test_REQ_LOC_002_no_movement_rpc_output_contains_a_coordinate_key_at_any_depth(world):
    for name, out in _all_outputs(world).items():
        bad = set(_keys(out)) & COORD_KEYS
        assert not bad, (name, bad)


def test_REQ_LOC_002_no_movement_rpc_output_contains_a_number_with_4_plus_decimals(world):
    for name, out in _all_outputs(world).items():
        text = json.dumps(out)
        assert re.search(r"-?\d{1,3}\.\d{4,}", text) is None, (name, text[:300])


def test_REQ_LOC_015_get_movements_day_with_no_fixes_has_coverage_none_and_no_visits_and_no_last_known(world):
    cur, _ = world
    out = _mov(cur, EMPTY_DAY)
    assert out["coverage"]["status"] == "none" and out["coverage"]["fixes"] == 0
    for k in ("visits", "last_known", "mobility"):
        assert k not in out, k
    assert out["day"] == str(EMPTY_DAY)


def test_REQ_LOC_016_unknown_visit_is_labelled_unknown_place_not_nearest(world):
    cur, ids = world
    out = _mov(cur, SYNTH_DAY)
    visits = out["visits"]
    assert [v["label"] for v in visits] == ["Test Home", "Test Gym", "unknown place", "Test Home"]
    unknown = visits[2]
    assert "place_id" not in unknown and "is_home" not in unknown
    assert out["unknown_visits"] == 1
    assert visits[0]["is_home"] is True and visits[1]["place_id"] == ids["gym"]
    m = out["mobility"]
    assert m["distinct_places"] == 2 and m["home_min"] == 120 and m["away_min"] == 90 and m["trips"] == 3
    assert m["first_leave"] == "11:30" and m["last_return"] == "14:00"        # ET clock (15:00 UTC = 10:00 EST)
    assert out["coverage"]["status"] == "fresh" and out["coverage"]["fixes"] == 46


def test_REQ_LOC_017_get_movements_carries_tier_descriptive_and_provisional_true(world):
    cur, ids = world
    for out in (_mov(cur, SYNTH_DAY), _mov(cur, EMPTY_DAY)):
        assert out["tier"] == "DESCRIPTIVE" and out["provisional"] is True
    cur.execute("select public.get_place(%s::uuid)", (ids["gym"],))
    place = _json(cur.fetchone()[0])
    assert place["tier"] == "DESCRIPTIVE" and place["visits_n"] == 1 and place["label"] == "Test Gym"
    assert place["dwell_total_min"] == 60 and "money_here" not in place
    cur.execute("select public.get_places()")
    reg = _json(cur.fetchone()[0])["places"]
    assert [p["label"] for p in reg] == ["Test Home", "Test Gym"] and reg[0]["visits_n"] == 2
    cur.execute("select public.get_place(gen_random_uuid())")
    assert _json(cur.fetchone()[0]) == {"refusal": "I do not track that."}
    cur.execute("select public.get_entity('place', 'not-a-uuid')")
    assert _json(cur.fetchone()[0])["refusal"] == "I do not track that."


def test_REQ_LOC_018_get_movements_renders_with_no_language_layer():
    sql = (ROOT / "migrations" / "0040_movements_api.sql").read_text().lower()
    for token in ("http", "pg_net", "net.http", "extensions.http", "ai.", "workers"):
        assert token not in sql, token


def test_REQ_LOC_005_migrations_0038_0039_0040_and_edge_function_have_no_coordinate_literal():
    for f in ("migrations/0038_restricted_location.sql", "migrations/0039_visits_and_lint.sql",
              "migrations/0040_movements_api.sql", "supabase/functions/location-ingest/index.ts"):
        text = (ROOT / f).read_text()
        assert re.search(r"-?\d{1,3}\.\d{4,}", text) is None, f


def test_ADR_0046_edge_function_never_logs_body():
    ts = (ROOT / "supabase" / "functions" / "location-ingest" / "index.ts").read_text()
    assert "console.log(" not in ts
    for line in ts.splitlines():
        code = line.split("//", 1)[0]                     # the statement, not its comment
        if "console." in code:
            assert "body" not in code and "req" not in code.replace("rpc failed", "") and "message" not in code, line
    assert 'req.headers.get("authorization")' in ts and "Bearer " in ts
    assert '{ result: "ok" }' in ts
