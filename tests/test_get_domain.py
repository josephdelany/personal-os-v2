"""get_domain(p_domain, p_window) — the nine-module envelope (B2, migration 0035, ADR-0041).

Reads LIVE config/analysis/core tables as the owner JWT inside one transaction and ROLLS BACK.
No row is written. Names carry the REQ/ADR IDs they cover (DoD item 1/3).

Run: python3 -m pytest tests/test_get_domain.py -v   (needs SUPABASE_DB_URL)
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
TIERS = {"EXPLORATORY", "WATCHING", "CONFIRMED", "REFUTED", "INSUFFICIENT"}
CALLS = [("sleep", "90d"), ("money", "30d"), ("attention", "1y"), ("places", "90d"), ("nonsense", "90d")]

# the seven closed templates of ADR-0041 §sentence (optional 'Stale · Nd. ' prefix)
NUM = r"-?\d+(?:\.\d+)?"
UNIT = r"[^\s(),]+"
TEMPLATES = [
    r".+: never captured\. .+\.",
    r".+: not logged since \d{2} [A-Z][a-z]{2} \d{4}\. .+\.",
    r".+: no scalar summary for this source\.",
    rf".+ {NUM} {UNIT} on \d{{2}} [A-Z][a-z]{{2}}; no personal band yet\.",
    rf".+ in your normal band \({NUM} {UNIT}, band {NUM}–{NUM}\)\.",
    rf".+ {NUM} {UNIT} (?:above|below) your band(?: for the \d+(?:st|nd|rd|th) day)?\.",
]
SENTENCE_RE = re.compile(r"(?:Stale · \d+d\. )?(?:" + "|".join(TEMPLATES) + r")")


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


@pytest.fixture(scope="module")
def conn():
    c = db.connect()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture(scope="module")
def cur(conn):
    return conn.cursor()


@pytest.fixture(scope="module")
def envs(cur):
    """All five owner-JWT envelopes, once per module (one transaction, rolled back at teardown)."""
    cur.execute("select set_config('request.jwt.claims', %s, true)", (OWNER,))
    out = {}
    for dom, win in CALLS:
        cur.execute("select public.get_domain(%s, %s)", (dom, win))
        out[dom] = _json(cur.fetchone()[0])
    return out


def _days(env):
    """Every day-valued field the envelope emits."""
    days = []
    if "hero" in env:
        days.append(env["hero"]["day"])
    for w in env.get("why", []):
        days.append(w["day"])
    for p in env.get("history", {}).get("points", []):
        days.append(p["day"])
    for n in env.get("notables", []):
        days.append(n["day"])
    return days


def test_ADR_0036_get_domain_refuses_without_owner_jwt():
    c = db.connect(); k = c.cursor()
    try:
        with pytest.raises(Exception) as exc:
            k.execute("select public.get_domain('sleep','90d')")
        assert "owner only" in str(exc.value)
    finally:
        c.rollback(); c.close()


def test_REQ_ASK_003_get_domain_unknown_key_returns_refusal_string_verbatim(envs):
    out = envs["nonsense"]
    assert out["refusal"] == "I do not track that."
    assert 1 <= len(out["nearest"]) <= 3
    assert "hero" not in out and "coverage" not in out and "sentence" not in out


def test_REQ_INF_505_get_domain_never_captured_has_no_hero_why_history(envs):
    p = envs["places"]
    assert p["coverage"]["status"] == "never_captured"
    for k in ("hero", "why", "history", "rhythm", "notables", "forecast", "entities"):
        assert k not in p, k
    assert "days_with_data" not in p["coverage"] and "days_in_window" not in p["coverage"]
    assert p["coverage"]["density"] == "none"
    assert p["sentence"].startswith("Places: never captured.")


def test_REQ_INF_109_get_domain_no_day_after_as_of(envs):
    for dom, env in envs.items():
        if "refusal" in env:
            continue
        for day in _days(env):
            assert day <= env["as_of"], (dom, day)
        if "forecast" in env:
            assert env["forecast"]["day_target"] > env["as_of"]     # a forecast is for tomorrow


def test_REQ_NAR_014_get_domain_every_value_carries_unit(envs):
    for dom, env in envs.items():
        if "refusal" in env:
            continue
        for key in ("hero", "history", "rhythm", "forecast"):
            if key in env:
                assert env[key].get("unit"), (dom, key)
        for w in env.get("why", []):
            assert w.get("unit"), (dom, w["metric"])


def test_REQ_ASK_011_get_domain_every_module_carries_trace(envs):
    for dom, env in envs.items():
        if "refusal" in env:
            continue
        for key in ("hero", "history", "rhythm", "forecast"):
            if key in env:
                assert "trace" in env[key], (dom, key)
        for key in ("why", "notables", "drives", "driven_by"):
            for item in env.get(key, []):
                assert "trace" in item, (dom, key, item)


def test_REQ_TIER_053_get_domain_claims_only_from_hypothesis_register(envs, cur):
    ids = {c["hypothesis_id"] for env in envs.values() for k in ("drives", "driven_by") for c in env.get(k, [])}
    if not ids:
        pytest.skip("no claims on any of the five domains today — nothing to verify against the register")
    cur.execute("select hypothesis_id from core.hypothesis_register where hypothesis_id = any(%s)", (list(ids),))
    found = {r[0] for r in cur.fetchall()}
    assert ids == found


def test_REQ_TIER_050_get_domain_claims_are_text_and_labels_only(envs):
    for env in envs.values():
        for k in ("drives", "driven_by"):
            for claim in env.get(k, []):
                assert claim["tier"] in TIERS
                assert claim["sentence"]
                for key, val in claim.items():
                    if isinstance(val, list):
                        assert len(val) <= 2, (key, val)      # n_eff is exactly [hi, lo]; no series


def test_ADR_0041_get_domain_sentence_matches_closed_templates(envs):
    for dom, env in envs.items():
        if "refusal" in env:
            continue
        assert SENTENCE_RE.fullmatch(env["sentence"]), (dom, env["sentence"])


def test_ADR_0041_get_domain_window_all_returns_more_points_than_90d(cur):
    cur.execute("select public.get_domain('sleep','all')")
    n_all = _json(cur.fetchone()[0])["history"]["n"]
    cur.execute("select public.get_domain('sleep','90d')")
    e90 = _json(cur.fetchone()[0])
    n_90 = e90.get("history", {}).get("n", 0)      # the panel's newest sleep day may be >90d ago
    assert n_all > n_90


def test_REQ_LOC_005_migration_0035_has_no_coordinate_literal():
    sql = (ROOT / "migrations" / "0035_get_domain.sql").read_text()
    assert re.search(r"-?\d{1,3}\.\d{4,}", sql) is None
