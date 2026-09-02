"""search_record(p_q, p_limit) — THE RECORD search (B3, migration 0036, ADR-0042).

Reads LIVE public.events / transactions / checkins / core.atoms_current as the owner JWT in
one transaction and ROLLS BACK. No row is written. Names carry the REQ/ADR IDs (DoD 1/3).

Run: python3 -m pytest tests/test_search_record.py -v   (needs SUPABASE_DB_URL)
"""
import json
import os
import pathlib
import re

import pytest

from lib import db

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these read the live database",
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OWNER = '{"email":"joseph.delany21@gmail.com"}'
NONSENSE = "zzqx-no-such-thing-9f2"


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


@pytest.fixture(scope="module")
def cur():
    conn = db.connect()
    c = conn.cursor()
    c.execute("select set_config('request.jwt.claims', %s, true)", (OWNER,))
    try:
        yield c
    finally:
        conn.rollback()
        conn.close()


def _search(cur, q, limit=50):
    cur.execute("select public.search_record(%s, %s)", (q, limit))
    return _json(cur.fetchone()[0])


@pytest.fixture(scope="module")
def common_term(cur):
    """A term that certainly matches: the most-watched YouTube channel (DISCOVER S3)."""
    cur.execute("""select payload->>'channel' from public.events
                    where kind='youtube_watch' and payload->>'channel' is not null
                    group by 1 order by count(*) desc limit 1""")
    row = cur.fetchone()
    if not row:
        pytest.skip("no youtube_watch rows with a channel")
    return row[0]


def test_ADR_0036_search_record_refuses_without_owner_jwt():
    conn = db.connect(); k = conn.cursor()
    try:
        with pytest.raises(Exception) as exc:
            k.execute("select public.search_record('coffee', 10)")
        assert "owner only" in str(exc.value)
    finally:
        conn.rollback(); conn.close()


def test_ADR_0042_search_record_short_query_returns_empty_with_note(cur):
    out = _search(cur, "a")
    assert out["n"] == 0 and out["hits"] == [] and out["by_month"] == []
    assert out["note"]


def test_REQ_INF_505_search_record_no_match_returns_empty_lists_not_absent(cur):
    out = _search(cur, NONSENSE)
    assert out["n"] == 0
    assert out["hits"] == [] and out["by_month"] == []       # present and empty, never absent
    assert out["truncated"] is False


def test_ADR_0042_search_record_hits_are_newest_first_and_capped(cur, common_term):
    out = _search(cur, common_term, 20)
    assert 1 <= len(out["hits"]) <= 20
    keys = [(h["day"], h["at"]) for h in out["hits"]]
    assert keys == sorted(keys, reverse=True)
    assert out["truncated"] == (out["n"] > 20)


def test_ADR_0042_search_record_by_month_sums_to_n(cur, common_term):
    out = _search(cur, common_term, 5)
    assert sum(m["n"] for m in out["by_month"]) == out["n"]    # counts ALL hits, not the page
    months = [m["month"] for m in out["by_month"]]
    assert months == sorted(months)
    assert all(re.fullmatch(r"\d{4}-\d{2}", m) for m in months)


def test_REQ_ASK_011_search_record_every_hit_has_src_and_row_id(cur, common_term):
    out = _search(cur, common_term, 50)
    for h in out["hits"]:
        assert h["src"] and h["row_id"], h
        assert set(h.keys()) == {"day", "at", "kind", "text", "src", "row_id"}


def test_ADR_0042_search_record_never_touches_restricted_schema():
    text = (ROOT / "migrations" / "0036_search_record.sql").read_text()
    assert "restricted." not in text
    assert "lat" not in text.lower().split()
    assert "lon" not in text.lower().split()


def test_REQ_LOC_005_migration_0036_has_no_coordinate_literal():
    sql = (ROOT / "migrations" / "0036_search_record.sql").read_text()
    assert re.search(r"-?\d{1,3}\.\d{4,}", sql) is None
