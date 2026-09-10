"""B19 §G.4 storage — the invariants the table refuses (REQ-INF-560..565, REQ-TIER-046).

The engine computes these correctly and is tested separately. These tests exist because the
engine is not the only possible writer: a later tool, a repair script or a hand-run INSERT can
all reach this table, and an invariant enforced only in Python is enforced only for one caller.
"""
import datetime as dt
import os
import re

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements

S = "chain_core_pytest"


def rebind(sql):
    sql = sql.replace("__CORE__", S)
    for schema in ("analysis", "config"):
        sql = re.sub(rf"\b{schema}\.", f"{schema}_pytest.", sql)
        sql = re.sub(rf"\bSCHEMA {schema}\b", f"SCHEMA {schema}_pytest", sql)
    return sql


@pytest.fixture
def cur(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (S, "analysis_pytest", "config_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    for filename in ("0002_metric_registry.sql", "0026_analysis_schema.sql",
                     "0062_chains_and_roles.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            c.execute(rebind(statement))
    return c


AS_OF = dt.date(2026, 9, 10)


def insert(c, **kw):
    base = dict(as_of=AS_OF, path=["sleep", "energy", "spend"],
                hypothesis_ids=["h1", "h2"], tiers=["PROMOTED", "CANDIDATE"],
                chain_tier="CANDIDATE", attenuated_effect=0.09, rank_score=0.072,
                actionable=True, what_would_firm_it_up="Register the second pair.",
                code_version="chains-v1")
    base.update(kw)
    cols = ", ".join(base)
    c.execute(f"INSERT INTO analysis_pytest.chains ({cols}) "
              f"VALUES ({', '.join(['%s'] * len(base))})", tuple(base.values()))


def _rejects(c, **kw):
    c.execute("SAVEPOINT s")
    try:
        insert(c, **kw)
        c.execute("RELEASE SAVEPOINT s")
        return None
    except Exception as e:                       # noqa: BLE001 — the message is the assertion
        c.execute("ROLLBACK TO SAVEPOINT s")
        return str(e)


def test_REQ_TIER_046_a_chain_tier_stronger_than_its_weakest_edge_is_refused(cur):
    """The engine computes the minimum correctly. This is about every OTHER writer: storing
    CONFIRMED over a CANDIDATE edge would let one well-evidenced link launder a guess, and the
    surface reading this table has no way to tell."""
    err = _rejects(cur, chain_tier="CONFIRMED_OBSERVATIONAL")
    assert "chain_tier_is_the_weakest_edge" in (err or "")
    insert(cur, chain_tier="CANDIDATE")          # the truthful one is accepted


def test_REQ_INF_561_a_path_that_revisits_a_node_is_refused(cur):
    """A cycle reaching storage composes an effect with itself and reports the square of a
    correlation as a discovery."""
    err = _rejects(cur, path=["sleep", "energy", "sleep"])
    assert "path_has_no_repeated_node" in (err or "")


def test_REQ_TIER_046_edge_arrays_must_match_the_path_length(cur):
    """A path of k nodes has exactly k-1 edges. If `tiers` and `path` drift, the weakest-edge
    tier is computed over the wrong set and the CHECK above starts guarding nothing."""
    # `chain_tier` is kept truthful for the shortened array so that the weakest-edge CHECK
    # cannot fire first and make this test pass for the wrong reason.
    err = _rejects(cur, tiers=["CANDIDATE"], chain_tier="CANDIDATE")
    assert "one_edge_between_each_pair" in (err or ""), err
    err = _rejects(cur, hypothesis_ids=["h1", "h2", "h3"])
    assert "one_edge_between_each_pair" in (err or ""), err


def test_REQ_INF_563_a_single_edge_is_not_a_chain(cur):
    """One edge is the hypothesis itself, which get_findings already surfaces. Storing it here
    double-counts one piece of evidence in the reader's mind."""
    err = _rejects(cur, path=["sleep", "energy"], hypothesis_ids=["h1"], tiers=["PROMOTED"],
                   chain_tier="PROMOTED")
    assert "a_chain_is_at_least_two_edges" in (err or "")


def test_REQ_INF_565_a_metric_defaults_to_context_and_never_silently_to_lever(cur):
    """The safe answer to "may Joe act on this?" is no. A metric nobody has classified is
    exactly the one nobody has thought about; defaulting to `lever` would make every new metric
    actionable the moment it appeared."""
    cur.execute(f"""INSERT INTO {S}.metric_registry
                    (metric_key, display_name, family, unit, state_class)
                    VALUES ('weather_temp','Temperature','context','degC','measurement')""")
    cur.execute(f"SELECT role FROM {S}.metric_registry WHERE metric_key = 'weather_temp'")
    assert cur.fetchone()[0] == "context"


def test_REQ_INF_565_role_admits_only_lever_or_context(cur):
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="role"):
        cur.execute(f"""INSERT INTO {S}.metric_registry
                        (metric_key, display_name, family, unit, state_class, role)
                        VALUES ('x','X','f','u','measurement','maybe')""")
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_TIER_046_the_sql_ladder_and_the_python_ladder_agree(cur):
    """Two copies of RULE-16's order exist — analysis.f_tier_rank and chains.TIER_ORDER — and a
    chain whose tier was computed by one and stored under the other would be refused at random.
    They are compared directly rather than trusted to stay aligned."""
    from tools.engines.chains import TIER_ORDER
    for i, tier in enumerate(TIER_ORDER, start=1):
        cur.execute("SELECT analysis_pytest.f_tier_rank(%s)", (tier,))
        assert cur.fetchone()[0] == i, f"{tier} ranks differently in SQL and Python"


def test_REQ_INF_560_the_engine_s_output_is_accepted_by_the_table(cur):
    """The two halves must actually fit. A constraint the engine cannot satisfy is a migration
    that silently disables the feature it was written for."""
    from tools.engines.chains import Edge, build
    ev = dict(n=120, n_eff=41.2, interval=[0.1, 0.5], estimator="hac_ols",
              reverse_check={"nc_exposure_p": 0.6}, family="f")
    edges = [Edge("h1", "sleep", "energy", "PROMOTED", 0.3, 0.8, dict(ev)),
             Edge("h2", "energy", "spend", "CANDIDATE", 0.3, 0.7, dict(ev))]
    chains = build(edges)
    assert chains, "the engine produced nothing to store"
    for c in chains:
        insert(cur, path=list(c.path), hypothesis_ids=[e.hypothesis_id for e in c.edges],
               tiers=list(c.tiers), chain_tier=c.chain_tier,
               attenuated_effect=c.attenuated_effect, rank_score=c.rank_score,
               actionable=c.actionable, what_would_firm_it_up=c.what_would_firm_it_up)
    cur.execute("SELECT count(*), max(attenuated_effect) FROM analysis_pytest.chains")
    n, effect = cur.fetchone()
    assert n == len(chains)
    assert float(effect) == pytest.approx(0.09)
