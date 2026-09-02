"""B9 — the promotion gate to REQ-TIER-012 and the confirmation gate to REQ-TIER-013 (ADR-0050, ADR-0051).

RULE-01's bounded exception (ADR-0022): every row here is a fixture INSERTed into a DISPOSABLE twin
(core_pytest / ops_pytest / analysis_pytest) inside one transaction that is ROLLED BACK. The series are
deterministic (seeded numpy or closed-form), never real data and never plausible personal data.

Run: python3 -m pytest tests/test_confirmation_gate.py -v   (needs SUPABASE_DB_URL)
"""
import datetime as dt
import json
import math
import os

import networkx as nx
import numpy as np
import pytest

from lib import db
from tests._location_fixture import apply_chain, as_owner, CORE, ANALYSIS_TWIN
from tools.engines import confirm, speccurve

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these apply the migration chain to disposable twins",
)

TODAY = dt.date(2026, 9, 2)
D0 = TODAY - dt.timedelta(days=181)          # promotion day: 180 days of post-promotion data
EXPOSURE, OUTCOME = "sleep_asleep_min", "hrv_sdnn"     # a registered edge in the seeded DAG
N_DAYS = 180


def _ar1(rng, n, rho):
    v, out = 0.0, []
    for _ in range(n):
        v = rho * v + rng.standard_normal() * math.sqrt(1 - rho * rho)
        out.append(v)
    return out


def _series(kind, seed=1):
    """Deterministic synthetic series for the exposure and the outcome."""
    rng = np.random.default_rng(seed)
    x = _ar1(rng, N_DAYS, 0.2)
    if kind == "effect":                     # a clean, stable, same-day effect
        y = [2.0 * x[i] + 0.5 * rng.standard_normal() for i in range(N_DAYS)]
    elif kind == "slow":                     # a slowly varying exposure: the future-exposure control must fail
        x = [math.sin(2 * math.pi * i / 60.0) for i in range(N_DAYS)]
        y = [2.0 * x[i] + 0.05 * rng.standard_normal() for i in range(N_DAYS)]
    elif kind == "partial":                  # an effect present in only the first 70% of the window:
        # the refutation tests must fire (measured: the placebo refuter does — a shuffled exposure still
        # tracks the outcome, which is what a placebo failure means)
        y = [(4.0 * x[i] if i < int(N_DAYS * 0.7) else 0.0) + 0.3 * rng.standard_normal() for i in range(N_DAYS)]
    else:                                    # pure noise
        y = _ar1(np.random.default_rng(seed + 7), N_DAYS, 0.2)
    return ({D0 + dt.timedelta(days=i + 1): x[i] for i in range(N_DAYS)},
            {D0 + dt.timedelta(days=i + 1): y[i] for i in range(N_DAYS)})


# The minimal backdoor set for (sleep_asleep_min -> hrv_sdnn) in the seeded DAG is
# {alcohol_standard_drinks, exercise_min}. Every regression conditions on it, so those series must exist
# in the synthetic panel or the design matrix is empty and nothing is testable.
ADJUSTMENT = ("alcohol_standard_drinks", "exercise_min")


def _with_adjustments(series, seed=99):
    rng = np.random.default_rng(seed)
    out = dict(series)
    for i, m in enumerate(ADJUSTMENT):
        vals = _ar1(rng, N_DAYS, 0.1)
        out[m] = {D0 + dt.timedelta(days=k + 1): vals[k] for k in range(N_DAYS)}
    return out


def _insert_panel(cur, series):
    rows = [(d, m, v) for m, dv in series.items() for d, v in dv.items()]
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        cur.execute(f"INSERT INTO {ANALYSIS_TWIN}.panel (day, metric, value, src, code_version) VALUES "
                    + ",".join(["(%s,%s,%s,'fixture','test')"] * len(chunk)),
                    [x for r in chunk for x in r])


def _register(cur, hyp, status="PROMOTED", exposure=EXPOSURE, outcome=OUTCOME, direction="positive",
              promoted_on=D0, next_recheck=None):
    cur.execute(f"""INSERT INTO {CORE}.hypothesis_register
        (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction, transformation,
         adjustment_set, test_statistic, preregistered_at, confirmation_data_from, resolution_rule,
         status, mined_from_preexisting, rule_version)
        VALUES (%s,%s,%s,0,%s,'dow_demedian','["day_of_week"]','quartile_contrast_mannwhitney',
                %s,%s,'v2 template',%s,false,'v2')""",
        (hyp, exposure, outcome, direction,
         dt.datetime.combine(D0, dt.time(), dt.timezone.utc),
         dt.datetime.combine(D0, dt.time(), dt.timezone.utc), status))
    if promoted_on is not None:
        cur.execute(f"""INSERT INTO {CORE}.hypothesis_resolutions
            (hypothesis_id, status_from, status_to, reason, post_days, registered_direction,
             code_version, look, look_day, next_recheck)
            VALUES (%s,'INSUFFICIENT','PROMOTED','promoted_same_sign_p_lt_0_05',%s,%s,'test',1,%s,%s)""",
            (hyp, N_DAYS, direction, promoted_on, next_recheck))


@pytest.fixture(scope="module")
def conn():
    c = db.connect()
    cur = c.cursor()
    apply_chain(cur)
    cur.execute(f"""CREATE TABLE {ANALYSIS_TWIN}.panel (
        day DATE NOT NULL, metric TEXT NOT NULL, value NUMERIC NOT NULL,
        src TEXT NOT NULL, code_version TEXT NOT NULL, PRIMARY KEY (day, metric))""")
    as_owner(cur)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def cur(conn):
    k = conn.cursor()
    k.execute("SAVEPOINT t")
    try:
        yield k
    finally:
        k.execute("ROLLBACK TO SAVEPOINT t")


def _run(cur, today=TODAY):
    return confirm.run(cur, today, core=CORE, panel_schema=ANALYSIS_TWIN)


def _ledger(cur, hyp):
    cur.execute(f"""SELECT status_from, status_to, reason, insufficiency_reason, beta, ci_lo, ci_hi,
                           hac_maxlags, e_value_point, e_value_limit, nc_outcome_metric, nc_outcome_p,
                           nc_exposure_p, refuter_results, counter_frame_n, adjustment_set, next_recheck,
                           prob_direction, run_id, coverage, post_days
                      FROM {CORE}.hypothesis_resolutions
                     WHERE hypothesis_id = %s AND code_version = %s
                     ORDER BY resolved_at DESC, resolution_id DESC""", (hyp, confirm.CODE_VERSION))
    cols = ("status_from", "status_to", "reason", "insufficiency_reason", "beta", "ci_lo", "ci_hi",
            "hac_maxlags", "e_value_point", "e_value_limit", "nc_outcome_metric", "nc_outcome_p",
            "nc_exposure_p", "refuter_results", "counter_frame_n", "adjustment_set", "next_recheck",
            "prob_direction", "run_id", "coverage", "post_days")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _notes(cur, hyp=None):
    q = f"SELECT kind, hypothesis_id, text, tier FROM {ANALYSIS_TWIN}.brief_notes"
    cur.execute(q + (" WHERE hypothesis_id = %s" if hyp else ""), (hyp,) if hyp else ())
    return [dict(zip(("kind", "hypothesis_id", "text", "tier"), r)) for r in cur.fetchall()]


def _status(cur, hyp):
    cur.execute(f"SELECT status FROM {CORE}.hypothesis_register WHERE hypothesis_id=%s", (hyp,))
    return cur.fetchone()[0]


# ---------------------------------------------------------------- the DAG (ADR-0051)

def test_ADR_0051_dag_is_acyclic(cur):
    g, exogenous = confirm.load_dag(cur)
    assert nx.is_directed_acyclic_graph(g), list(nx.find_cycle(g))
    assert exogenous == {"day_of_week", "season"}          # the '*' edges, forced into every regression
    cur.execute("SELECT count(*), count(DISTINCT basis) FROM config.dag_edges")
    n, bases = cur.fetchone()
    assert n >= 22 and bases >= 3
    cur.execute("SELECT DISTINCT basis FROM config.dag_edges")
    assert {r[0] for r in cur.fetchall()} <= {"exogenous_clock", "physiology", "behaviour", "joe"}


def test_REQ_TIER_013_adjustment_set_is_minimal_backdoor_for_seed_edges(cur):
    g, _ = confirm.load_dag(cur)
    z = confirm.minimal_backdoor(g, EXPOSURE, OUTCOME)
    assert z is not None and set(z) == set(ADJUSTMENT), z
    desc = nx.descendants(g, EXPOSURE) | {EXPOSURE}
    for m in z:
        assert m not in desc, m                                   # never adjust for a descendant of the exposure
        assert nx.has_path(g, m, EXPOSURE) and nx.has_path(g, m, OUTCOME), m
    back = g.copy(); back.remove_edges_from(list(g.out_edges(EXPOSURE)))
    assert nx.is_d_separator(back, {EXPOSURE}, {OUTCOME}, set(z))  # sufficient
    from itertools import combinations
    for r in range(len(z)):
        for sub in combinations(z, r):
            assert not nx.is_d_separator(back, {EXPOSURE}, {OUTCOME}, set(sub)), sub   # and minimal
    # a pair the DAG does not know is NOT silently given an empty adjustment set
    assert confirm.minimal_backdoor(g, "not_a_registered_metric", OUTCOME) is None
    assert confirm.minimal_backdoor(g, OUTCOME, EXPOSURE) is None          # no directed path that way


# ---------------------------------------------------------------- the estimator (REQ-TIER-013)

def test_REQ_TIER_013_hac_maxlags_follows_rule():
    for n in (60, 100, 150, 365, 1000):
        assert confirm.hac_maxlags(n) == max(1, int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0)))), n
    assert confirm.hac_maxlags(100) == 4


def test_REQ_TIER_013_e_value_at_point_and_limit_for_known_beta():
    rr = math.exp(0.91)                                    # d = beta*sd_x/sd_y = 1.0
    expected = rr + math.sqrt(rr * (rr - 1))
    point, limit = confirm.e_values(1.0, 0.5, 1.5, 1.0, 1.0)
    assert abs(point - expected) < 1e-3
    rr_lo = math.exp(0.91 * 0.5)                           # the bound NEAREST the null
    assert abs(limit - (rr_lo + math.sqrt(rr_lo * (rr_lo - 1)))) < 1e-3
    assert limit < point
    assert confirm.e_values(1.0, -0.2, 2.0, 1.0, 1.0)[1] == 1.0        # interval spans the null
    assert abs(confirm.e_values(-1.0, -1.5, -0.5, 1.0, 1.0)[0] - point) < 1e-9   # direction-symmetric


# ---------------------------------------------------------------- negative controls (REQ-TIER-014)

def test_REQ_TIER_014_negative_control_outcome_failure_refutes_and_writes_notice(cur):
    x, y = _series("effect")
    # a metric with no directed path from the exposure that is nonetheless a copy of it: a real effect
    # cannot move an unrelated outcome, so the negative control must fire
    _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y, "spend.monetary_7d": dict(x)}))
    _register(cur, "watch:ncout")
    stats = _run(cur)
    assert stats["refuted"] == 1 and _status(cur, "watch:ncout") == "REFUTED"
    row = _ledger(cur, "watch:ncout")[0]
    assert row["reason"] == "refuted_negative_control_failed"
    assert row["nc_outcome_metric"] == "spend.monetary_7d" and float(row["nc_outcome_p"]) < confirm.NC_PASS_P
    (note,) = _notes(cur, "watch:ncout")
    assert note["kind"] == "refutation" and note["tier"] == "DESCRIPTIVE"
    assert "watch:ncout" in note["text"] and "negative control" in note["text"]
    cur.execute("select public.get_today()")
    today = cur.fetchone()[0]
    notices = (today if isinstance(today, dict) else json.loads(today))["notices"]
    assert any(n["hypothesis_id"] == "watch:ncout" and n["tier"] == "DESCRIPTIVE" for n in notices)


def test_REQ_TIER_014_future_exposure_control_failure_refutes(cur):
    x, y = _series("slow")     # a slow exposure: its FUTURE value predicts the past outcome
    _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y}))
    _register(cur, "watch:future")
    stats = _run(cur)
    assert stats["refuted"] == 1 and _status(cur, "watch:future") == "REFUTED"
    row = _ledger(cur, "watch:future")[0]
    assert row["reason"] == "refuted_negative_control_failed"
    assert row["nc_exposure_p"] is not None and float(row["nc_exposure_p"]) < confirm.NC_PASS_P
    assert "future exposure" in _notes(cur, "watch:future")[0]["text"]


def test_REQ_TIER_014_refutation_test_failure_refutes(cur):
    # ADR-0051: the refutation tests are implemented in confirm.py, not via DoWhy (which does not install
    # on the interpreter Joe can run). An effect that reverses halfway fails the data-subset refuter.
    x, y = _series("partial")
    _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y}))
    _register(cur, "watch:refuter")
    stats = _run(cur)
    row = _ledger(cur, "watch:refuter")[0]
    assert stats["refuted"] == 1 and row["reason"] == "refuted_refutation_test_failed"
    ref = row["refuter_results"]
    ref = ref if isinstance(ref, dict) else json.loads(ref)
    assert ref["all_passed"] is False
    assert not (ref["placebo_ok"] and ref["subset_ok"] and ref["random_common_cause_ok"])
    assert "refutation test" in _notes(cur, "watch:refuter")[0]["text"]


def test_REQ_TIER_014_placebo_refuter_does_not_flag_a_real_effect():
    x, y = _series("effect")
    arr, _ = confirm._paired({EXPOSURE: x, OUTCOME: y}, EXPOSURE, OUTCOME, 0, [], D0, TODAY)
    fit = confirm.hac_ols(arr)
    ref = confirm.refuters(arr, "watch:placebo", fit)
    assert ref["placebo_ok"] and ref["placebo_p"] >= confirm.REFUTER_PLACEBO_P
    assert confirm.refuters(arr, "watch:placebo", fit) == ref          # deterministic (RULE-11)


# ---------------------------------------------------------------- the ladder (REQ-TIER-040/041/042)

def test_REQ_TIER_040_confirm_requires_promoted_first(cur):
    _register(cur, "watch:skip", status="INSUFFICIENT", promoted_on=None)
    with pytest.raises(Exception) as exc:
        cur.execute(f"UPDATE {CORE}.hypothesis_register SET status='CONFIRMED_OBSERVATIONAL' "
                    f"WHERE hypothesis_id='watch:skip'")
    assert "REQ-TIER-040" in str(exc.value)
    cur.execute("ROLLBACK TO SAVEPOINT t"); cur.execute("SAVEPOINT t")
    _register(cur, "watch:step", status="INSUFFICIENT", promoted_on=None)
    cur.execute(f"UPDATE {CORE}.hypothesis_register SET status='PROMOTED' WHERE hypothesis_id='watch:step'")
    cur.execute(f"UPDATE {CORE}.hypothesis_register SET status='CONFIRMED_OBSERVATIONAL' WHERE hypothesis_id='watch:step'")
    assert _status(cur, "watch:step") == "CONFIRMED_OBSERVATIONAL"
    cur.execute(f"UPDATE {CORE}.hypothesis_register SET status='REFUTED' WHERE hypothesis_id='watch:step'")
    assert _status(cur, "watch:step") == "REFUTED"       # REQ-TIER-041: any distance down, one step
    x, y = _series("effect"); _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y}))
    assert _run(cur)["considered"] == 0                   # the gate never considers a non-PROMOTED row


def test_REQ_TIER_041_042_monthly_recheck_failure_demotes_with_ledger_row(cur):
    # seed 2: pure noise whose future-exposure control passes, so the row reaches the decision (the
    # control fires on ~20% of noise by construction — B9 sets its bar at p >= 0.20)
    x, y = _series("noise", seed=2)
    _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y}))
    _register(cur, "watch:recheck", status="CONFIRMED_OBSERVATIONAL",
              promoted_on=D0, next_recheck=TODAY - dt.timedelta(days=1))
    cur.execute(f"""INSERT INTO {CORE}.hypothesis_resolutions
        (hypothesis_id, status_from, status_to, reason, post_days, registered_direction, code_version,
         look, look_day, next_recheck)
        VALUES ('watch:recheck','PROMOTED','CONFIRMED_OBSERVATIONAL','confirmed_all_checks_passed',
                120,'positive','test',2,%s,%s)""", (D0, TODAY - dt.timedelta(days=1)))
    stats = _run(cur)
    assert stats["demoted"] == 1
    assert _status(cur, "watch:recheck") == "PROMOTED"
    row = _ledger(cur, "watch:recheck")[0]
    assert row["status_from"] == "CONFIRMED_OBSERVATIONAL" and row["status_to"] == "PROMOTED"
    assert row["reason"] == "demoted_recheck_failed"
    assert any("watch:recheck" in n["text"] for n in _notes(cur, "watch:recheck"))     # REQ-TIER-043
    cur.execute("select public.get_findings()")
    env = cur.fetchone()[0]; env = env if isinstance(env, dict) else json.loads(env)
    assert "watch:recheck" not in {c["hypothesis_id"] for c in env.get("confirmed", [])}
    assert any(h["hypothesis_id"] == "watch:recheck" and h["reason"] == "demoted_recheck_failed"
               for h in env["history"])


def test_REQ_TIER_042_run_id_records_the_job_that_performed_it(cur):
    import uuid
    x, y = _series("noise"); _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y}))
    _register(cur, "watch:job")
    rid = uuid.uuid4()
    confirm.run(cur, TODAY, core=CORE, panel_schema=ANALYSIS_TWIN, run_id=rid)
    rows = _ledger(cur, "watch:job")
    assert rows and all(str(r["run_id"]) == str(rid) for r in rows)


# ---------------------------------------------------------------- RULE-20

def test_RULE_20_forward_prediction_is_scored_at_look_2(cur):
    x, y = _series("effect")
    _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y}))
    _register(cur, "watch:pred")
    # core.predictions CHECKs resolves_at > created_at, so a matured prediction was created before it resolved
    cur.execute(f"""INSERT INTO {CORE}.predictions
        (hypothesis_id, claim_text, resolution_rule, created_at, resolves_at, evidence_tier,
         model_version, p_forecast)
        VALUES ('watch:pred','claim','sign holds', now() - interval '40 days', now() - interval '1 day',
                'PROMOTED', 'resolve-v2', 0.5)""")
    stats = _run(cur)
    assert stats["scored"] == 1
    cur.execute(f"SELECT outcome_bool, brier, resolved_at FROM {CORE}.predictions WHERE hypothesis_id='watch:pred'")
    ok, brier, resolved_at = cur.fetchone()
    assert ok is True and resolved_at is not None
    assert abs(float(brier) - 0.25) < 1e-9      # p_forecast 0.5 -> Brier 0.25 by construction (ADR-0049 b)
    assert _run(cur)["scored"] == 0             # already scored; never scored twice


# ---------------------------------------------------------------- REQ-TIER-012 / 028

def test_REQ_TIER_012_spec_curve_has_108_specs_and_null_share(cur):
    x, y = _series("effect")
    rows, share = speccurve.curve(x, y, 0, "positive")
    assert len(rows) == speccurve.N_SPECS == 108 >= speccurve.MIN_SPECS
    assert len({r["spec_id"] for r in rows}) == 108
    assert {r["transformation"] for r in rows} == set(speccurve.TRANSFORMATIONS)
    assert {r["split"] for r in rows} == set(speccurve.SPLITS)
    assert {r["window"] for r in rows} == set(speccurve.WINDOWS)
    assert {r["test"] for r in rows} == set(speccurve.TESTS)
    assert share > 0.5                                        # a real effect is seen across specifications
    null = speccurve.null_share(x, y, 0, "positive", "watch:spec", reps=5)
    assert share > null                                       # REQ-TIER-012's circular-shift condition
    xn, yn = _series("noise")
    _, share_n = speccurve.curve(xn, yn, 0, "positive")
    assert share_n < 0.5                                      # noise clears neither bar
    speccurve.store(cur, ANALYSIS_TWIN, "watch:spec", 1, rows)
    cur.execute(f"SELECT count(*), count(p), count(DISTINCT window_spec) FROM {ANALYSIS_TWIN}.spec_curves "
                f"WHERE hypothesis_id='watch:spec' AND look=1")
    n, n_p, n_w = cur.fetchone()
    assert n == 108 and n_p > 0 and n_w == 2


def test_REQ_TIER_028_counter_frame_stored_on_promotion(cur):
    x, y = _series("effect")
    _insert_panel(cur, _with_adjustments({EXPOSURE: x, OUTCOME: y}))
    _register(cur, "watch:frame")
    _run(cur)
    row = _ledger(cur, "watch:frame")[0]
    assert row["counter_frame_n"] is not None and row["counter_frame_n"] >= 0
    assert row["counter_frame_n"] == speccurve.counter_frame_n(x, y, 0)
    if row["status_to"] == "CONFIRMED_OBSERVATIONAL":
        cur.execute("select public.get_findings()")
        env = cur.fetchone()[0]; env = env if isinstance(env, dict) else json.loads(env)
        (c,) = [c for c in env["confirmed"] if c["hypothesis_id"] == "watch:frame"]
        assert c["adjustment_set"] is not None and c["e_value"]["point"] is not None
        assert c["negative_controls"]["future_exposure_p"] is not None
        assert c["counter_frame_n"] == row["counter_frame_n"]
        assert c["effect"]["unit"] == OUTCOME and "prob_direction" in c["effect"]
        assert "ci" not in c["effect"]        # REQ-TIER-025: no frequentist interval on a user-facing surface


# ---------------------------------------------------------------- the honesty proof (ADR-0050)

def test_ADR_0050_confirmation_on_pure_noise_synthetic_is_below_5_percent():
    """200 seeded null runs: two independent AR(1) series, the direction PRE-REGISTERED (never chosen
    after seeing the data). The measured rate is the honesty number for this build."""
    n_runs, n_days, confirmed, usable = 200, 150, 0, 0
    d0 = dt.date(2026, 1, 1)
    for r in range(n_runs):
        rng = np.random.default_rng(50_000 + r + 500)
        xs = _ar1(rng, n_days, 0.5)
        ys = _ar1(rng, n_days, 0.5)
        panel = {"x": {d0 + dt.timedelta(days=i): xs[i] for i in range(n_days)},
                 "y": {d0 + dt.timedelta(days=i): ys[i] for i in range(n_days)}}
        lo, hi = d0 - dt.timedelta(days=1), d0 + dt.timedelta(days=n_days)
        arr, _ = confirm._paired(panel, "x", "y", 0, [], lo, hi)
        if len(arr) < confirm.MIN_POST_PROMO_DAYS:
            continue
        usable += 1
        fit = confirm.hac_ols(arr)
        ref = confirm.refuters(arr, f"null{r}", fit)
        fut, _ = confirm._paired(panel, "x", "y", 0, [], lo, hi, x_shift=7)
        ncf = confirm.hac_ols(fut)["p"] if len(fut) >= 20 else None
        confirmed += confirm.checks(fit, "positive", ref, None, ncf)["confirm"]
    rate = confirmed / usable
    assert usable == n_runs
    assert rate < 0.05, f"null confirmation rate {rate:.4f} ({confirmed}/{usable}) is not below 5%"
