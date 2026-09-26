"""ADR-0173 activation inventory: infer missing migrations from catalog presence only."""
import pytest

from tests._location_fixture import (CORE, OPS, LOC_SCHEMA, _LOC_WORD, _QUALIFIED, _TWIN_OF,
                                     apply_chain)
from tests._sql_fixture import connect, requires_disposable
from tools import v1_activation_check as check


def _files(tmp_path, **sources):
    paths = []
    for name, sql in sources.items():
        path = tmp_path / f"{name}.sql"
        path.write_text(sql)
        paths.append(path)
    return paths


def test_ADR_0173_replay_tracks_drop_rename_and_schema_moves(tmp_path):
    files = _files(tmp_path,
        m0001="CREATE SCHEMA IF NOT EXISTS __CORE__; CREATE TABLE __CORE__.a (x int);"
              "CREATE OR REPLACE FUNCTION public.f(p int) RETURNS int LANGUAGE sql AS $$ SELECT 1; $$;",
        m0002="-- note\nCREATE TABLE __CORE__.gone (x int); DROP TABLE IF EXISTS __CORE__.gone;"
              "ALTER TABLE __CORE__.a RENAME TO b;",
        m0003="ALTER FUNCTION public.f(int) SET SCHEMA __CORE__;"
              "CREATE FUNCTION public.f(p int) RETURNS int LANGUAGE sql AS $$ SELECT 2; $$;",
        m0004="GRANT SELECT ON __CORE__.b TO authenticated;")
    objects = check.expected_objects(files)
    assert objects == {("schema", "core", ""): "m0001.sql", ("table", "core", "b"): "m0002.sql",
                       ("function", "core", "f"): "m0003.sql", ("function", "public", "f"): "m0003.sql"}


def test_ADR_0173_plan_proposes_the_tail_from_the_first_gap(tmp_path):
    files = _files(tmp_path, m1="", m2="", m3="", m4="")
    objects = {("table", "s", "a"): "m1.sql", ("table", "s", "b"): "m2.sql",
               ("table", "s", "c"): "m3.sql", ("table", "s", "d"): "m3.sql"}
    result = check.plan(files, objects, {("table", "s", "a")})
    assert result["proposed_apply"] == ["m2.sql", "m3.sql", "m4.sql"]
    assert [r["status"] for r in result["migrations"]] == ["present", "missing", "missing", "unverifiable"]
    assert result["needs_manual_review"] == {"partial": [], "present_after_first_gap": []}


def test_ADR_0173_partial_and_out_of_order_states_are_flagged_not_hidden(tmp_path):
    files = _files(tmp_path, m1="", m2="", m3="")
    objects = {("table", "s", "a"): "m1.sql", ("table", "s", "b"): "m2.sql",
               ("table", "s", "c"): "m2.sql", ("table", "s", "d"): "m3.sql"}
    result = check.plan(files, objects, {("table", "s", "a"), ("table", "s", "b"), ("table", "s", "d")})
    assert result["proposed_apply"] == ["m2.sql", "m3.sql"]
    assert result["needs_manual_review"] == {"partial": ["m2.sql"], "present_after_first_gap": ["m3.sql"]}
    assert "MANUAL REVIEW" in check.report(result)


def test_ADR_0173_all_present_proposes_nothing(tmp_path):
    files = _files(tmp_path, m1="")
    result = check.plan(files, {("table", "s", "a"): "m1.sql"}, {("table", "s", "a")})
    assert result["proposed_apply"] == []
    assert "No missing or partial migrations" in check.report(result)


def _twin_rewrite(sql):
    sql = sql.replace("__CORE__", CORE).replace("__OPS__", OPS)
    sql = _LOC_WORD.sub(LOC_SCHEMA, sql)
    return _QUALIFIED.sub(lambda m: f"{_TWIN_OF[m.group(1)]}.", sql)


@requires_disposable
def test_ADR_0173_empty_database_reports_every_verifiable_migration_missing():
    conn = connect()
    try:
        result = check.run(conn.cursor(), rewrite=_twin_rewrite)
        statuses = {r["status"] for r in result["migrations"]}
        assert "present" not in statuses and "partial" not in statuses
        assert "0091_v0_checkins.sql" in result["proposed_apply"]
        assert result["proposed_apply"][-1] == "0096_v0_location_daily.sql"
    finally:
        conn.rollback()
        conn.close()


@requires_disposable
def test_ADR_0173_fully_migrated_database_reports_nothing_missing():
    conn = connect()
    try:
        cur = conn.cursor()
        apply_chain(cur)
        result = check.run(cur, rewrite=_twin_rewrite)
        missing = [r for r in result["migrations"] if r["status"] in ("missing", "partial")]
        assert missing == [], missing
        assert result["proposed_apply"] == []
    finally:
        conn.rollback()
        conn.close()
