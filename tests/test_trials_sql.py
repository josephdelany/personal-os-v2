"""B19 §D storage — what the trial tables refuse (REQ-INF-200..216).

A randomized result outranks every observational finding on RULE-16's ladder, which makes this
row the most attractive thing in the system to fudge: move the outcome after seeing the data and
a null becomes an EXPERIMENTAL claim. The engine refuses that. These tests are about every OTHER
writer — a repair script, a later tool, a hand-run UPDATE.
"""
import datetime as dt
import os
import re

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements

S = "trial_core_pytest"


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
                     "0062_chains_and_roles.sql", "0063_micro_trials.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            c.execute(rebind(statement))
    for key, role in (("caffeine_mg", "lever"), ("sleep_minutes", "context"),
                      ("weather_temp", "context")):
        c.execute(f"""INSERT INTO {S}.metric_registry
                      (metric_key, display_name, family, unit, state_class, role)
                      VALUES (%s, %s, 'f', 'u', 'measurement', %s)""", (key, key, role))
    return c


def insert(c, **kw):
    base = dict(exposure="caffeine_mg", outcome="sleep_minutes", block_length_days=7,
                n_blocks_planned=12, washout_days=2,
                washout_justification="caffeine half-life is about six hours",
                randomization_seed="blake2b:trial-1", blinded=False,
                blinding_note="a behavioural exposure admits no indistinguishable placebo",
                primary_outcome_metric="sleep_minutes",
                analysis_method="itt_block_means_hac", mde_sd=3.0, assumed_rho=0.0,
                computed_power=0.91)
    base.update(kw)
    cols = ", ".join(base)
    c.execute(f"INSERT INTO analysis_pytest.trials ({cols}) "
              f"VALUES ({', '.join(['%s'] * len(base))}) RETURNING trial_id",
              tuple(base.values()))
    return c.fetchone()[0]


def _rejects(c, fn):
    c.execute("SAVEPOINT s")
    try:
        fn()
        c.execute("RELEASE SAVEPOINT s")
        return None
    except Exception as e:                       # noqa: BLE001 — the message is the assertion
        c.execute("ROLLBACK TO SAVEPOINT s")
        return str(e)


def test_REQ_INF_216_a_context_exposure_cannot_be_randomised(cur):
    """Randomising something Joe only observes would assign an arm nobody can comply with."""
    err = _rejects(cur, lambda: insert(cur, exposure="weather_temp"))
    assert "REQ-INF-216" in (err or ""), err
    assert "marked context" in (err or "")


def test_REQ_INF_206_a_trial_under_six_weeks_of_blocks_is_refused(cur):
    err = _rejects(cur, lambda: insert(cur, n_blocks_planned=4))
    assert "at_least_six_weeks_of_blocks" in (err or ""), err


def test_REQ_INF_208_an_underpowered_trial_cannot_be_stored(cur):
    """It costs six weeks of Joe's compliance and returns a null that means "we could not have
    seen it" while reading as "it does not work"."""
    err = _rejects(cur, lambda: insert(cur, computed_power=0.55))
    assert "power_at_or_above_the_floor" in (err or ""), err


def test_REQ_INF_203_a_block_no_longer_than_the_washout_is_refused(cur):
    # Block count raised so the six-week rule cannot fire first and make this pass for the
    # wrong reason: 2 x 30 = 60 days clears the duration floor while the washout still binds.
    err = _rejects(cur, lambda: insert(cur, block_length_days=2, n_blocks_planned=30,
                                       washout_days=2))
    assert "block_must_outlast_the_washout" in (err or ""), err


def test_REQ_INF_205_an_unblinded_trial_must_state_the_impossibility(cur):
    """The note is not optional decoration; it is the disclosure that travels with the result."""
    err = _rejects(cur, lambda: insert(cur, blinded=False, blinding_note=None))
    assert "unblinded_states_why" in (err or ""), err
    insert(cur, blinded=True, blinding_note=None)      # a blinded trial needs no excuse


def test_REQ_INF_213_the_outcome_freezes_once_the_first_block_is_assigned(cur):
    """The single most attractive fudge in the system: move the outcome after seeing the data
    and a null becomes an EXPERIMENTAL claim."""
    tid = insert(cur)
    # Still a proposal: editing is allowed, so a rethink does not force delete-and-recreate.
    cur.execute("UPDATE analysis_pytest.trials SET primary_outcome_metric = 'caffeine_mg' "
                "WHERE trial_id = %s", (tid,))
    cur.execute("UPDATE analysis_pytest.trials SET primary_outcome_metric = 'sleep_minutes' "
                "WHERE trial_id = %s", (tid,))
    cur.execute("""INSERT INTO analysis_pytest.trial_assignments
                   (trial_id, block_index, arm, starts_on, ends_on)
                   VALUES (%s, 0, 'A', %s, %s)""",
                (tid, dt.date(2026, 9, 1), dt.date(2026, 9, 7)))

    for column, value in (("primary_outcome_metric", "caffeine_mg"),
                          ("analysis_method", "whatever_shows_something"),
                          ("mde_sd", 0.1), ("n_blocks_planned", 40)):
        err = _rejects(cur, lambda c=column, v=value: cur.execute(
            f"UPDATE analysis_pytest.trials SET {c} = %s WHERE trial_id = %s", (v, tid)))
        assert "REQ-INF-213" in (err or ""), f"{column} was not frozen: {err}"


def test_REQ_INF_213_a_non_prereg_column_still_moves_after_randomisation_begins(cur):
    """The freeze is targeted. `completed_at` must still be writable, or a started trial could
    never be finished — a constraint that blocks the normal path gets disabled, not respected."""
    tid = insert(cur)
    cur.execute("""INSERT INTO analysis_pytest.trial_assignments
                   (trial_id, block_index, arm, starts_on, ends_on)
                   VALUES (%s, 0, 'A', %s, %s)""",
                (tid, dt.date(2026, 9, 1), dt.date(2026, 9, 7)))
    cur.execute("UPDATE analysis_pytest.trials SET completed_at = now() WHERE trial_id = %s",
                (tid,))
    cur.execute("SELECT completed_at IS NOT NULL FROM analysis_pytest.trials "
                "WHERE trial_id = %s", (tid,))
    assert cur.fetchone()[0] is True


def test_REQ_INF_202_a_block_cannot_be_assigned_twice(cur):
    """An assignment that changes when you look at it again is not a randomisation."""
    tid = insert(cur)
    cur.execute("""INSERT INTO analysis_pytest.trial_assignments
                   (trial_id, block_index, arm, starts_on, ends_on)
                   VALUES (%s, 0, 'A', %s, %s)""",
                (tid, dt.date(2026, 9, 1), dt.date(2026, 9, 7)))
    err = _rejects(cur, lambda: cur.execute(
        """INSERT INTO analysis_pytest.trial_assignments
           (trial_id, block_index, arm, starts_on, ends_on) VALUES (%s, 0, 'B', %s, %s)""",
        (tid, dt.date(2026, 9, 1), dt.date(2026, 9, 7))))
    assert "trial_assignments_pkey" in (err or ""), err


def test_REQ_INF_209_a_deviation_must_belong_to_a_real_assigned_block(cur):
    """A deviation from a block that was never assigned is a data error, and silently accepting
    it would let the deviation RATE — which gates EXPERIMENTAL — be computed over a denominator
    that does not exist."""
    tid = insert(cur)
    err = _rejects(cur, lambda: cur.execute(
        """INSERT INTO analysis_pytest.trial_deviations
           (trial_id, block_index, day, assigned_arm) VALUES (%s, 7, %s, 'A')""",
        (tid, dt.date(2026, 9, 3))))
    assert "trial_deviations" in (err or "").lower(), err


def test_REQ_INF_209_one_deviation_row_per_day(cur):
    tid = insert(cur)
    cur.execute("""INSERT INTO analysis_pytest.trial_assignments
                   (trial_id, block_index, arm, starts_on, ends_on)
                   VALUES (%s, 0, 'A', %s, %s)""",
                (tid, dt.date(2026, 9, 1), dt.date(2026, 9, 7)))
    cur.execute("""INSERT INTO analysis_pytest.trial_deviations
                   (trial_id, block_index, day, assigned_arm) VALUES (%s, 0, %s, 'A')""",
                (tid, dt.date(2026, 9, 3)))
    err = _rejects(cur, lambda: cur.execute(
        """INSERT INTO analysis_pytest.trial_deviations
           (trial_id, block_index, day, assigned_arm) VALUES (%s, 0, %s, 'A')""",
        (tid, dt.date(2026, 9, 3))))
    assert err is not None, "a day cannot deviate twice"


def test_REQ_INF_201_the_engine_s_accepted_plan_satisfies_the_table(cur):
    """The two halves must fit. A constraint the engine cannot satisfy is a migration that
    silently disables the feature it was written for."""
    from tools.engines.trials import propose, Refusal
    plan = propose("caffeine_mg", "sleep_minutes", block_days=7, n_blocks=12, mde_sd=3.0,
                   washout_days=2, role="lever")
    assert not isinstance(plan, Refusal), plan
    insert(cur, block_length_days=plan["block_length_days"],
           n_blocks_planned=plan["n_blocks_planned"], washout_days=plan["washout_days"],
           mde_sd=plan["mde_sd"], computed_power=plan["power"],
           analysis_method=plan["analysis_method"],
           primary_outcome_metric=plan["primary_outcome_metric"])
    cur.execute("SELECT count(*) FROM analysis_pytest.trials")
    assert cur.fetchone()[0] >= 1
