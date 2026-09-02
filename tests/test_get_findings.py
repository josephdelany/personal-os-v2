"""get_findings() — the FINDINGS lifecycle lists (B6, migration 0041, ADR-0047).

Reads LIVE core.hypothesis_register / core.predictions as the owner JWT in one transaction and
ROLLS BACK. No row is written. Names carry the REQ/ADR IDs (DoD 1/3).

Run: python3 -m pytest tests/test_get_findings.py -v   (needs SUPABASE_DB_URL)
"""
import json
import os

import pytest

from lib import db

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these read the live database",
)

OWNER = '{"email":"joseph.delany21@gmail.com"}'
LISTS = ("watching", "confirmed", "refuted", "insufficient", "predictions_pending")
TIERS = {"WATCHING", "CONFIRMED", "REFUTED", "INSUFFICIENT"}


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


@pytest.fixture(scope="module")
def env(cur):
    cur.execute("select public.get_findings()")
    return _json(cur.fetchone()[0])


def _items(env):
    for k in LISTS:
        for item in env.get(k, []):
            yield k, item


def test_ADR_0036_get_findings_refuses_without_owner_jwt():
    conn = db.connect(); k = conn.cursor()
    try:
        with pytest.raises(Exception) as exc:
            k.execute("select public.get_findings()")
        assert "owner only" in str(exc.value)
    finally:
        conn.rollback(); conn.close()


def test_REQ_TIER_035_get_findings_contains_no_candidate_row(env, cur):
    ids = {item["hypothesis_id"] for _, item in _items(env) if item.get("hypothesis_id")}
    if ids:
        cur.execute("select hypothesis_id from core.hypothesis_register where status='CANDIDATE' and hypothesis_id = any(%s)", (list(ids),))
        assert list(cur.fetchall()) == []
    for _, item in _items(env):
        assert item.get("tier") != "EXPLORATORY"
    # and the register's CANDIDATE rows are counted, never listed
    cur.execute("select count(*) from core.hypothesis_register where status='CANDIDATE'")
    assert env["counts"]["candidates"] == cur.fetchone()[0]


def test_REQ_TIER_005_every_item_carries_tier_and_trace(env):
    for k, item in _items(env):
        assert "trace" in item and item["trace"].get("table"), (k, item)
        if k == "predictions_pending":
            assert "tier" in item, item          # evidence_tier from the prediction row
        else:
            assert item["tier"] in TIERS, (k, item)
            assert item["hypothesis_id"] and "registered_at" in item, (k, item)
    for item in env.get("confirmed", []):
        assert "e_value" not in item and "negative_control" not in item     # absent, never a placeholder


def test_ADR_0047_counts_match_list_lengths_where_lists_present(env):
    c = env["counts"]
    for key in ("watching", "confirmed", "refuted"):
        assert c[key] == len(env.get(key, [])), key
    assert set(c.keys()) == {"candidates", "watching", "confirmed", "refuted"}


def test_ADR_0047_watching_days_elapsed_is_nonnegative(env):
    for w in env.get("watching", []):
        assert w["days_elapsed"] >= 0 and w["days_needed"] == 30
        assert w["status"] in ("INSUFFICIENT", "PROMOTED")
        assert w["source"] == w["hypothesis_id"].replace("watch:", "", 1)
