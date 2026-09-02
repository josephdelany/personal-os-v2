"""get_entity(p_type, p_key) — the entity page (B4, migration 0037, ADR-0043).

Reads LIVE public.transactions / public.events / core.atoms_current as the owner JWT in one
transaction and ROLLS BACK. No row is written. Names carry the REQ/ADR IDs (DoD 1/3).

Run: python3 -m pytest tests/test_get_entity.py -v   (needs SUPABASE_DB_URL)
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


def _entity(cur, t, k):
    cur.execute("select public.get_entity(%s, %s)", (t, k))
    return _json(cur.fetchone()[0])


@pytest.fixture(scope="module")
def top_merchant(cur):
    cur.execute("select merchant from public.transactions where merchant is not null group by 1 order by count(*) desc limit 1")
    row = cur.fetchone()
    if not row:
        pytest.skip("no transactions")
    return row[0]


@pytest.fixture(scope="module")
def top_channel(cur):
    cur.execute("""select payload->>'channel' from public.events where kind='youtube_watch'
                    and payload->>'channel' is not null group by 1 order by count(*) desc limit 1""")
    row = cur.fetchone()
    if not row:
        pytest.skip("no youtube_watch rows with a channel")
    return row[0]


def test_ADR_0036_get_entity_refuses_without_owner_jwt():
    conn = db.connect(); k = conn.cursor()
    try:
        with pytest.raises(Exception) as exc:
            k.execute("select public.get_entity('merchant', 'x')")
        assert "owner only" in str(exc.value)
    finally:
        conn.rollback(); conn.close()


def test_REQ_ASK_003_get_entity_unknown_type_returns_refusal_string_verbatim(cur):
    out = _entity(cur, "planet", "mars")
    assert out["refusal"] == "I do not track that."
    assert out["nearest"] == ["merchant", "category", "site", "channel", "exercise", "place"]
    assert "n" not in out


def test_ADR_0043_get_entity_place_returns_refusal_until_B5(cur):
    out = _entity(cur, "place", "anywhere")
    assert out["refusal"] == "I do not track that."
    assert "B5" in out["note"]


def test_REQ_INF_505_get_entity_unknown_key_returns_n_zero_and_note_only(cur):
    out = _entity(cur, "merchant", "zzqx-no-such-merchant-9f2")
    assert out["n"] == 0
    assert set(out.keys()) == {"type", "key", "as_of", "n", "note"}


def test_ADR_0043_get_entity_merchant_by_month_sums_to_n(cur, top_merchant):
    out = _entity(cur, "merchant", top_merchant)
    assert out["n"] >= 1 and out["unit"] == "$"
    assert sum(m["n"] for m in out["by_month"]) == out["n"]
    assert sum(w["n"] for w in out["by_weekday"]) == out["n"]
    assert sum(h["n"] for h in out["by_hour"]) == out["n"]
    assert round(sum(m.get("amount", 0) for m in out["by_month"]), 2) == pytest.approx(out["amount_total"], abs=0.05)
    assert out["n_90d"] <= out["n"]


def test_ADR_0043_get_entity_channel_recent_is_newest_first_and_max_20(cur, top_channel):
    out = _entity(cur, "channel", top_channel)
    assert out["unit"] == "events" and "amount_total" not in out
    rec = out["recent"]
    assert 1 <= len(rec) <= 20
    # newest-first by the source row's own timestamp (subject day + clock is not ts order:
    # a 01:30 row belongs to the previous subject day but sorts after that day's 21:58 row)
    cur.execute("""select id::text from public.events where kind='youtube_watch' and payload->>'channel' = %s
                    and ts < ((select public.get_entity('channel', %s)->>'as_of')::date + 1)::timestamptz
                    order by ts desc limit 20""", (top_channel, top_channel))
    assert [r["row_id"] for r in rec] == [row[0] for row in cur.fetchall()]


def test_REQ_ASK_011_get_entity_every_recent_row_has_src_and_row_id_and_top_has_trace(cur, top_merchant):
    out = _entity(cur, "merchant", top_merchant)
    assert out["trace"]["tables"] == "public.transactions"
    assert out["trace"]["key"] == {"type": "merchant", "key": top_merchant}
    for r in out["recent"]:
        assert r["src"] and r["row_id"], r


def test_REQ_INF_109_get_entity_last_seen_not_after_as_of(cur, top_merchant, top_channel):
    for t, k in (("merchant", top_merchant), ("channel", top_channel)):
        out = _entity(cur, t, k)
        assert out["last_seen"] <= out["as_of"], (t, k)
        assert out["first_seen"] <= out["last_seen"]
        for r in out["recent"]:
            assert r["day"] <= out["as_of"]


def test_REQ_LOC_005_migration_0037_has_no_coordinate_literal():
    sql = (ROOT / "migrations" / "0037_get_entity.sql").read_text()
    assert re.search(r"-?\d{1,3}\.\d{4,}", sql) is None
