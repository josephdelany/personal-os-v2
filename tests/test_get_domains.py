"""get_domains() — the SOURCES index (B1, migration 0034, ADR-0040).

Reads LIVE config.* and analysis.panel inside one transaction as the owner JWT, then
ROLLS BACK. No row is written; nothing persists. Names carry the REQ/ADR IDs (DoD 1/3).

Run: python3 -m pytest tests/test_get_domains.py -v   (needs SUPABASE_DB_URL)
"""
import json
import os
import pathlib
import re

import pytest

from lib import db

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these read the live config/panel",
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OWNER = '{"email":"joseph.delany21@gmail.com"}'
STATUSES = {"fresh", "stale", "not_logged", "never_captured"}
TRACE_KEYS = {"table", "day", "metric", "src", "code_version"}


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


@pytest.fixture()
def cur():
    conn = db.connect()
    c = conn.cursor()
    try:
        yield c
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture()
def env(cur):
    """Owner-JWT envelope from the live function."""
    cur.execute("select set_config('request.jwt.claims', %s, true)", (OWNER,))
    cur.execute("select public.get_domains()")
    return _json(cur.fetchone()[0])


def test_ADR_0036_get_domains_refuses_without_owner_jwt(cur):
    cur.execute("SAVEPOINT sp")
    with pytest.raises(Exception) as exc:
        cur.execute("select public.get_domains()")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert "owner only" in str(exc.value)


def test_REQ_INF_505_get_domains_never_emits_hero_for_never_captured(env):
    never = [d for d in env["domains"] if d["coverage"]["status"] == "never_captured"]
    assert never, "expected at least one never-captured domain today (places, calendar)"
    for d in never:
        assert "hero" not in d, d["domain"]
        assert d["coverage"]["density"] == "none", d["domain"]
        assert "days_with_data" not in d["coverage"], d["domain"]     # absent, never 0


def test_REQ_INF_109_get_domains_hero_day_never_after_as_of(env):
    as_of = env["as_of"]
    heroes = [d["hero"] for d in env["domains"] if "hero" in d]
    assert heroes, "expected at least one hero today"
    for h in heroes:
        assert h["day"] <= as_of, h


def test_REQ_NAR_014_get_domains_every_hero_carries_unit_and_trace(env):
    for d in env["domains"]:
        if "hero" in d:
            h = d["hero"]
            assert h.get("unit"), d["domain"]
            assert set(h["trace"].keys()) == TRACE_KEYS, d["domain"]
            assert "value" in h, d["domain"]


def test_ADR_0040_every_seeded_metric_exists_in_panel_or_is_declared_absent(cur):
    cur.execute("""select dm.domain_key, dm.metric from config.domain_metrics dm
                    where not exists (select 1 from analysis.panel p where p.metric = dm.metric)""")
    assert list(cur.fetchall()) == []          # pg8000 returns a tuple


def test_REQ_LOC_005_migration_0034_has_no_coordinate_literal():
    sql = (ROOT / "migrations" / "0034_domain_config.sql").read_text()
    assert re.search(r"-?\d{1,3}\.\d{4,}", sql) is None


def test_ADR_0040_coverage_status_is_closed_vocabulary(env):
    assert env["pillars"] == ["body", "movement", "fuel", "mind", "life"]
    assert len(env["domains"]) == 14
    for d in env["domains"]:
        assert d["coverage"]["status"] in STATUSES, d["domain"]
        assert d["coverage"]["density"] in {"none", "weeks", "months", "years"}, d["domain"]
