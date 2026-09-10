"""Focused Ask migration fixture; prerequisite DDL comes from actual migrations.

This deliberately does not claim full-chain coverage: legacy search/entity and
inference dependencies are not installed. All objects/rows vanish on rollback.
"""
import os
import re

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements


def rebind(sql):
    sql = sql.replace("__CORE__", "ask_core_pytest").replace("__OPS__", "ops_pytest")
    for schema in ("public", "analysis", "config", "auth"):
        sql = re.sub(rf"\b{schema}\.", f"{schema}_pytest.", sql)
        sql = re.sub(rf"\bSCHEMA {schema}\b", f"SCHEMA {schema}_pytest", sql)
    return sql


@pytest.fixture
def ask_cur(sql_connection):
    # Disposable local server only (tools/test_local_sql.py). This fixture builds five schemas
    # from real migration DDL; against the production instance that is hundreds of statements
    # of network round trips, and on 2026-09-09 it began failing with SQLSTATE 57014
    # ("canceling statement due to statement timeout") while creating them — two errors in an
    # otherwise green nightly run. Locally the same work takes well under a second, touches no
    # production catalog, and is covered in CI by the `local-sql` job in tests.yml, so nothing
    # is lost by not running it remotely.
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("Ask SQL fixture builds five schemas; disposable local server only "
                    "(run via tools/test_local_sql.py)")
    cur = sql_connection.cursor()
    for schema in ("ask_core_pytest", "analysis_pytest", "config_pytest", "auth_pytest", "public_pytest"):
        cur.execute(f"CREATE SCHEMA {schema}")
    # The owner-check function reads the same JWT setting as Supabase's helper.
    # It is a test prerequisite, not a claim about external authentication.
    cur.execute("""CREATE FUNCTION auth_pytest.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$
        SELECT nullif(current_setting('request.jwt.claims', true), '')::jsonb $$""")
    for role in ("anon", "authenticated"):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE ROLE {role}")
    cur.execute("SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname='pg_trgm'")
    extension = cur.fetchone()
    if extension:
        extension_schema = extension[0]
    else:
        cur.execute("CREATE SCHEMA extensions_pytest")
        cur.execute("CREATE EXTENSION pg_trgm WITH SCHEMA extensions_pytest")
        extension_schema = "extensions_pytest"

    def apply_file(filename, include=lambda statement: True):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            if include(statement):
                sql = rebind(statement)
                sql = sql.replace("extensions.", '"' + extension_schema.replace('"', '""') + '".')
                cur.execute(sql)

    apply_file("0002_metric_registry.sql")
    # The spine's capture and atom tables. `ask`'s `spend` operation reads `transaction` atoms
    # (B13/ADR-0059 puts the amount there and the merchant descriptor in `evidence_span`), so
    # without them that branch could only fail at runtime.
    apply_file("0004_raw_captures.sql")
    apply_file("0005_atoms.sql")
    # 0059 resolves the spend subject to a merchant entity and follows paid_to
    # edges, so the entity and link tables are now prerequisites of `ask`.
    apply_file("0003_entities.sql")
    apply_file("0006_links.sql")
    apply_file("0026_analysis_schema.sql")
    # The hypothesis register and its resolutions. `ask`'s effect/contrast branch reads both —
    # a registered finding turns an exploratory contrast into a PROMOTED/CONFIRMED effect
    # (REQ-ASK-032) — so without them that whole branch could only fail at runtime, which is
    # why it had no test. Only the table DDL is taken; the API functions those migrations also
    # carry pull in dependencies this fixture deliberately does not install.
    apply_file("0010_hypothesis_register.sql", lambda s: "CREATE TABLE" in s or "CREATE INDEX" in s)
    apply_file("0042_hypothesis_resolutions.sql", lambda s: "CREATE TABLE" in s or "CREATE INDEX" in s)
    apply_file("0034_domain_config.sql")
    apply_file("0047_recommendations.sql", lambda s: any(
        f"{verb} {table}" in s
        for verb in ("CREATE TABLE IF NOT EXISTS", "INSERT INTO")
        for table in ("config.medical_vocabulary", "config.strings", "analysis.render_violations")
    ))
    # The legacy tables `search_record` and `get_entity` read. They are created empty and to
    # the shape those functions expect: the point is to exercise the real functions against
    # the real column names, not a stand-in whose contract could drift from theirs.
    cur.execute("""CREATE TABLE public_pytest.events (
        id BIGSERIAL PRIMARY KEY, user_id UUID, ts TIMESTAMPTZ NOT NULL, kind TEXT NOT NULL,
        payload JSONB, ingested_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE public_pytest.transactions (
        id BIGSERIAL PRIMARY KEY, user_id UUID, ts TIMESTAMPTZ NOT NULL, amount NUMERIC,
        currency TEXT, merchant TEXT, category TEXT, source TEXT, meta JSONB,
        ingested_at TIMESTAMPTZ DEFAULT now())""")
    # Column names taken from the live table, not guessed: `search_record` reads `type` and
    # `note`, and a stub with different columns fails at runtime inside the function under
    # test rather than at fixture build, which reads as a defect in the caller.
    cur.execute("""CREATE TABLE public_pytest.checkins (
        id BIGSERIAL PRIMARY KEY, user_id UUID, ts TIMESTAMPTZ NOT NULL,
        checkin_date DATE, type TEXT, note TEXT, meta JSONB,
        ingested_at TIMESTAMPTZ DEFAULT now())""")
    apply_file("0036_search_record.sql")
    apply_file("0037_get_entity.sql")
    apply_file("0049_ask_core.sql")
    # 0056 gives the two-argument f_daily_panel(date, timestamptz). 0059 calls it everywhere,
    # so the fixture must carry the same dependency the migration order does.
    cur.execute("""CREATE TABLE IF NOT EXISTS analysis_pytest.panel (
        day DATE NOT NULL, metric TEXT NOT NULL, value NUMERIC, src TEXT,
        code_version TEXT, computed_at TIMESTAMPTZ DEFAULT now())""")
    apply_file("0056_atom_panel.sql")
    # 0058 replaces ask(text,date) with ask(text,date,timestamptz) — two clocks.
    apply_file("0058_ask_two_clocks.sql")
    # 0059 wires resolved merchants into spend (ADR-0093).
    apply_file("0059_spend_by_merchant.sql")
    cur.execute("SELECT set_config('request.jwt.claims', %s, true)",
                ('{"email":"joseph.delany21@gmail.com"}',))
    fixture = (ROOT / "tests/fixtures/ask_describe.sql").read_text()
    for statement in split_statements(fixture):
        cur.execute(statement)
    return cur
